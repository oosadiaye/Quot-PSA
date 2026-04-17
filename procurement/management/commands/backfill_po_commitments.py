"""Backfill ProcurementBudgetLink rows for existing Approved/Posted POs.

Use this after the Approved-status commitment hook was added, to retro-fit
commitments for POs that were approved *before* the hook existed. Without
this backfill, old POs show up in lists but contribute 0 to the Budget
Execution Report's "Committed" column.

Usage:
    python manage.py backfill_po_commitments                 # dry-run
    python manage.py backfill_po_commitments --apply         # write changes
    python manage.py backfill_po_commitments --apply -v 2    # verbose
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from procurement.models import PurchaseOrder, ProcurementBudgetLink
from accounting.services.procurement_commitments import create_commitment_for_po


class Command(BaseCommand):
    help = "Create ProcurementBudgetLink for Approved/Posted POs missing one."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually write the ProcurementBudgetLink rows. "
                 "Without this flag the command only reports what would change.",
        )

    def handle(self, *args, **options) -> None:
        apply_changes: bool = options["apply"]
        pos = PurchaseOrder.objects.filter(
            status__in=["Approved", "Posted"],
        ).exclude(
            pk__in=ProcurementBudgetLink.objects.values_list("purchase_order_id", flat=True),
        )

        total = pos.count()
        self.stdout.write(
            self.style.NOTICE(
                f"Found {total} Approved/Posted PO(s) without a ProcurementBudgetLink."
            )
        )

        created = 0
        skipped = 0
        errors: list[str] = []

        for po in pos:
            reason = ""
            try:
                if apply_changes:
                    with transaction.atomic():
                        ok = create_commitment_for_po(po)
                    if not ok:
                        _, reason = _would_create(po)
                else:
                    ok, reason = _would_create(po)
            except Exception as exc:  # pragma: no cover
                errors.append(f"{po.po_number}: {exc}")
                continue

            if ok:
                created += 1
                self.stdout.write(f"  [OK] {po.po_number} - linked")
            else:
                skipped += 1
                self.stdout.write(f"  [-]  {po.po_number} - {reason}")

        mode = "APPLIED" if apply_changes else "DRY-RUN"
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"[{mode}] linked={created}  skipped={skipped}  errors={len(errors)}"
        ))
        for err in errors:
            self.stdout.write(self.style.ERROR(f"  [!] {err}"))

        if not apply_changes and created:
            self.stdout.write(
                self.style.WARNING(
                    "Re-run with --apply to write these rows."
                )
            )


def _would_create(po: PurchaseOrder) -> tuple[bool, str]:
    """Dry-run probe: returns (ok, reason) so the command can print why.

    Mirrors ``create_commitment_for_po``'s prerequisites, including the
    economic-segment parent-chain fallback.
    """
    from accounting.models.ncoa import (
        AdministrativeSegment, EconomicSegment, FundSegment,
    )
    from budget.models import Appropriation

    if not po.mda or not po.fund or not po.lines.exists():
        return False, "missing MDA, Fund, or lines"
    first = po.lines.first().account
    if not first:
        return False, "first line has no GL account"
    admin = AdministrativeSegment.objects.filter(legacy_mda=po.mda).first()
    econ = EconomicSegment.objects.filter(legacy_account=first).first()
    fund = FundSegment.objects.filter(legacy_fund=po.fund).first()
    missing = [
        name for name, seg in (('admin', admin), ('econ', econ), ('fund', fund))
        if seg is None
    ]
    if missing:
        return False, f"NCoA bridges missing: {missing}"

    # Walk up the Economic parent chain (rollup).
    candidates = [econ]
    cursor = econ.parent
    while cursor is not None:
        candidates.append(cursor)
        cursor = cursor.parent

    found = Appropriation.objects.filter(
        administrative=admin,
        economic__in=candidates,
        fund=fund,
        status="ACTIVE",
    ).exists()
    if found:
        return True, "match found"
    codes = ", ".join(c.code for c in candidates)
    return False, (
        f"no ACTIVE Appropriation for MDA={admin.code} / Fund={fund.code} / "
        f"Econ in [{codes}] -- create one to back this PO"
    )
