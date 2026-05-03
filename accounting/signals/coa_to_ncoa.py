"""
Forward sync: every ``Account`` save mirrors into ``EconomicSegment``.

Wired from ``accounting.apps.AccountingConfig.ready()``. Once attached, every
create / update on Account — through the COA form, the bulk-import endpoint,
the Django admin, the API, or a shell — also writes (or updates) the matching
NCoA EconomicSegment row in the same transaction.

Re-entrancy: the signal only writes to EconomicSegment, never to Account,
so there is no save-loop risk. EconomicSegment has its own clean() rule that
checks ``code[0] == account_type_code``; the mapping in
``coa_to_ncoa_sync.py`` always satisfies that, so the upsert never raises.

Opt-out: setting ``account._skip_ncoa_sync = True`` before calling save()
suppresses the mirror for that one row. Useful inside the backfill endpoint
itself (which calls the mapping directly and doesn't want a recursive trip
through the signal) and inside test suites that need to construct Account
fixtures without touching EconomicSegment.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from accounting.models.gl import Account
from accounting.services.coa_to_ncoa_sync import mirror_account_to_economic_segment


logger = logging.getLogger(__name__)


@receiver(post_save, sender=Account, dispatch_uid='accounting.coa_to_ncoa.mirror_account')
def _mirror_account_on_save(sender, instance: Account, created: bool, **kwargs):
    """Mirror create / update of Account into EconomicSegment."""
    if getattr(instance, '_skip_ncoa_sync', False):
        return
    try:
        obj, was_created = mirror_account_to_economic_segment(instance)
        if obj is None:
            logger.debug(
                'Skipped mirror for Account id=%s code=%r (likely too long or blank).',
                instance.id, instance.code,
            )
            return
        logger.debug(
            'Mirrored Account id=%s code=%s to EconomicSegment id=%s (%s).',
            instance.id, instance.code, obj.id,
            'created' if was_created else 'updated',
        )
    except Exception as exc:
        # Never let a mirror failure roll back the Account save itself.
        # Log loudly so an operator can investigate, but the user's COA
        # write succeeds regardless.
        logger.error(
            'Failed to mirror Account id=%s code=%r to NCoA EconomicSegment: %s',
            instance.id, instance.code, exc, exc_info=True,
        )


def _connect_signals() -> None:
    """No-op — the @receiver decorator already attaches the handler at import.

    Provided as a stable hook in case future signals on this module need to
    be conditionally attached (e.g. behind a feature flag).
    """
    return
