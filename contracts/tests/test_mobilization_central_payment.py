"""Mobilisation on the central payment pipeline.

Issuing a mobilisation advance now auto-creates a DRAFT *advance* PV
(payment_type=ADVANCE, special_gl='A', vendor set) so it rides the same
PV → approve → draft Payment → post pipeline as every other outgoing
payment. Cash leaves only when that Payment is posted, which calls
``MobilizationService.record_disbursement`` to bump
``ContractBalance.mobilization_paid`` and flip the advance → PAID.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from contracts.models import MobilizationPaymentStatus
from contracts.services.mobilization_service import MobilizationService

# Reuse the accounting warrant toggle so issue_advance's warrant gate
# doesn't fail closed in the test schema.
from accounting.tests.test_central_payment_processing import _disable_warrant


@pytest.fixture
def active_tsa(tsa_account):
    """The PV factory picks the first ``is_active`` TSA — guarantee one."""
    if not tsa_account.is_active:
        tsa_account.is_active = True
        tsa_account.save(update_fields=['is_active'])
    return tsa_account


@pytest.mark.django_db
class TestMobilizationAutoPV:

    def test_issue_advance_creates_linked_advance_pv(
        self, activated_contract, drafter, active_tsa,
    ):
        _disable_warrant()
        mob = MobilizationService.issue_advance(
            contract=activated_contract, actor=drafter,
        )
        # Tracking record created at the mobilisation amount (15% of ₦100M).
        assert mob.amount == Decimal('15000000.00')
        assert mob.status == MobilizationPaymentStatus.PENDING

        # …and a DRAFT advance PV auto-created + linked.
        pv = mob.payment_voucher
        assert pv is not None
        assert pv.payment_type == 'ADVANCE'
        assert pv.special_gl_indicator == 'A'
        assert pv.vendor_id == activated_contract.vendor_id
        assert pv.gross_amount == Decimal('15000000.00')
        assert pv.status == 'DRAFT'

    def test_issued_pv_is_recognised_as_advance_by_central_helper(
        self, activated_contract, drafter, active_tsa,
    ):
        """The whole point of tagging ADVANCE/'A'/vendor: the central
        provisioning helper must build an is_advance Payment with NO
        invoice allocation."""
        from django.db import transaction
        from accounting.services.pv_payment_provisioning import (
            ensure_draft_payment_for_pv,
        )
        _disable_warrant()
        mob = MobilizationService.issue_advance(
            contract=activated_contract, actor=drafter,
        )
        with transaction.atomic():
            payment = ensure_draft_payment_for_pv(mob.payment_voucher)
        assert payment.is_advance is True
        assert payment.advance_type == 'Supplier Advance'
        assert payment.allocations.count() == 0
        assert payment.total_amount == Decimal('15000000.00')


@pytest.mark.django_db
class TestRecordDisbursement:

    def test_bumps_balance_and_flips_status(
        self, activated_contract, drafter, activator, active_tsa,
    ):
        _disable_warrant()
        mob = MobilizationService.issue_advance(
            contract=activated_contract, actor=drafter,
        )
        from contracts.models import ContractBalance
        before = ContractBalance.objects.get(pk=activated_contract.pk)
        assert before.mobilization_paid == Decimal('0.00')

        result = MobilizationService.record_disbursement(
            pv=mob.payment_voucher, payment_date=date(2026, 3, 1), actor=activator,
        )
        assert result is not None

        after = ContractBalance.objects.get(pk=activated_contract.pk)
        assert after.mobilization_paid == Decimal('15000000.00')
        mob.refresh_from_db()
        assert mob.status == MobilizationPaymentStatus.PAID

    def test_idempotent_no_double_bump(
        self, activated_contract, drafter, activator, active_tsa,
    ):
        _disable_warrant()
        mob = MobilizationService.issue_advance(
            contract=activated_contract, actor=drafter,
        )
        pv = mob.payment_voucher
        MobilizationService.record_disbursement(
            pv=pv, payment_date=date(2026, 3, 1), actor=activator,
        )
        # Second call must NOT bump the balance again.
        MobilizationService.record_disbursement(
            pv=pv, payment_date=date(2026, 3, 2), actor=activator,
        )
        from contracts.models import ContractBalance
        bal = ContractBalance.objects.get(pk=activated_contract.pk)
        assert bal.mobilization_paid == Decimal('15000000.00')

    def test_noop_for_non_mobilisation_pv(
        self, activated_contract, drafter, tsa_account,
    ):
        """A PV with no MobilizationPayment behind it is a no-op — safe to
        call for any advance payment."""
        from accounting.models.treasury import PaymentVoucherGov
        pv = PaymentVoucherGov.objects.create(
            voucher_number='PV-NOTMOB-0001',
            payment_type='ADVANCE', special_gl_indicator='A',
            ncoa_code=activated_contract.ncoa_code,
            payee_name='Someone', gross_amount=Decimal('1000.00'),
            net_amount=Decimal('1000.00'), narration='x',
            tsa_account=tsa_account, status='DRAFT',
        )
        result = MobilizationService.record_disbursement(
            pv=pv, payment_date=date(2026, 3, 1), actor=drafter,
        )
        assert result is None
