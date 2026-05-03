"""
Seed demo data for Bank Reconciliation E2E testing.

Builds the minimum set of records needed to exercise every branch of the
``auto_match_statement`` service:

    * TreasuryAccount (reused or created)
    * PaymentVoucherGov + PaymentInstruction (status=PROCESSED) — debit side
    * RevenueCollection (status=POSTED) — credit side
    * A CSV statement fixture written to ``media/demo_fixtures/`` containing:
        - exact-reference matches (strategy 1, confidence 99)
        - amount+date matches with blank/different reference (strategy 2, 85)
        - intentionally unmatched rows (bank charges, stale lodgement) so the
          reconciliation session surfaces reconciling items

Usage
-----
    python manage.py tenant_command seed_demo_bank_reconciliation --schema=<name>
    python manage.py tenant_command seed_demo_bank_reconciliation --schema=<name> --clear
    python manage.py tenant_command seed_demo_bank_reconciliation --schema=<name> --days-ago 7

The command is idempotent — rerunning updates (not duplicates) the tagged
records. ``--clear`` removes prior ``DEMO-BR-*`` rows and the generated CSV.

After seeding, upload the printed CSV path via the Bank Reconciliation UI and
click "Auto-Match" to verify that the expected counts match the summary
printed at the end of this command.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone as dt_tz
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


_TAG = "DEMO-BR-"
_FIXTURE_SUBDIR = "demo_fixtures"
_FIXTURE_NAME = "bank_statement_demo.csv"


@dataclass(frozen=True)
class _Expected:
    """Expected auto-match outcome for the generated CSV."""

    total_lines: int
    matched_by_reference: int
    matched_by_amount_date: int
    unmatched: int

    @property
    def total_matched(self) -> int:
        return self.matched_by_reference + self.matched_by_amount_date


class Command(BaseCommand):
    help = "Seed demo TSA payments, revenues and a CSV statement to exercise bank reconciliation."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete prior DEMO-BR-* rows and regenerate the CSV.",
        )
        parser.add_argument(
            "--days-ago",
            type=int,
            default=7,
            help="Anchor date for the statement window (N days before today). Default: 7.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would happen without writing anything.",
        )

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def handle(self, *args, **options) -> None:
        days_ago: int = options["days_ago"]
        clear: bool = options["clear"]
        dry: bool = options["dry_run"]

        anchor = date.today() - timedelta(days=days_ago)
        self.stdout.write(
            self.style.NOTICE(
                f"Seeding bank reconciliation fixtures anchored at {anchor} "
                f"(clear={clear}, dry_run={dry})."
            )
        )

        if clear and not dry:
            self._clear()

        tsa = self._ensure_tsa(dry)
        ncoa = self._first_ncoa()
        revenue_head = self._first_revenue_head()

        if ncoa is None:
            raise CommandError(
                "No NCoACode rows found. Run `seed_demo_registers` first to seed NCoA segments."
            )

        payments = self._seed_payments(tsa, ncoa, anchor, dry)
        revenues = self._seed_revenues(tsa, ncoa, revenue_head, anchor, dry)

        csv_path, expected = self._write_csv(payments, revenues, anchor, dry)

        self._print_summary(csv_path, expected, tsa, anchor)

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------
    def _clear(self) -> None:
        from accounting.models import (
            PaymentInstruction,
            PaymentVoucherGov,
            RevenueCollection,
            TreasuryAccount,
        )

        pi_n = PaymentInstruction.objects.filter(batch_reference__startswith=_TAG).count()
        PaymentInstruction.objects.filter(batch_reference__startswith=_TAG).delete()

        pv_qs = PaymentVoucherGov.objects.filter(voucher_number__startswith=_TAG)
        pv_n = pv_qs.count()
        pv_qs.delete()

        rc_qs = RevenueCollection.objects.filter(receipt_number__startswith=_TAG)
        rc_n = rc_qs.count()
        rc_qs.delete()

        ta_qs = TreasuryAccount.objects.filter(account_number__startswith=_TAG)
        ta_n = ta_qs.count()
        ta_qs.delete()

        csv_path = self._csv_path()
        removed_csv = False
        if csv_path.exists():
            csv_path.unlink()
            removed_csv = True

        self.stdout.write(
            self.style.WARNING(
                f"  Cleared: {pi_n} PaymentInstruction, {pv_n} PaymentVoucher, "
                f"{rc_n} RevenueCollection, {ta_n} TreasuryAccount. "
                f"CSV removed: {removed_csv}."
            )
        )

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    def _ensure_tsa(self, dry: bool):
        from accounting.models import TreasuryAccount

        existing = (
            TreasuryAccount.objects.filter(is_active=True).order_by("account_number").first()
        )
        if existing:
            self.stdout.write(f"  Using existing TSA: {existing.account_number} ({existing.account_name}).")
            return existing

        if dry:
            self.stdout.write("  Would create a new TSA (dry-run).")
            return None

        tsa = TreasuryAccount.objects.create(
            account_number=f"{_TAG}TSA-001",
            account_name="Demo Bank Recon TSA",
            bank="CBN",
            account_type="MAIN_TSA",
            is_active=True,
            current_balance=Decimal("0"),
            description="Auto-created by seed_demo_bank_reconciliation.",
        )
        self.stdout.write(self.style.SUCCESS(f"  Created TSA {tsa.account_number}."))
        return tsa

    def _first_ncoa(self):
        from accounting.models import NCoACode

        return NCoACode.objects.filter(is_active=True).first() or NCoACode.objects.first()

    def _first_revenue_head(self):
        from accounting.models import RevenueHead

        return RevenueHead.objects.filter(is_active=True).first() or RevenueHead.objects.first()

    # ------------------------------------------------------------------
    # Payments — debit side of the bank statement
    # ------------------------------------------------------------------
    def _seed_payments(self, tsa, ncoa, anchor: date, dry: bool) -> list:
        """Create 4 processed payment instructions.

        Returns the list for CSV generation. Payments 1–2 will match by
        reference, payment 3 will match by amount+date (CSV reference blank),
        payment 4 will NOT appear in the CSV (unmatched payment → reconciling
        item on the ledger side).
        """
        from accounting.models import PaymentInstruction, PaymentVoucherGov

        specs = [
            # (suffix, amount, beneficiary, day_offset, bank_reference)
            ("PAY-001", Decimal("2_500_000.00"), "Alpha Construction Ltd", 0, f"{_TAG}REF-PAY-001"),
            ("PAY-002", Decimal("1_875_500.00"), "Beta Consulting Services", 1, f"{_TAG}REF-PAY-002"),
            ("PAY-003", Decimal("650_000.00"),  "Gamma Supplies Nigeria",  2, f"{_TAG}REF-PAY-003"),
            ("PAY-004", Decimal("980_000.00"),  "Delta Logistics Co",      3, f"{_TAG}REF-PAY-004"),
        ]

        results = []
        for suffix, amount, beneficiary, offset, bank_ref in specs:
            voucher_number = f"{_TAG}PV-{suffix}"
            batch_ref = f"{_TAG}BATCH-{suffix}"
            processed_at = datetime.combine(
                anchor + timedelta(days=offset),
                datetime.min.time(),
                tzinfo=dt_tz.utc,
            )

            if dry:
                results.append(
                    {
                        "amount": amount,
                        "beneficiary": beneficiary,
                        "date": processed_at.date(),
                        "bank_reference": bank_ref,
                    }
                )
                continue

            with transaction.atomic():
                pv, _ = PaymentVoucherGov.objects.update_or_create(
                    voucher_number=voucher_number,
                    defaults={
                        "payment_type": "VENDOR",
                        "ncoa_code": ncoa,
                        "payee_name": beneficiary,
                        "payee_account": "1234567890",
                        "payee_bank": "First Bank",
                        "gross_amount": amount,
                        "wht_amount": Decimal("0"),
                        "net_amount": amount,
                        "narration": f"Demo payment to {beneficiary}",
                        "tsa_account": tsa,
                        "status": "PAID",
                    },
                )
                pi, _ = PaymentInstruction.objects.update_or_create(
                    payment_voucher=pv,
                    defaults={
                        "tsa_account": tsa,
                        "beneficiary_name": beneficiary,
                        "beneficiary_account": "1234567890",
                        "beneficiary_bank": "First Bank",
                        "amount": amount,
                        "narration": f"Demo payment to {beneficiary}",
                        "batch_reference": batch_ref,
                        "bank_reference": bank_ref,
                        "processed_at": processed_at,
                        "status": "PROCESSED",
                    },
                )
            results.append(
                {
                    "amount": amount,
                    "beneficiary": beneficiary,
                    "date": processed_at.date(),
                    "bank_reference": bank_ref,
                }
            )

        self.stdout.write(f"  Payments seeded: {len(results)} (PROCESSED).")
        return results

    # ------------------------------------------------------------------
    # Revenue collections — credit side
    # ------------------------------------------------------------------
    def _seed_revenues(self, tsa, ncoa, head, anchor: date, dry: bool) -> list:
        """Create 3 posted revenue collections. First two match by reference,
        third matches by amount+date (blank CSV reference)."""
        from accounting.models import RevenueCollection

        if head is None:
            self.stdout.write(
                self.style.WARNING("  No RevenueHead available — skipping revenue seed.")
            )
            return []

        specs = [
            ("REV-001", Decimal("1_200_000.00"), "Demo Taxpayer A", 0, f"{_TAG}PAY-REV-001"),
            ("REV-002", Decimal("450_000.00"),  "Demo Taxpayer B", 1, f"{_TAG}PAY-REV-002"),
            ("REV-003", Decimal("320_000.00"),  "Demo Taxpayer C", 2, f"{_TAG}PAY-REV-003"),
        ]

        results = []
        for suffix, amount, payer, offset, pay_ref in specs:
            receipt_number = f"{_TAG}{suffix}"
            coll_date = anchor + timedelta(days=offset)

            if dry:
                results.append(
                    {
                        "amount": amount,
                        "payer": payer,
                        "date": coll_date,
                        "payment_reference": pay_ref,
                    }
                )
                continue

            RevenueCollection.objects.update_or_create(
                receipt_number=receipt_number,
                defaults={
                    "revenue_head": head,
                    "ncoa_code": ncoa,
                    "payer_name": payer,
                    "amount": amount,
                    "payment_reference": pay_ref,
                    "tsa_account": tsa,
                    "collection_date": coll_date,
                    "value_date": coll_date,
                    "collection_channel": "ONLINE",
                    "status": "POSTED",
                    "description": f"Demo revenue from {payer}",
                },
            )
            results.append(
                {
                    "amount": amount,
                    "payer": payer,
                    "date": coll_date,
                    "payment_reference": pay_ref,
                }
            )

        self.stdout.write(f"  Revenue collections seeded: {len(results)} (POSTED).")
        return results

    # ------------------------------------------------------------------
    # CSV fixture
    # ------------------------------------------------------------------
    def _csv_path(self) -> Path:
        media_root = Path(getattr(settings, "MEDIA_ROOT", "media"))
        return media_root / _FIXTURE_SUBDIR / _FIXTURE_NAME

    def _write_csv(
        self,
        payments: list,
        revenues: list,
        anchor: date,
        dry: bool,
    ) -> tuple[Path, _Expected]:
        path = self._csv_path()

        # Compose rows:
        #   3 payments get debit rows (2 with exact ref, 1 with blank ref)
        #   2 revenues get credit rows (both with exact ref)
        #   1 revenue gets a credit row with blank ref (amount+date match)
        #   2 unmatched rows: bank charge debit + stale lodgement credit
        rows: list[dict] = []

        # Strategy-1 matches (reference).
        if len(payments) >= 1:
            p = payments[0]
            rows.append(_row(p["date"], f"TRF TO {p['beneficiary'].upper()}", p["bank_reference"], debit=p["amount"]))
        if len(payments) >= 2:
            p = payments[1]
            rows.append(_row(p["date"], f"NEFT {p['beneficiary'].upper()}", p["bank_reference"], debit=p["amount"]))

        # Strategy-2 match (amount+date, blank ref).
        matched_by_amount_date = 0
        if len(payments) >= 3:
            p = payments[2]
            rows.append(_row(p["date"], f"CHEQUE {p['beneficiary'].upper()}", "", debit=p["amount"]))
            matched_by_amount_date += 1

        # Revenues by reference.
        if len(revenues) >= 1:
            r = revenues[0]
            rows.append(_row(r["date"], f"LODGEMENT {r['payer'].upper()}", r["payment_reference"], credit=r["amount"]))
        if len(revenues) >= 2:
            r = revenues[1]
            rows.append(_row(r["date"], f"REMITA CREDIT {r['payer'].upper()}", r["payment_reference"], credit=r["amount"]))

        # Revenue by amount+date (blank ref).
        if len(revenues) >= 3:
            r = revenues[2]
            rows.append(_row(r["date"], f"CASH DEPOSIT {r['payer'].upper()}", "", credit=r["amount"]))
            matched_by_amount_date += 1

        # Unmatched reconciling items.
        rows.append(_row(anchor + timedelta(days=1), "BANK MAINTENANCE CHARGE", "CHG-001", debit=Decimal("1_500.00")))
        rows.append(_row(anchor + timedelta(days=4), "UNIDENTIFIED LODGEMENT", "", credit=Decimal("75_000.00")))

        matched_by_reference = (min(len(payments), 2)) + (min(len(revenues), 2))
        expected = _Expected(
            total_lines=len(rows),
            matched_by_reference=matched_by_reference,
            matched_by_amount_date=matched_by_amount_date,
            unmatched=2,
        )

        if dry:
            self.stdout.write(f"  Would write {len(rows)} rows to {path} (dry-run).")
            return path, expected

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["date", "description", "reference", "debit", "credit", "balance"])
            running = Decimal("25_000_000.00")
            for r in rows:
                running = running + (r["credit"] or Decimal("0")) - (r["debit"] or Decimal("0"))
                writer.writerow(
                    [
                        r["date"].isoformat(),
                        r["description"],
                        r["reference"],
                        f"{r['debit']:.2f}" if r["debit"] else "",
                        f"{r['credit']:.2f}" if r["credit"] else "",
                        f"{running:.2f}",
                    ]
                )

        self.stdout.write(self.style.SUCCESS(f"  CSV written: {path}"))
        return path, expected

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def _print_summary(self, csv_path: Path, expected: _Expected, tsa, anchor: date) -> None:
        tsa_line = f"{tsa.account_number} — {tsa.account_name}" if tsa else "(dry-run, no TSA)"
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Bank reconciliation seed complete."))
        self.stdout.write(f"  TSA               : {tsa_line}")
        self.stdout.write(f"  Statement window  : {anchor} → {anchor + timedelta(days=4)}")
        self.stdout.write(f"  CSV fixture       : {csv_path}")
        self.stdout.write("")
        self.stdout.write("Expected auto-match outcome:")
        self.stdout.write(f"  total_lines         = {expected.total_lines}")
        self.stdout.write(f"  matched (reference) = {expected.matched_by_reference}")
        self.stdout.write(f"  matched (amount)    = {expected.matched_by_amount_date}")
        self.stdout.write(f"  unmatched           = {expected.unmatched}")
        self.stdout.write("")
        self.stdout.write("Next step — in the Bank Reconciliation UI:")
        self.stdout.write("  1. Enter the TSA account id above")
        self.stdout.write(f"  2. Upload {csv_path.name}")
        self.stdout.write("  3. Click 'Auto-Match' and verify the counts above")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _row(
    d: date,
    description: str,
    reference: str,
    debit: Decimal | None = None,
    credit: Decimal | None = None,
) -> dict:
    return {
        "date": d,
        "description": description,
        "reference": reference,
        "debit": debit or Decimal("0"),
        "credit": credit or Decimal("0"),
    }
