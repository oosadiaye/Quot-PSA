"""Supplier self-service: who may sign in, and how a supplier is invited, suspended and let back in.

Activation has two doors, both off until the tenant switches the portal on: a procurement officer invites a supplier
(manual), or the supplier is invited automatically when its registration payment is confirmed (a tenant setting). Either
way the supplier gets a narrow ``vendor`` role and can use only the supplier-portal API, filtered to its own records.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import connection, transaction
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django_tenants.utils import schema_context

from procurement.models import SupplierPortalSettings, Vendor, VendorBankChangeRequest, VendorUser

logger = logging.getLogger(__name__)

User = get_user_model()
VENDOR_ROLE = 'vendor'


class PortalError(Exception):
    """A refusal a person can act on; the message is shown as it is."""


def portal_settings() -> SupplierPortalSettings:
    return SupplierPortalSettings.objects.order_by('pk').first() or SupplierPortalSettings.objects.create()


def _require_enabled() -> SupplierPortalSettings:
    cfg = portal_settings()
    if not cfg.enabled:
        raise PortalError('The supplier portal is switched off for this government. Switch it on in the portal settings first.')
    return cfg


def _send_invitation(user, vendor: Vendor) -> None:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f'{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}'
    send_mail(
        subject='QUOT PSA — your supplier portal account',
        message=(f'{vendor.name} has been invited to the supplier portal. Choose a password here to sign in:\n\n{link}\n\n'
                 'This link expires in 3 days.'),
        from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[user.email], fail_silently=True,
    )


@transaction.atomic
def invite(vendor: Vendor, *, email: str | None = None) -> VendorUser:
    """Create (or reuse) the supplier's sign-in, give it the supplier role, and email a link to choose a password."""
    _require_enabled()
    address = (email or vendor.email or '').strip().lower()
    if not address:
        raise PortalError('This supplier has no email address. Add one to invite it to the portal.')
    existing = VendorUser.objects.select_related('user').filter(vendor=vendor).first()
    if existing is not None and existing.vendor.portal_status == 'active':
        raise PortalError('This supplier is already active on the portal.')

    from tenants.models import Client, UserTenantRole

    schema = connection.schema_name         # read before entering the public schema, which changes it
    with schema_context('public'):
        # Looked up by schema name: under schema_context the connection holds a placeholder tenant, not the row.
        tenant = Client.objects.get(schema_name=schema)
        user = existing.user if existing else User.objects.filter(email__iexact=address).first()
        if user is None:
            user = User(username=address[:150], email=address, is_active=True)
            user.set_unusable_password()
            user.save()
    # VendorUser is a tenant table, so this check runs outside the public schema.
    if VendorUser.objects.filter(user=user).exclude(vendor=vendor).exists():
        raise PortalError('That email address already belongs to another supplier. Use a different one.')
    with schema_context('public'):
        UserTenantRole.objects.update_or_create(user=user, tenant=tenant, defaults={'role': VENDOR_ROLE, 'is_active': True})
    link, _ = VendorUser.objects.get_or_create(vendor=vendor, defaults={'user': user})
    vendor.portal_status = 'invited'
    vendor.portal_invited_at = timezone.now()
    vendor.save(update_fields=['portal_status', 'portal_invited_at', 'updated_at'])
    _send_invitation(user, vendor)
    return link


@transaction.atomic
def activate(vendor: Vendor) -> Vendor:
    """Let an invited supplier in. A supplier whose registration is unpaid or expired signs in only to renew it."""
    _require_enabled()
    if not VendorUser.objects.filter(vendor=vendor).exists():
        raise PortalError('Invite this supplier first: it has no portal sign-in yet.')
    vendor.portal_status = 'active'
    vendor.save(update_fields=['portal_status', 'updated_at'])
    return vendor


@transaction.atomic
def suspend(vendor: Vendor) -> Vendor:
    """Shut a supplier out of the portal without touching its procurement record."""
    vendor.portal_status = 'suspended'
    vendor.save(update_fields=['portal_status', 'updated_at'])
    return vendor


def on_registration_paid(vendor: Vendor) -> None:
    """The registration payment was confirmed: invite (and activate) the supplier when the tenant has asked for that.
    Never lets a portal problem undo a confirmed payment."""
    try:
        cfg = portal_settings()
        if not (cfg.enabled and cfg.auto_activate_on_payment) or vendor.portal_status != 'not_invited' or not vendor.email:
            return
        invite(vendor)
        activate(vendor)
    except Exception:  # noqa: BLE001 - the payment stands whatever happens here
        logger.exception('Supplier portal auto-invite failed for vendor_id=%s', vendor.pk)


def supplier_for(user) -> Vendor | None:
    """The supplier a signed-in user speaks for, only while the portal is on and the supplier is active on it."""
    if user is None or not user.is_authenticated:
        return None
    link = VendorUser.objects.select_related('vendor').filter(user=user).first()
    if link is None or link.vendor.portal_status != 'active' or not portal_settings().enabled:
        return None
    return link.vendor


@transaction.atomic
def request_bank_change(vendor: Vendor, user, *, bank_name: str, bank_account_number: str, bank_sort_code: str = '') -> VendorBankChangeRequest:
    """A supplier asks to change where it is paid. Nothing changes until the procurement office approves it."""
    if VendorBankChangeRequest.objects.filter(vendor=vendor, status='pending').exists():
        raise PortalError('You already have a bank change waiting for approval. Wait for it to be decided first.')
    return VendorBankChangeRequest.objects.create(
        vendor=vendor, requested_by=user, bank_name=bank_name.strip(),
        bank_account_number=bank_account_number.strip(), bank_sort_code=bank_sort_code.strip(),
    )


@transaction.atomic
def decide_bank_change(change: VendorBankChangeRequest, user, *, approve: bool, reason: str = '') -> VendorBankChangeRequest:
    """The procurement office approves (the supplier's bank details change) or rejects (they do not) a request."""
    if change.status != 'pending':
        raise PortalError(f'This request was already {change.status}.')
    if not approve and not reason.strip():
        raise PortalError('Give a reason for rejecting a bank change, so the supplier knows what to fix.')
    change.status = 'approved' if approve else 'rejected'
    change.decided_by, change.decided_at, change.reason = user, timezone.now(), reason.strip()
    change.save()
    if approve:
        v = change.vendor
        v.bank_name, v.bank_account_number, v.bank_sort_code = change.bank_name, change.bank_account_number, change.bank_sort_code
        v.save(update_fields=['bank_name', 'bank_account_number', 'bank_sort_code', 'updated_at'])
    return change
