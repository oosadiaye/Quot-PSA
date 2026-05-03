"""
Post a Jan-1 opening-balance journal so the Statement of Financial
Position shows non-zero Net Assets from fiscal-year start.

The entry books:

    DR  Cash in TSA (resolved via tsa_gl_resolver)  NGN  n
    CR  Accumulated Fund (43100100 by default)    NGN  n

This mirrors what a real state government does at go-live — the
consolidated revenue fund opens with an opening balance carried
forward from the prior year. Without this, the seeded tenants show
Net Assets = 0 until the period-close runs, which is technically
correct but confusing for demos.

Idempotent: reference ``OPENING-BAL:YYYY`` is checked; re-running is
safe.

Usage
-----
    python manage.py tenant_command seed_opening_balance --schema=<name>
    python manage.py tenant_command seed_opening_balance --schema=<name> --year=2026 --amount=50000000
    python manage.py tenant_command seed_opening_balance --schema=<name> --clear
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Post a FY-start opening-balance journal (DR Cash / CR Accumulated Fund).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year', type=int, default=None,
            help='Fiscal year (defaults to current).',
        )
        parser.add_argument(
            '--amount', type=str, default='50000000',
            help='Opening balance amount in NGN (default 50 M).',
        )
        parser.add_argument(
            '--clear', action='store_true',
            help='Delete the existing opening balance journal first.',
        )

    def handle(self, *args, **options):
        from django.db import transaction
        from django.db.models import F
        from django.utils import timezone
        from accounting.models import (
            Account, AccountingSettings, JournalHeader, JournalLine,
            GLBalance,
        )

        year: int = options['year'] or date.today().year
        amount = Decimal(str(options['amount']))
        clear: bool = options['clear']

        reference = f'OPENING-BAL:{year}'

        existing = JournalHeader.objects.filter(reference_number=reference)
        if clear and existing.exists():
            # Rewind GLBalance contributions before deleting.
            for h in existing.prefetch_related('lines'):
                for line in h.lines.all():
                    _rewind_balance(
                        GLBalance, line.account, year, 1,
                        -(line.debit or Decimal('0')),
                        -(line.credit or Decimal('0')),
                    )
            deleted, _ = existing.delete()
            self.stdout.write(self.style.WARNING(
                f'Cleared {deleted} prior opening-balance rows.'
            ))
        elif existing.exists():
            self.stdout.write(self.style.NOTICE(
                f'Opening balance for FY {year} already posted '
                f'({existing.first().reference_number}). Use --clear to reset.'
            ))
            return

        # Resolve accounts. Cash GL goes through the same resolver as the
        # live posting paths (TSA gl_cash_account → settings default →
        # 31* asset prefix scan) so the seed and the runtime never disagree.
        from accounting.services.tsa_gl_resolver import resolve_tsa_cash_gl
        settings_obj = AccountingSettings.objects.first()
        af_code = _resolve(
            settings_obj, 'accumulated_fund_account_code', '43100100',
        )

        try:
            cash = resolve_tsa_cash_gl(tsa_account=None)
        except Exception as exc:
            raise CommandError(f'Cannot resolve TSA cash GL: {exc}')

        af = Account.objects.filter(code=af_code, is_active=True).first()
        if af is None:
            raise CommandError(
                f'Accumulated-fund account {af_code!r} not found. '
                'Configure AccountingSettings.accumulated_fund_account_code '
                'or add the account to the COA.'
            )

        with transaction.atomic():
            header = JournalHeader.objects.create(
                posting_date=date(year, 1, 1),
                description=(
                    f'Opening balance — FY {year}. '
                    f'NGN {amount:,.2f} brought forward from prior year.'
                ),
                reference_number=reference,
                status='Posted',
                posted_at=timezone.now(),
                source_module='opening_balance',
            )
            JournalLine.objects.bulk_create([
                JournalLine(
                    header=header, account=cash,
                    debit=amount, credit=Decimal('0'),
                    memo=f'Opening cash balance FY {year}',
                ),
                JournalLine(
                    header=header, account=af,
                    debit=Decimal('0'), credit=amount,
                    memo=f'Opening Accumulated Fund FY {year}',
                ),
            ])
            _post_balance(GLBalance, cash, year, 1, amount, Decimal('0'))
            _post_balance(GLBalance, af,   year, 1, Decimal('0'), amount)

        self.stdout.write(self.style.SUCCESS(
            f'Opening balance posted — FY {year}, NGN {amount:,.2f}. '
            f'Cash {cash.code} +DR, Accumulated Fund {af.code} +CR.'
        ))


def _resolve(settings_obj, attr: str, default: str) -> str:
    if settings_obj is None:
        return default
    val = getattr(settings_obj, attr, None)
    if val is None:
        return default
    s = str(val).strip()
    return s or default


def _post_balance(GLBalance, account, year, period, debit, credit):
    from django.db.models import F
    bal, _ = GLBalance.objects.get_or_create(
        account=account, fund=None, function=None, program=None,
        geo=None, mda=None, fiscal_year=year, period=period,
        defaults={'debit_balance': 0, 'credit_balance': 0},
    )
    GLBalance.objects.filter(pk=bal.pk).update(
        debit_balance=F('debit_balance') + debit,
        credit_balance=F('credit_balance') + credit,
    )


def _rewind_balance(GLBalance, account, year, period, debit_delta, credit_delta):
    _post_balance(GLBalance, account, year, period, debit_delta, credit_delta)
