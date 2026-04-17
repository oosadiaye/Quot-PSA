"""
Seed PaymentVoucherGov + PaymentInstruction rows so the IPSAS 2 Cash
Flow Statement shows non-zero outflows for the direct-method report.

Inflows already come from RevenueCollection (seeded by
``seed_demo_registers``). This command adds the matching outflow side
so the cash flow statement reconciles.

Outflows per month (NGN, all PROCESSED so they land in the report):
  * Personnel payroll      — NCoA 21100100
  * Vendor O&M             — NCoA 22100100
  * Capex disbursement     — NCoA 23100100
  * Debt service           — NCoA 24100100
  * Subvention transfers   — NCoA 25100100

Idempotent via ``voucher_number`` prefix ``DEMO-CF-``.
"""
from __future__ import annotations

import random
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand


_TAG = 'DEMO-CF-'

OUTFLOW_SPECS = [
    ('21100100', 'SALARY',     'Payroll disbursement',    Decimal('2800000')),
    ('22100100', 'VENDOR',     'Vendor O&M settlement',   Decimal('1200000')),
    ('23100100', 'VENDOR',     'Capital project payment', Decimal('850000')),
    ('24100100', 'DEBT',       'Debt service interest',   Decimal('420000')),
    ('25100100', 'SUBVENTION', 'Parastatal subvention',   Decimal('680000')),
]


class Command(BaseCommand):
    help = 'Seed PV + PaymentInstruction rows so IPSAS 2 cash flow reports non-zero outflows.'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, default=None)
        parser.add_argument('--clear', action='store_true')

    def handle(self, *args, **options):
        from django.db import transaction
        from django.utils import timezone
        from accounting.models import (
            PaymentVoucherGov, PaymentInstruction, TreasuryAccount, NCoACode,
            AdministrativeSegment, FunctionalSegment, ProgrammeSegment,
            FundSegment, GeographicSegment, EconomicSegment,
        )

        year: int = options['year'] or date.today().year
        clear: bool = options['clear']

        if clear:
            # Delete PIs first (FK PROTECT back to PV).
            pi_count = PaymentInstruction.objects.filter(
                payment_voucher__voucher_number__startswith=_TAG,
            ).count()
            PaymentInstruction.objects.filter(
                payment_voucher__voucher_number__startswith=_TAG,
            ).delete()
            pv_count = PaymentVoucherGov.objects.filter(
                voucher_number__startswith=_TAG,
            ).count()
            PaymentVoucherGov.objects.filter(
                voucher_number__startswith=_TAG,
            ).delete()
            self.stdout.write(self.style.WARNING(
                f'Cleared {pi_count} PIs, {pv_count} PVs.'
            ))

        tsa = TreasuryAccount.objects.filter(is_active=True).first()
        admin = AdministrativeSegment.objects.filter(is_active=True).first()
        func = FunctionalSegment.objects.filter(is_active=True).first()
        prog = ProgrammeSegment.objects.filter(is_active=True).first()
        fund = FundSegment.objects.filter(is_active=True).first()
        geo = GeographicSegment.objects.filter(is_active=True).first()

        if not all([tsa, admin, func, prog, fund, geo]):
            self.stdout.write(self.style.WARNING(
                'Missing NCoA segments / TSA — run seed_ncoa + seed_demo_registers first.'
            ))
            return

        rng = random.Random(f'{year}-cf')
        created = 0

        for month in range(1, 13):
            posting_date = date(year, month, 1)
            for idx, (econ_code, pay_type, narration, base) in enumerate(OUTFLOW_SPECS, start=1):
                ref = f'{_TAG}{year}-{month:02d}-{idx:02d}'

                if PaymentVoucherGov.objects.filter(voucher_number=ref).exists():
                    continue

                econ = EconomicSegment.objects.filter(code=econ_code).first()
                if econ is None:
                    continue

                ncoa, _ = NCoACode.objects.get_or_create(
                    administrative=admin, economic=econ, functional=func,
                    programme=prog, fund=fund, geographic=geo,
                    defaults={'is_active': True, 'description': 'Demo CF seed'},
                )

                factor = Decimal(str(1.0 + (rng.random() - 0.5) * 0.3))
                amount = (base * factor).quantize(Decimal('0.01'))

                with transaction.atomic():
                    pv = PaymentVoucherGov.objects.create(
                        voucher_number=ref,
                        payment_type=pay_type,
                        ncoa_code=ncoa,
                        payee_name=f'Demo Payee {econ_code}',
                        payee_account=f'1000{idx:06d}',
                        payee_bank='CBN',
                        gross_amount=amount,
                        wht_amount=Decimal('0'),
                        net_amount=amount,
                        narration=narration,
                        tsa_account=tsa,
                        status='PAID',
                    )
                    PaymentInstruction.objects.create(
                        payment_voucher=pv,
                        tsa_account=tsa,
                        beneficiary_name=pv.payee_name,
                        beneficiary_account=pv.payee_account,
                        beneficiary_bank=pv.payee_bank,
                        amount=amount,
                        narration=narration,
                        batch_reference=f'{_TAG}BATCH-{year}-{month:02d}',
                        status='PROCESSED',
                        processed_at=timezone.now(),
                    )
                    created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Cash-flow seed complete — {created} PV+PI pairs for FY {year}.'
        ))
