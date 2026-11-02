"""Assign users to MDAs (``core.Organization``) and check tenant membership.

A user's MDA memberships are ``UserOrganization`` rows. Until now nothing in
the app created them, so the active-MDA switcher and the per-MDA data scoping
had nobody to scope. This module is the one place that writes them, used by
user create / edit.
"""
from __future__ import annotations

from typing import Iterable, Mapping

from django.db import transaction
from django_tenants.utils import schema_context

from core.models import UserOrganization

# The model field owns the default role; read it rather than restating it.
DEFAULT_PER_ORG_ROLE = UserOrganization._meta.get_field('per_org_role').get_default()


def replace_user_organizations(
    user,
    assignments: Iterable[Mapping],
    default_organization_id: int | None = None,
) -> list[UserOrganization]:
    """Make ``user``'s MDA memberships exactly ``assignments``.

    Each assignment is ``{'organization': <Organization>, 'per_org_role': str?}``.
    MDAs not listed are removed; listed ones are created or updated in place, so
    calling this twice with the same input changes nothing. Exactly one
    membership is flagged ``is_default``: ``default_organization_id`` if given,
    otherwise the first one listed. An empty list clears every assignment.

    Raises ``ValueError`` if ``default_organization_id`` is not among the
    assignments — a caller bug the serializer is meant to have caught.
    """
    wanted: dict[int, str] = {}
    for item in assignments:
        wanted[item['organization'].pk] = item.get('per_org_role') or DEFAULT_PER_ORG_ROLE

    if wanted:
        if default_organization_id is None:
            default_pk = next(iter(wanted))
        elif default_organization_id in wanted:
            default_pk = default_organization_id
        else:
            raise ValueError('default_organization_id must be one of the assigned MDAs.')
    else:
        default_pk = None

    with transaction.atomic():
        UserOrganization.objects.filter(user=user).exclude(organization_id__in=wanted).delete()
        for org_pk, role in wanted.items():
            UserOrganization.objects.update_or_create(
                user=user,
                organization_id=org_pk,
                defaults={
                    'per_org_role': role,
                    'is_default': org_pk == default_pk,
                    'is_active': True,
                },
            )

    return list(UserOrganization.objects.filter(user=user).select_related('organization'))


def user_in_tenant(user_id: int, tenant) -> bool:
    """True if ``user_id`` has an active role in ``tenant`` and is an active user."""
    from tenants.models import UserTenantRole

    if tenant is None:
        return False
    with schema_context('public'):
        return UserTenantRole.objects.filter(
            tenant=tenant, user_id=user_id, is_active=True, user__is_active=True,
        ).exists()
