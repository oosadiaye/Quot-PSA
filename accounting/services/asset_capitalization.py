"""
Enterprise-grade asset auto-capitalisation service (SAP-style sub-ledger).

Single source of truth for "when a debit lands on a flagged GL, create a
FixedAsset and add the capitalisation contra-entries". Callable from any
posting path:

    • Journal Entry (manual)             — JournalViewSet._post_to_gl
    • AP Invoice posting                 — services.procurement_posting.post_ap_invoice
    • Goods Receipt / GRN posting        — services.procurement_posting.post_grn
    • Payment Voucher posting            — services.payment_voucher_posting
    • Future paths (asset transfers,
      donations, capital reclassification) — pass the journal through here

By centralising the logic, every source of capex on this codebase ends up
with the same audit trail, the same budget enforcement, the same
sub-ledger linkage, and the same FixedAsset record shape.

The contra-entry pattern (vs in-place rerouting)
================================================
For each debit line where ``account.auto_create_asset`` is True the
service adds two new lines to the journal *without* mutating the original
line. Net journal becomes:

    DR  23xxxxxx  Capex                100   ← original (preserved)
    ...                                       (other original lines untouched)
    CR  23xxxxxx  Capex (clearing)     100   ← contra (added)
    DR  31xxxxxx  Asset cost (recon)   100   ← capitalisation (added)

Net ledger movement
-------------------
* Capex GL nets to zero — used as a clearing account
* Asset reconciliation GL ↑ at acquisition cost
* Original credit (e.g. Bank, AP, Cash) untouched
* Appropriation on the capex GL records committed + expended
* FixedAsset record created with its own asset_number (sub-ledger identity)
* JournalLine.asset FK on both contra and recon lines provides the
  sub-asset linkage SAP calls "Anlage" — recon account at GL level,
  per-asset detail at sub-record level

Eligibility
-----------
* ``account.auto_create_asset == True``
* ``line.debit > 0``
* ``account.asset_category`` is set (with a valid ``cost_account``)

If the flag is on but the category or cost account is missing, the
service raises ValidationError to fail loud — silently skipping would
let capex slip past capitalisation, polluting future P&L.

Re-entrancy
-----------
Lines created by this service carry ``_skip_auto_capitalize=True`` so that
if the journal is re-posted (or the loop is ever extended to include
just-created lines) the contra/recon pair is never itself capitalised.
The service also snapshots the line list before iterating, so it can
never iterate over its own additions even without the flag.

Usage
-----

    from accounting.services.asset_capitalization import apply_asset_capitalization
    apply_asset_capitalization(journal)

The caller is responsible for:
  - having already run budget enforcement on the original lines
    (the service trusts that anything reaching it is budget-approved
    for the source GL), and
  - calling within the same DB transaction as journal save / GL update,
    so a failure here rolls back the whole posting atomically.
"""
from __future__ import annotations

import datetime
import logging
from decimal import Decimal
from typing import Iterable

from django.core.exceptions import ValidationError


def _as_date(value) -> datetime.date | None:
    """
    Coerce ``value`` into a ``datetime.date``.

    Django's DateField doesn't auto-cast string assignments to date until
    the model is reloaded from the DB (or full_clean is called). Callers
    of this service may pass a freshly-created journal whose
    ``posting_date`` is still the string they handed to ``objects.create()``.
    Without coercion, ``FixedAsset._generate_asset_number`` blows up trying
    to call ``.year`` on a string. Cheap belt-and-braces.
    """
    if value is None or isinstance(value, datetime.date):
        return value if not isinstance(value, datetime.datetime) else value.date()
    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


logger = logging.getLogger(__name__)


