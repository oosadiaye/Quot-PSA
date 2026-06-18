"""Mirror TreasuryAccount → BankAccount on create.

Every active TSA needs a BankAccount mirror row so it shows up in the
"Bank Account" dropdown on screens that pick a payment source (New
Outgoing Payment, Vendor Advance, etc.). The mirror reuses the TSA's
`gl_cash_account` so GL postings still hit the right cash control.

Why a signal instead of relying only on the lazy sync in
`BankAccountViewSet.get_queryset`:
- New tenants seeding TSAs (provisioning, migration, fixtures) get
  their bank accounts populated immediately, with no dependence on
  whether the UI has been visited yet.
- Manually-created TSAs in Django admin get a mirror without an extra
  step.
- Background jobs that bypass the bank-accounts list endpoint (PV
  posting, reconciliation seeds) can rely on the mirror existing.

Idempotent: matched by `account_number`. Re-saving a TSA never
duplicates the mirror; it just refreshes `is_active`, `bank_name` and
`current_balance` to track the source row.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from ..models import BankAccount
from ..models.treasury import TreasuryAccount

logger = logging.getLogger(__name__)


@receiver(post_save, sender=TreasuryAccount)
def mirror_tsa_to_bank_account(sender, instance: TreasuryAccount, created: bool, **kwargs) -> None:
    """Create or refresh the BankAccount mirror for a TreasuryAccount.

    On **create**: seed every field, including `currency=None` (most
    tenants have no default Currency row at id=1).

    On **update**: only refresh the fields the TSA is authoritative
    for (name, gl_account, bank_name, is_active). Leave `currency`,
    `opening_balance`, and `current_balance` untouched so a manual
    edit on the BankAccount mirror (e.g. an operator picked the right
    currency post-creation) survives subsequent TSA saves.

    Was: every save reset `currency` to None, wiping any manual fix.
    """
    try:
        if created:
            defaults = {
                'name': f"TSA: {instance.account_name}",
                'account_type': 'Bank',
                'gl_account': instance.gl_cash_account,
                'bank_name': instance.bank or '',
                'is_active': bool(instance.is_active),
                'opening_balance': instance.current_balance or 0,
                'current_balance': instance.current_balance or 0,
                'currency': None,
            }
        else:
            # Refresh only TSA-derived fields; never clobber currency
            # or balances on update.
            defaults = {
                'name': f"TSA: {instance.account_name}",
                'gl_account': instance.gl_cash_account,
                'bank_name': instance.bank or '',
                'is_active': bool(instance.is_active),
            }
        BankAccount.objects.update_or_create(
            account_number=instance.account_number,
            defaults=defaults,
        )
    except Exception:
        # Mirror creation gates outgoing payment selection — a failed
        # mirror means operators can't pick this TSA in the payment
        # form. Log at ERROR (not WARNING) so on-call notices; we still
        # don't re-raise because blocking the underlying TSA save would
        # be worse — the admin can manually trigger a re-mirror.
        logger.error(
            'Failed to mirror TSA %s to BankAccount',
            instance.account_number, exc_info=True,
        )
