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


@pytest.mark.integration
class TestEligiblePayments:

    def test_includes_posted_payment_on_that_account(
            self, db, bank_account_for_batch, make_posted_payment):
        from accounting.services.payment_batch import PaymentBatchService
        p = make_posted_payment()
        ids = list(PaymentBatchService.eligible_payments(
            bank_account_for_batch).values_list('id', flat=True))
        assert p.id in ids

    def test_excludes_draft_payment(
            self, db, bank_account_for_batch, make_posted_payment):
        from accounting.services.payment_batch import PaymentBatchService
        p = make_posted_payment(status='Draft')
        ids = list(PaymentBatchService.eligible_payments(
            bank_account_for_batch).values_list('id', flat=True))
        assert p.id not in ids

    def test_excludes_payment_on_a_different_bank_account(
            self, db, bank_account_for_batch, make_posted_payment, cash_account):
        from accounting.models import BankAccount
        from accounting.services.payment_batch import PaymentBatchService
        other = BankAccount.objects.create(
            name='Other', account_number='0200000002', account_type='Bank',
            gl_account=cash_account, bank_name='Other Bank', is_active=True,
            currency=None)
        p = make_posted_payment(bank_account=other)
        ids = list(PaymentBatchService.eligible_payments(
            bank_account_for_batch).values_list('id', flat=True))
        assert p.id not in ids


@pytest.mark.integration
class TestAddPaymentsValidation:

    def test_rejects_payment_with_blank_payee_bank(
            self, db, bank_account_for_batch, make_posted_payment, vendor_without_bank):
        from django.core.exceptions import ValidationError
        from accounting.services.payment_batch import PaymentBatchService
        p = make_posted_payment(vendor=vendor_without_bank)
        with pytest.raises(ValidationError) as exc:
            PaymentBatchService.create_batch(
                bank_account=bank_account_for_batch, batch_date=None,
                payment_ids=[p.id], user=None)
        # the error must name the vendor so the operator knows what to fix
        assert 'NoBank Ltd' in str(exc.value)

    def test_rejects_draft_payment(
            self, db, bank_account_for_batch, make_posted_payment):
        from django.core.exceptions import ValidationError
        from accounting.services.payment_batch import PaymentBatchService
        p = make_posted_payment(status='Draft')
        with pytest.raises(ValidationError):
            PaymentBatchService.create_batch(
                bank_account=bank_account_for_batch, batch_date=None,
                payment_ids=[p.id], user=None)

    def test_rejects_payment_on_a_different_bank_account(
            self, db, bank_account_for_batch, make_posted_payment, cash_account):
        from django.core.exceptions import ValidationError
        from accounting.models import BankAccount
        from accounting.services.payment_batch import PaymentBatchService
        other = BankAccount.objects.create(
            name='Other', account_number='0200000003', account_type='Bank',
            gl_account=cash_account, bank_name='Other Bank', is_active=True,
            currency=None)
        p = make_posted_payment(bank_account=other)
        with pytest.raises(ValidationError):
            PaymentBatchService.create_batch(
                bank_account=bank_account_for_batch, batch_date=None,
                payment_ids=[p.id], user=None)

    def test_rejects_payment_already_in_an_active_batch(
            self, db, bank_account_for_batch, make_posted_payment):
        from django.core.exceptions import ValidationError
        from accounting.services.payment_batch import PaymentBatchService
        p = make_posted_payment()
        PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch, batch_date=None,
            payment_ids=[p.id], user=None)
        with pytest.raises(ValidationError):
            PaymentBatchService.create_batch(
                bank_account=bank_account_for_batch, batch_date=None,
                payment_ids=[p.id], user=None)

    def test_batch_number_increments(
            self, db, bank_account_for_batch, make_posted_payment):
        from accounting.services.payment_batch import PaymentBatchService
        a = PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch, batch_date=None,
            payment_ids=[make_posted_payment().id], user=None)
        b = PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch, batch_date=None,
            payment_ids=[make_posted_payment().id], user=None)
        assert a.batch_number != b.batch_number
        assert int(b.batch_number.rsplit('/', 1)[1]) == \
            int(a.batch_number.rsplit('/', 1)[1]) + 1

    def test_snapshot_is_written_onto_the_line(
            self, db, bank_account_for_batch, make_posted_payment):
        from accounting.services.payment_batch import PaymentBatchService
        batch = PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch, batch_date=None,
            payment_ids=[make_posted_payment().id], user=None)
        line = batch.lines.first()
        assert line.payee_name == 'ACME Ltd'
        assert line.payee_bank == 'Zenith Bank'
        assert line.payee_account == '0123456789'
        assert line.sequence == 1


