"""Give every existing Cash / Petty Cash / Imprest account its cash journal (new accounts get one on save)."""
from django.core.management.base import BaseCommand

from accounting.models import BankAccount
from accounting.models.cash_posting import CASH_ACCOUNT_TYPES
from accounting.services.cash_journal_sync import ensure_cash_journal


class Command(BaseCommand):
    help = 'Create the cash journal of every cash account that has none.'

    def handle(self, *args, **options):
        made = 0
        for account in BankAccount.objects.filter(account_type__in=CASH_ACCOUNT_TYPES):
            before = hasattr(account, 'cash_journal')
            ensure_cash_journal(account)
            made += 0 if before else 1
        self.stdout.write(self.style.SUCCESS(f'{made} cash journal(s) created.'))