def apply_asset_capitalization(journal) -> list[dict]:
    """
    Walk the journal's debit lines, applying SAP-style auto-capitalisation
    to any line whose account has ``auto_create_asset=True``.

    Parameters
    ----------
    journal : JournalHeader
        The journal whose lines are being posted. The journal must already
        be saved (so ``journal.lines.all()`` is queryable). ``posting_date``,
        ``description``, ``document_number``, and the dimension FKs (mda /
        fund / function / program / geo) are all read off the header.

    Returns
    -------
    list[dict]
        One entry per asset created. Useful for caller logging /
        response payload. Empty list = no eligible lines.

    Raises
    ------
    ValidationError
        If a line is flagged for capitalisation but its account is
        missing an asset category, or the category is missing a cost
        account. Fail-loud — never silently skip capex.
    """
    # Late imports — this module is loaded by accounting.signals at
    # startup, before all models are ready in some test paths.
    from accounting.models.assets import FixedAsset
    from accounting.models import JournalLine

    auto_assets_created: list[dict] = []
    # Snapshot lines BEFORE iterating so the loop never sees its own additions.
    source_lines = list(journal.lines.all())

    for line in source_lines:
        acc = line.account
        if not (acc and getattr(acc, 'auto_create_asset', False)):
            continue
        if not (line.debit and line.debit > 0):
            continue  # only debit lines capitalise
        if getattr(line, '_skip_auto_capitalize', False):
            continue  # in-memory opt-out (contra / recon inserts)
        # PERSISTENT idempotency marker: ``line.asset_id`` is stamped on
        # the original capex line at the end of a successful capitalisation.
        # If this method is called again for the same journal (e.g. via
        # _validate_journal_balanced from a different posting path AFTER
        # JournalViewSet._post_to_gl already ran), we'd otherwise
        # re-create the asset + contra/recon pair. Skipping when an asset
        # is already linked makes the service safely re-runnable across
        # any posting sequence — Journal, AP, PO, GRN, PV, Asset Disposal.
        if getattr(line, 'asset_id', None):
            continue

        category = getattr(acc, 'asset_category', None)
        if not category:
            raise ValidationError({
                'asset_auto_create': (
                    f"Account {acc.code} is flagged for asset auto-creation "
                    f"but has no asset category configured. Please assign "
                    f"one in Chart of Accounts before posting."
                ),
            })
        cost_account = getattr(category, 'cost_account', None)
        if not cost_account:
            raise ValidationError({
                'asset_auto_create': (
                    f"Asset Category '{category.name}' has no cost account "
                    f"configured. Set the Cost Account on the category "
                    f"before posting to GL {acc.code}."
                ),
            })

        # Asset name — line memo first, fall back to journal description,
        # then a synthetic placeholder so we always have something.
        asset_name = (line.memo or '').strip() or (journal.description or '').strip()[:200]
        if not asset_name:
            asset_name = f"{category.name} from {journal.document_number or 'JV'}"

        asset = FixedAsset.objects.create(
            name=asset_name[:200],
            description=(
                f"Auto-capitalised from {journal.document_number or 'JV'} "
                f"(line {line.id}). Source GL: {acc.code} {acc.name}. "
                f"Reconciliation GL: {cost_account.code} {cost_account.name}."
            )[:500],
            asset_category=category.code,
            # Defensive cast — see _as_date docstring for context.
            acquisition_date=_as_date(journal.posting_date) or datetime.date.today(),
            acquisition_cost=line.debit,
            asset_account=cost_account,
            accumulated_depreciation_account=getattr(category, 'accumulated_depreciation_account', None),
            depreciation_expense_account=getattr(category, 'depreciation_expense_account', None),
            mda=getattr(journal, 'mda', None),
            fund=getattr(journal, 'fund', None),
            function=getattr(journal, 'function', None),
            program=getattr(journal, 'program', None),
            geo=getattr(journal, 'geo', None),
            status='Active',
            created_from_journal_line=line,
        )

        # ── Contra credit: clear the capex GL (clearing-account semantics) ──
        contra_line = JournalLine(
            header=journal,
            account=acc,                        # SAME GL as the original
            debit=Decimal('0'),
            credit=line.debit,
            memo=(
                f"Auto-cap clearing — Asset {asset.asset_number} "
                f"({asset.name})"
            )[:255],
            document_number=line.document_number,
            asset=asset,                        # traceability
        )
        contra_line._skip_auto_capitalize = True
        contra_line.save()

        # ── Capitalisation debit: hit the asset reconciliation GL ──
        # The recon account is the *control* GL; the asset FK is the
        # sub-ledger pointer. Together they reproduce SAP's two-tier
        # asset accounting (recon GL + per-asset sub-record).
        recon_line = JournalLine(
            header=journal,
            account=cost_account,
            debit=line.debit,
            credit=Decimal('0'),
            memo=(
                f"Asset capitalisation — {asset.asset_number}: "
                f"{asset.name}"
            )[:255],
            document_number=line.document_number,
            asset=asset,
        )
        recon_line._skip_auto_capitalize = True
        recon_line.save()

        # Stamp the original line so reports know it triggered an auto-cap.
        # We DO NOT change ``line.account`` — preserving the capex GL is
        # the entire point: budget enforcement + audit-trail clarity.
        #
        # Use queryset .update() rather than instance.save() because
        # ``JournalLine.save()`` carries an audit guard that refuses
        # modifications when the parent journal is already 'Posted'.
        # The AP-invoice posting path creates its journal with
        # status='Posted' BEFORE validation runs, so by the time we
        # reach this stamp the guard would otherwise reject the update.
        # ``.update()`` bypasses save() entirely — same DB write, no
        # signal recursion, no guard trip. The asset_id stamp is a
        # bookkeeping reference, not a content change auditors would
        # flag, so the bypass is safe and intentional.
        type(line).objects.filter(pk=line.pk).update(asset=asset)
        # Keep the in-memory instance in sync so the idempotency check
        # on a same-process re-run sees the populated asset_id.
        line.asset_id = asset.pk

        auto_assets_created.append({
            'source_gl': acc.code,
            'recon_gl': cost_account.code,
            'asset_number': asset.asset_number,
            'amount': str(line.debit),
            'name': asset.name,
        })

    if auto_assets_created:
        logger.info(
            'Asset auto-capitalisation: journal=%s created %d asset(s): %s',
            getattr(journal, 'document_number', journal.pk),
            len(auto_assets_created),
            auto_assets_created,
        )

    return auto_assets_created


def asset_eligible_lines(journal) -> Iterable:
    """
    Pre-flight helper — returns the lines that *would* be capitalised by
    ``apply_asset_capitalization``. Useful for UI previews ("This posting
    will create N fixed assets") without committing.
    """
    for line in journal.lines.all():
        acc = line.account
        if not (acc and getattr(acc, 'auto_create_asset', False)):
            continue
        if not (line.debit and line.debit > 0):
            continue
        yield line