@pytest.mark.integration
class TestBatchTransitions:

    def _batch(self, bank_account, make_posted_payment):
        from accounting.services.payment_batch import PaymentBatchService
        p = make_posted_payment()
        return PaymentBatchService.create_batch(
            bank_account=bank_account, batch_date=None,
            payment_ids=[p.id], user=None), p

    def test_dispatch_moves_draft_to_dispatched(
            self, db, bank_account_for_batch, make_posted_payment):
        from accounting.services.payment_batch import PaymentBatchService
        batch, _ = self._batch(bank_account_for_batch, make_posted_payment)
        PaymentBatchService.dispatch(batch, user=None)
        batch.refresh_from_db()
        assert batch.status == 'Dispatched'
        assert batch.dispatched_at is not None

    def test_cannot_add_lines_once_dispatched(
            self, db, bank_account_for_batch, make_posted_payment):
        from django.core.exceptions import ValidationError
        from accounting.services.payment_batch import PaymentBatchService
        batch, _ = self._batch(bank_account_for_batch, make_posted_payment)
        PaymentBatchService.dispatch(batch, user=None)
        other = make_posted_payment()
        with pytest.raises(ValidationError):
            PaymentBatchService.add_payments(batch, [other.id], user=None)

    def test_confirmed_is_terminal(
            self, db, bank_account_for_batch, make_posted_payment):
        from django.core.exceptions import ValidationError
        from accounting.services.payment_batch import PaymentBatchService
        batch, _ = self._batch(bank_account_for_batch, make_posted_payment)
        PaymentBatchService.dispatch(batch, user=None)
        PaymentBatchService.confirm(batch, user=None)
        with pytest.raises(ValidationError):
            PaymentBatchService.cancel(batch, user=None, reason='nope')

    def test_cannot_confirm_a_draft(
            self, db, bank_account_for_batch, make_posted_payment):
        from django.core.exceptions import ValidationError
        from accounting.services.payment_batch import PaymentBatchService
        batch, _ = self._batch(bank_account_for_batch, make_posted_payment)
        with pytest.raises(ValidationError):
            PaymentBatchService.confirm(batch, user=None)

    def test_cancel_releases_payments_back_to_eligible(
            self, db, bank_account_for_batch, make_posted_payment):
        from accounting.services.payment_batch import PaymentBatchService
        batch, p = self._batch(bank_account_for_batch, make_posted_payment)
        assert p.id not in list(PaymentBatchService.eligible_payments(
            bank_account_for_batch).values_list('id', flat=True))
        PaymentBatchService.cancel(batch, user=None, reason='keyed in error')
        assert p.id in list(PaymentBatchService.eligible_payments(
            bank_account_for_batch).values_list('id', flat=True))

    def test_snapshot_survives_vendor_edit(
            self, db, bank_account_for_batch, make_posted_payment, batch_vendor):
        """A signed letter must reprint what was signed, not what the
        vendor record says today."""
        batch, _ = self._batch(bank_account_for_batch, make_posted_payment)
        batch_vendor.bank_account_number = '5555555555'
        batch_vendor.bank_name = 'Changed Bank'
        batch_vendor.save()
        line = batch.lines.first()
        line.refresh_from_db()
        assert line.payee_account == '0123456789'
        assert line.payee_bank == 'Zenith Bank'

    def test_remove_line_renumbers_remaining(
            self, db, bank_account_for_batch, make_posted_payment):
        """The printed S/N column must stay 1..N with no gaps."""
        from accounting.services.payment_batch import PaymentBatchService
        ids = [make_posted_payment().id for _ in range(3)]
        batch = PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch, batch_date=None,
            payment_ids=ids, user=None)
        first_line = batch.lines.order_by('sequence').first()
        PaymentBatchService.remove_line(batch, first_line.id, user=None)
        sequences = list(batch.lines.order_by('sequence')
                         .values_list('sequence', flat=True))
        assert sequences == [1, 2]

    def test_dispatch_rejects_empty_batch(
            self, db, bank_account_for_batch, make_posted_payment):
        from django.core.exceptions import ValidationError
        from accounting.services.payment_batch import PaymentBatchService
        batch, _ = self._batch(bank_account_for_batch, make_posted_payment)
        line = batch.lines.first()
        PaymentBatchService.remove_line(batch, line.id, user=None)
        with pytest.raises(ValidationError):
            PaymentBatchService.dispatch(batch, user=None)


@pytest.mark.integration
class TestLineOrdering:

    def test_sn_follows_the_order_the_operator_supplied(
            self, db, bank_account_for_batch, make_posted_payment):
        """The letter is a signed document. If the operator picks payments
        in a deliberate order, the S/N column must reflect it — a
        pk__in filter returns rows in arbitrary order, so this is not
        automatic.
        """
        from accounting.services.payment_batch import PaymentBatchService
        payments = [make_posted_payment() for _ in range(4)]
        # Deliberately NOT ascending-pk order.
        chosen = [payments[2].id, payments[0].id, payments[3].id, payments[1].id]
        batch = PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch, batch_date=None,
            payment_ids=chosen, user=None)
        by_sequence = list(batch.lines.order_by('sequence')
                           .values_list('payment_id', flat=True))
        assert by_sequence == chosen

    def test_added_lines_continue_the_sequence(
            self, db, bank_account_for_batch, make_posted_payment):
        from accounting.services.payment_batch import PaymentBatchService
        first = make_posted_payment()
        batch = PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch, batch_date=None,
            payment_ids=[first.id], user=None)
        second = make_posted_payment()
        third = make_posted_payment()
        PaymentBatchService.add_payments(batch, [third.id, second.id], user=None)
        by_sequence = list(batch.lines.order_by('sequence')
                           .values_list('payment_id', flat=True))
        assert by_sequence == [first.id, third.id, second.id]
