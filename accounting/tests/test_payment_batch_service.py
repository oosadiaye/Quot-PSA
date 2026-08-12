"""Payment batching — DB integration tests."""
from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.mark.integration
class TestBankLetterSettingsSingleton:

    def test_get_singleton_creates_row_with_defaults(self, db):
        from accounting.models import BankLetterSettings
        s = BankLetterSettings.get_singleton()
        assert s.pk == 1
        assert s.ministry_name == 'Ministry of Finance'
        assert s.office_name == 'Office of the Accountant General'

    def test_get_singleton_is_idempotent(self, db):
        from accounting.models import BankLetterSettings
        a = BankLetterSettings.get_singleton()
        a.office_address = 'Asaba'
        a.save()
        b = BankLetterSettings.get_singleton()
        assert b.pk == a.pk
        assert b.office_address == 'Asaba'
        assert BankLetterSettings.objects.count() == 1


@pytest.mark.integration
class TestPaymentBatchModel:

    def test_total_amount_sums_active_lines(self, db, bank_account_for_batch):
        from accounting.models import PaymentBatch, PaymentBatchLine
        batch = PaymentBatch.objects.create(
            batch_number='PB/2026/0001',
            source_bank_account=bank_account_for_batch,
            addressee_bank_name='Premium Trust Bank',
            addressee_account_no='0100070001',
        )
        for i, amt in enumerate(['100.00', '250.50'], start=1):
            PaymentBatchLine.objects.create(
                batch=batch, payment=None, sequence=i,
                payee_name=f'Vendor {i}', payee_bank='First Bank',
                payee_account='0123456789', purpose='Supplies',
                amount=Decimal(amt),
            )
        assert batch.total_amount == Decimal('350.50')

    def test_total_amount_excludes_inactive_lines(self, db, bank_account_for_batch):
        from accounting.models import PaymentBatch, PaymentBatchLine
        batch = PaymentBatch.objects.create(
            batch_number='PB/2026/0002',
            source_bank_account=bank_account_for_batch,
            addressee_bank_name='Premium Trust Bank',
            addressee_account_no='0100070001',
        )
        PaymentBatchLine.objects.create(
            batch=batch, payment=None, sequence=1, payee_name='A',
            payee_bank='B', payee_account='0123456789', purpose='X',
            amount=Decimal('100.00'), is_active_membership=False,
        )
        assert batch.total_amount == Decimal('0')

    def test_active_membership_is_unique_per_payment(
            self, db, bank_account_for_batch, make_posted_payment):
        """The double-payment guard: one payment cannot sit in two live
        batches, or the bank is instructed twice."""
        from django.db.utils import IntegrityError
        from accounting.models import PaymentBatch, PaymentBatchLine
        payment = make_posted_payment()
        first = PaymentBatch.objects.create(
            batch_number='PB/2026/0003',
            source_bank_account=bank_account_for_batch,
            addressee_bank_name='Premium Trust Bank',
            addressee_account_no='0100070001',
        )
        second = PaymentBatch.objects.create(
            batch_number='PB/2026/0004',
            source_bank_account=bank_account_for_batch,
            addressee_bank_name='Premium Trust Bank',
            addressee_account_no='0100070001',
        )
        common = dict(
            payment=payment, sequence=1, payee_name='ACME Ltd',
            payee_bank='Zenith Bank', payee_account='0123456789',
            purpose='Supplies', amount=Decimal('100.00'),
        )
        PaymentBatchLine.objects.create(batch=first, **common)
        with pytest.raises(IntegrityError):
            PaymentBatchLine.objects.create(batch=second, **common)

    def test_inactive_membership_frees_the_payment(
            self, db, bank_account_for_batch, make_posted_payment):
        """Cancelling a batch must release its payments for re-batching."""
        from accounting.models import PaymentBatch, PaymentBatchLine
        payment = make_posted_payment()
        first = PaymentBatch.objects.create(
            batch_number='PB/2026/0005',
            source_bank_account=bank_account_for_batch,
            addressee_bank_name='Premium Trust Bank',
            addressee_account_no='0100070001',
        )
        second = PaymentBatch.objects.create(
            batch_number='PB/2026/0006',
            source_bank_account=bank_account_for_batch,
            addressee_bank_name='Premium Trust Bank',
            addressee_account_no='0100070001',
        )
        common = dict(
            payment=payment, sequence=1, payee_name='ACME Ltd',
            payee_bank='Zenith Bank', payee_account='0123456789',
            purpose='Supplies', amount=Decimal('100.00'),
        )
        line = PaymentBatchLine.objects.create(batch=first, **common)
        line.is_active_membership = False
        line.save(update_fields=['is_active_membership'])
        # No IntegrityError — the partial index only covers active rows.
        PaymentBatchLine.objects.create(batch=second, **common)
