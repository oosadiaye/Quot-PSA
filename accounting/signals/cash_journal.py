"""Every Cash / Petty Cash / Imprest account in Bank & Cash has its cash journal, created and kept in step on save."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounting.models import BankAccount
from accounting.services.cash_journal_sync import ensure_cash_journal


@receiver(post_save, sender=BankAccount, dispatch_uid='cash_journal_follows_bank_account')
def sync_cash_journal(sender, instance, raw=False, **kwargs):
    if raw:                       # loaddata: the journal rows come in the fixture too
        return
    ensure_cash_journal(instance)
