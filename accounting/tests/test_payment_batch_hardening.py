"""Payment batching — controls at the HTTP and service boundary.

The original suite tested the service thoroughly and the API thinly, which
is exactly where the defects were: ``ModelViewSet`` silently contributed
PATCH and DELETE verbs that the four-state machine never authored, so a
Confirmed batch could be deleted and its payments re-batched and re-sent.

Every test here pins one control that a review found missing.
"""
from __future__ import annotations

from decimal import Decimal

import pytest


# ─────────────────────────────────────────────────────────────────────
# Amount source — the letter instructs what the payment actually moves
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestLineAmountComesFromThePayment:
    """``Payment.payment_voucher`` is a plain FK with no uniqueness."""

    def test_two_payments_on_one_pv_each_carry_their_own_amount(
        self, db, bank_account_for_batch, make_posted_payment, maker_user,
    ):
        """The failure this prevents: both lines billed the full PV net.

        A PV of 900 settled by two payments of 400 and 500 must produce
        lines of 400 and 500 — total 900. Sourcing from ``pv.net_amount``
        produced 900 and 900, instructing the bank to pay 1800.
        """
        from accounting.services.payment_batch import PaymentBatchService

        first = make_posted_payment(amount='400.00')
        second = make_posted_payment(amount='500.00')

        batch = PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch,
            batch_date=None,
            payment_ids=[first.pk, second.pk],
            user=maker_user,
        )

        amounts = sorted(line.amount for line in batch.lines.all())
        assert amounts == [Decimal('400.00'), Decimal('500.00')]
        assert batch.total_amount == Decimal('900.00')

    def test_partial_settlement_does_not_over_instruct(
        self, db, bank_account_for_batch, make_posted_payment, maker_user,
    ):
        from accounting.services.payment_batch import PaymentBatchService

        partial = make_posted_payment(amount='250.00')
        batch = PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch, batch_date=None,
            payment_ids=[partial.pk], user=maker_user,
        )
        assert batch.lines.get().amount == Decimal('250.00')


# ─────────────────────────────────────────────────────────────────────
# Voucher authority ceiling
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def gov_voucher(db):
    """A minimal PaymentVoucherGov authorising 600.00 net.

    Built inline rather than imported from contracts' conftest: the six
    NCoA segments are the only heavyweight part and each is a
    ``get_or_create`` on a fixed code, so the cost is one-time per schema.
    """
    from accounting.models import (
        AdministrativeSegment, EconomicSegment, FunctionalSegment,
        ProgrammeSegment, FundSegment, GeographicSegment, NCoACode,
        PaymentVoucherGov, TreasuryAccount,
    )

    admin, _ = AdministrativeSegment.objects.get_or_create(
        code='050101000000',
        defaults={'name': 'Ministry of Works', 'level': 'ORGANIZATION',
                  'sector_code': '05', 'organization_code': '01',
                  'is_mda': True, 'mda_type': 'MINISTRY', 'is_active': True})
    econ, _ = EconomicSegment.objects.get_or_create(
        code='22010101',
        defaults={'name': 'Construction Expenditure', 'account_type_code': '2',
                  'is_posting_level': True, 'normal_balance': 'DEBIT',
                  'is_active': True})
    func, _ = FunctionalSegment.objects.get_or_create(
        code='70111',
        defaults={'name': 'Executive and Legislative Organs',
                  'division_code': '701', 'group_code': '1',
                  'class_code': '1', 'is_active': True})
    prog, _ = ProgrammeSegment.objects.get_or_create(
        code='01010001000100',
        defaults={'name': 'Test Programme', 'policy_code': '01',
                  'programme_code': '01', 'project_code': '000100',
                  'objective_code': '01', 'activity_code': '00',
                  'is_active': True})
    fund, _ = FundSegment.objects.get_or_create(
        code='01100',
        defaults={'name': 'Consolidated Revenue Fund', 'main_fund_code': '01',
                  'sub_fund_code': '1', 'fund_source_code': '00',
                  'is_active': True})
    geo, _ = GeographicSegment.objects.get_or_create(
        code='52500000',
        defaults={'name': 'Delta State', 'zone_code': '5',
                  'state_code': '25', 'is_active': True})
    ncoa, _ = NCoACode.objects.get_or_create(
        administrative=admin, economic=econ, functional=func,
        programme=prog, fund=fund, geographic=geo,
        defaults={'is_active': True, 'description': 'Batch guard test code'})

    # PaymentVoucherGov.tsa_account is NOT NULL — the voucher names the
    # treasury account the cash comes out of. SUB_ACCOUNT rather than
    # MAIN_TSA so the "one active MAIN_TSA per MDA" constraint stays free
    # for any other fixture in the same schema.
    tsa, _ = TreasuryAccount.objects.get_or_create(
        account_number='9900112233',
        defaults={'account_name': 'Works MDA Sub-Account', 'bank': 'CBN',
                  'account_type': 'SUB_ACCOUNT', 'is_active': True})

    return PaymentVoucherGov.objects.create(
        voucher_number='PV/2026/9001', payment_type='VENDOR',
        ncoa_code=ncoa, tsa_account=tsa,
        payee_name='ACME Ltd', payee_account='0123456789',
        payee_bank='Zenith Bank',
        gross_amount=Decimal('600.00'), net_amount=Decimal('600.00'),
    )


@pytest.fixture
def make_voucher_payment(db, bank_account_for_batch, batch_vendor):
    """Posted payment created WITH its voucher already attached.

    ``Payment`` carries ``ImmutableModelMixin``, so a Posted row refuses
    later edits ("Cannot modify a posted transaction"). The voucher link
    therefore has to exist at insert time rather than being bolted on
    afterwards — which is also how the real flow works, since the PV
    authorises the payment before it is posted.
    """
    from accounting.models import Payment

    counter = {'n': 0}

    def _make(voucher, amount):
        counter['n'] += 1
        return Payment.objects.create(
            payment_number=f'PAYV-{counter["n"]:04d}',
            payment_method='Wire',
            total_amount=Decimal(amount),
            status='Posted',
            bank_account=bank_account_for_batch,
            vendor=batch_vendor,
            payment_voucher=voucher,
            reference_number='Contract certificate',
        )

    return _make


@pytest.mark.integration
class TestVoucherAuthorityCeiling:
    """One PV may be settled by several payments; their total may not
    exceed what the voucher authorised."""

    def test_staged_settlement_within_authority_is_allowed(
        self, db, bank_account_for_batch, make_voucher_payment,
        maker_user, gov_voucher,
    ):
        """400 + 200 against a 600 voucher — legitimate, must not block."""
        from accounting.services.payment_batch import PaymentBatchService

        first = make_voucher_payment(gov_voucher, '400.00')
        second = make_voucher_payment(gov_voucher, '200.00')

        batch = PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch, batch_date=None,
            payment_ids=[first.pk, second.pk], user=maker_user,
        )
        assert batch.total_amount == Decimal('600.00')

    def test_exceeding_the_voucher_is_refused(
        self, db, bank_account_for_batch, make_voucher_payment,
        maker_user, gov_voucher,
    ):
        """400 + 400 against a 600 voucher — the excess has no authority."""
        from accounting.services.payment_batch import (
            PaymentBatchError, PaymentBatchService,
        )

        first = make_voucher_payment(gov_voucher, '400.00')
        second = make_voucher_payment(gov_voucher, '400.00')

        with pytest.raises(PaymentBatchError) as exc:
            PaymentBatchService.create_batch(
                bank_account=bank_account_for_batch, batch_date=None,
                payment_ids=[first.pk, second.pk], user=maker_user,
            )
        assert 'PV/2026/9001' in str(exc.value)
        assert 'authorises only' in str(exc.value)

    def test_guard_holds_across_separate_batches(
        self, db, bank_account_for_batch, make_voucher_payment,
        maker_user, gov_voucher,
    ):
        """Splitting the over-payment across two letters must not evade it."""
        from accounting.services.payment_batch import (
            PaymentBatchError, PaymentBatchService,
        )

        first = make_voucher_payment(gov_voucher, '500.00')
        second = make_voucher_payment(gov_voucher, '500.00')

        PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch, batch_date=None,
            payment_ids=[first.pk], user=maker_user,
        )
        with pytest.raises(PaymentBatchError):
            PaymentBatchService.create_batch(
                bank_account=bank_account_for_batch, batch_date=None,
                payment_ids=[second.pk], user=maker_user,
            )

    def test_a_payment_with_no_voucher_has_no_ceiling(
        self, db, bank_account_for_batch, make_posted_payment, maker_user,
    ):
        from accounting.services.payment_batch import PaymentBatchService

        batch = PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch, batch_date=None,
            payment_ids=[make_posted_payment(amount='9999.00').pk],
            user=maker_user,
        )
        assert batch.total_amount == Decimal('9999.00')


# ─────────────────────────────────────────────────────────────────────
# Confirmation evidence
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestConfirmationRequiresBankEvidence:

    def _dispatched(self, bank_account, make_posted_payment, user):
        from accounting.services.payment_batch import PaymentBatchService
        batch = PaymentBatchService.create_batch(
            bank_account=bank_account, batch_date=None,
            payment_ids=[make_posted_payment().pk], user=user,
        )
        PaymentBatchService.dispatch(batch, user)
        return batch

    def test_blank_reference_is_refused(
        self, db, bank_account_for_batch, make_posted_payment, maker_user,
    ):
        from accounting.services.payment_batch import (
            PaymentBatchError, PaymentBatchService,
        )
        batch = self._dispatched(
            bank_account_for_batch, make_posted_payment, maker_user)

        with pytest.raises(PaymentBatchError) as exc:
            PaymentBatchService.confirm(batch, maker_user, '  ')
        assert 'final' in str(exc.value)

    def test_reference_is_recorded_on_the_batch(
        self, db, bank_account_for_batch, make_posted_payment, maker_user,
    ):
        from accounting.models import PaymentBatch
        from accounting.services.payment_batch import PaymentBatchService

        batch = self._dispatched(
            bank_account_for_batch, make_posted_payment, maker_user)
        PaymentBatchService.confirm(batch, maker_user, '  FT26090400123456 ')

        batch.refresh_from_db()
        assert batch.status == PaymentBatch.STATUS_CONFIRMED
        assert batch.bank_reference == 'FT26090400123456'
        assert batch.confirmed_by_id == maker_user.pk

    def test_api_rejects_a_confirm_with_no_reference(
        self, db, tenant_api_client, bank_account_for_batch,
        make_posted_payment, superuser,
    ):
        batch = self._dispatched(
            bank_account_for_batch, make_posted_payment, superuser)
        tenant_api_client.force_authenticate(user=superuser)

        resp = tenant_api_client.post(
            f'/api/v1/accounting/payment-batches/{batch.pk}/confirm/',
            {}, format='json')
        assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────
# Batch numbering — a real row to lock, and an integer to increment
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestBatchNumberAllocation:

    def test_first_batch_of_a_year_allocates_one(
        self, db, bank_account_for_batch, make_posted_payment, maker_user,
    ):
        """The old MAX() approach locked nothing when no batch existed."""
        from datetime import date
        from accounting.services.payment_batch import PaymentBatchService

        batch = PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch,
            batch_date=date(2031, 3, 1),
            payment_ids=[make_posted_payment().pk],
            user=maker_user,
        )
        assert batch.batch_number == 'PB/2031/0001'

    def test_sequence_advances_across_batches(
        self, db, bank_account_for_batch, make_posted_payment, maker_user,
    ):
        from datetime import date
        from accounting.services.payment_batch import PaymentBatchService

        numbers = [
            PaymentBatchService.create_batch(
                bank_account=bank_account_for_batch,
                batch_date=date(2032, 3, 1),
                payment_ids=[make_posted_payment().pk],
                user=maker_user,
            ).batch_number
            for _ in range(3)
        ]
        assert numbers == ['PB/2032/0001', 'PB/2032/0002', 'PB/2032/0003']

    def test_counter_is_per_year(
        self, db, bank_account_for_batch, make_posted_payment, maker_user,
    ):
        from datetime import date
        from accounting.services.payment_batch import PaymentBatchService

        a = PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch, batch_date=date(2033, 12, 31),
            payment_ids=[make_posted_payment().pk], user=maker_user)
        b = PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch, batch_date=date(2034, 1, 2),
            payment_ids=[make_posted_payment().pk], user=maker_user)

        assert a.batch_number == 'PB/2033/0001'
        assert b.batch_number == 'PB/2034/0001'

    def test_survives_past_the_four_digit_pad(self, db):
        """String MAX() broke here: 'PB/2035/10000' sorts below '.../9999'."""
        from accounting.models import TransactionSequence
        from accounting.services.payment_batch import (
            PaymentBatchService, format_batch_number,
        )

        TransactionSequence.objects.create(
            name='payment_batch_2035', prefix='PB/2035/', next_value=9999)

        assert PaymentBatchService._next_sequence(2035) == 9999
        assert PaymentBatchService._next_sequence(2035) == 10000
        assert format_batch_number(2035, 10000) == 'PB/2035/10000'


# ─────────────────────────────────────────────────────────────────────
# Line-level audit
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestLineAudit:

    def test_line_records_who_added_the_vendor(
        self, db, bank_account_for_batch, make_posted_payment, maker_user,
    ):
        from accounting.services.payment_batch import PaymentBatchService

        batch = PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch, batch_date=None,
            payment_ids=[make_posted_payment().pk], user=maker_user,
        )
        line = batch.lines.get()
        assert line.created_by_id == maker_user.pk
        assert line.created_at is not None


# ─────────────────────────────────────────────────────────────────────
# Cancellation of a letter the bank already holds
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestCancelRequiresJustificationOnceDispatched:

    def _dispatched_batch(self, bank_account, make_posted_payment, user):
        from accounting.services.payment_batch import PaymentBatchService
        batch = PaymentBatchService.create_batch(
            bank_account=bank_account, batch_date=None,
            payment_ids=[make_posted_payment().pk], user=user,
        )
        PaymentBatchService.dispatch(batch, user)
        return batch

    def test_draft_cancels_without_a_reason(
        self, db, bank_account_for_batch, make_posted_payment, maker_user,
    ):
        from accounting.models import PaymentBatch
        from accounting.services.payment_batch import PaymentBatchService

        batch = PaymentBatchService.create_batch(
            bank_account=bank_account_for_batch, batch_date=None,
            payment_ids=[make_posted_payment().pk], user=maker_user,
        )
        PaymentBatchService.cancel(batch, maker_user)
        assert batch.status == PaymentBatch.STATUS_CANCELLED

    def test_dispatched_refuses_a_blank_reason(
        self, db, bank_account_for_batch, make_posted_payment,
        maker_user, checker_user,
    ):
        from accounting.services.payment_batch import (
            PaymentBatchError, PaymentBatchService,
        )
        batch = self._dispatched_batch(
            bank_account_for_batch, make_posted_payment, checker_user)

        with pytest.raises(PaymentBatchError) as exc:
            PaymentBatchService.cancel(batch, maker_user, '   ')
        assert 'written reason' in str(exc.value)

    def test_dispatched_cancels_with_a_reason_and_releases_payments(
        self, db, bank_account_for_batch, make_posted_payment,
        maker_user, checker_user,
    ):
        from accounting.models import PaymentBatch
        from accounting.services.payment_batch import PaymentBatchService

        batch = self._dispatched_batch(
            bank_account_for_batch, make_posted_payment, checker_user)
        PaymentBatchService.cancel(
            batch, maker_user, 'Bank confirmed the instruction was not actioned.')

        assert batch.status == PaymentBatch.STATUS_CANCELLED
        assert not batch.lines.filter(is_active_membership=True).exists()


# ─────────────────────────────────────────────────────────────────────
# Segregation of duties — driven by editable SoDRule rows, never code
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def sod_dispatch_rule(db):
    """The seeded create × dispatch rule, as a tenant admin would have it."""
    from core.models import PermissionDefinition, SoDRule

    create_perm, _ = PermissionDefinition.objects.get_or_create(
        code='accounting.payment_batch.create',
        defaults={'module': 'accounting', 'resource': 'payment_batch',
                  'action': 'create', 'description': 'Compile a bank payment letter'},
    )
    dispatch_perm, _ = PermissionDefinition.objects.get_or_create(
        code='accounting.payment_batch.dispatch',
        defaults={'module': 'accounting', 'resource': 'payment_batch',
                  'action': 'dispatch', 'description': 'Dispatch letter to the bank'},
    )
    rule, _ = SoDRule.objects.get_or_create(
        code='sod.payment_batch.create_dispatch',
        defaults={
            'name': 'Bank letter — compiler cannot dispatch own letter',
            'permission_a': create_perm, 'permission_b': dispatch_perm,
            'scope': 'same_document', 'severity': 'block',
            'is_active': True, 'is_system': True,
        },
    )
    return rule


@pytest.mark.integration
class TestDispatchSegregationIsConfigurable:
    """The matrix is data. These tests prove the code reads it."""

    def _draft(self, bank_account, make_posted_payment, user):
        from accounting.services.payment_batch import PaymentBatchService
        return PaymentBatchService.create_batch(
            bank_account=bank_account, batch_date=None,
            payment_ids=[make_posted_payment().pk], user=user,
        )

    def test_creator_cannot_dispatch_while_the_rule_is_active(
        self, db, bank_account_for_batch, make_posted_payment,
        maker_user, sod_dispatch_rule,
    ):
        from accounting.services.payment_batch import PaymentBatchService
        from core.services.sod_evaluator import SoDViolation

        batch = self._draft(bank_account_for_batch, make_posted_payment, maker_user)

        with pytest.raises(SoDViolation) as exc:
            PaymentBatchService.dispatch(batch, maker_user)
        assert 'sod.payment_batch.create_dispatch' in str(exc.value)

    def test_a_second_officer_can_dispatch(
        self, db, bank_account_for_batch, make_posted_payment,
        maker_user, checker_user, sod_dispatch_rule,
    ):
        from accounting.models import PaymentBatch
        from accounting.services.payment_batch import PaymentBatchService

        batch = self._draft(bank_account_for_batch, make_posted_payment, maker_user)
        PaymentBatchService.dispatch(batch, checker_user)
        assert batch.status == PaymentBatch.STATUS_DISPATCHED

    def test_deactivating_the_rule_lets_the_creator_dispatch(
        self, db, bank_account_for_batch, make_posted_payment,
        maker_user, sod_dispatch_rule,
    ):
        """Proof the control is configuration, not a hardcoded policy.

        A tenant whose treasury runs a different control switches this row
        off from the SoD-rules page and the same action now succeeds — no
        code change, no deploy.
        """
        from accounting.models import PaymentBatch
        from accounting.services.payment_batch import PaymentBatchService

        sod_dispatch_rule.is_active = False
        sod_dispatch_rule.save(update_fields=['is_active'])

        batch = self._draft(bank_account_for_batch, make_posted_payment, maker_user)
        PaymentBatchService.dispatch(batch, maker_user)
        assert batch.status == PaymentBatch.STATUS_DISPATCHED

    def test_severity_warn_logs_but_allows(
        self, db, bank_account_for_batch, make_posted_payment,
        maker_user, sod_dispatch_rule,
    ):
        """``severity`` is a per-rule column the admin sets."""
        from accounting.models import PaymentBatch
        from accounting.services.payment_batch import PaymentBatchService

        sod_dispatch_rule.severity = 'warn'
        sod_dispatch_rule.save(update_fields=['severity'])

        batch = self._draft(bank_account_for_batch, make_posted_payment, maker_user)
        PaymentBatchService.dispatch(batch, maker_user)
        assert batch.status == PaymentBatch.STATUS_DISPATCHED

    def test_no_rule_configured_means_no_restriction(
        self, db, bank_account_for_batch, make_posted_payment, maker_user,
    ):
        """A tenant that never seeded the catalogue is not silently blocked."""
        from accounting.models import PaymentBatch
        from accounting.services.payment_batch import PaymentBatchService

        batch = self._draft(bank_account_for_batch, make_posted_payment, maker_user)
        PaymentBatchService.dispatch(batch, maker_user)
        assert batch.status == PaymentBatch.STATUS_DISPATCHED


# ─────────────────────────────────────────────────────────────────────
# HTTP surface — the verbs ModelViewSet contributed for free
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestHttpVerbsRespectTheLifecycle:

    def _batch(self, bank_account, make_posted_payment, user, status=None):
        from accounting.services.payment_batch import PaymentBatchService
        batch = PaymentBatchService.create_batch(
            bank_account=bank_account, batch_date=None,
            payment_ids=[make_posted_payment().pk], user=user,
        )
        if status:
            batch.status = status
            batch.save(update_fields=['status'])
        return batch

    def test_put_is_not_routed_at_all(self):
        from accounting.views.payment_batch import PaymentBatchViewSet
        assert 'put' not in PaymentBatchViewSet.http_method_names

    def test_delete_refused_once_dispatched(
        self, db, tenant_api_client, bank_account_for_batch,
        make_posted_payment, superuser,
    ):
        from accounting.models import PaymentBatch

        batch = self._batch(bank_account_for_batch, make_posted_payment,
                            superuser, PaymentBatch.STATUS_DISPATCHED)
        tenant_api_client.force_authenticate(user=superuser)

        resp = tenant_api_client.delete(f'/api/v1/accounting/payment-batches/{batch.pk}/')
        assert resp.status_code == 409
        assert PaymentBatch.objects.filter(pk=batch.pk).exists()

    def test_delete_refused_once_confirmed_so_payments_stay_locked(
        self, db, tenant_api_client, bank_account_for_batch,
        make_posted_payment, superuser,
    ):
        """The double-payment route: delete cascades to lines, which
        releases the partial unique index, which frees the payments."""
        from accounting.models import PaymentBatch, PaymentBatchLine

        batch = self._batch(bank_account_for_batch, make_posted_payment,
                            superuser, PaymentBatch.STATUS_CONFIRMED)
        tenant_api_client.force_authenticate(user=superuser)

        resp = tenant_api_client.delete(f'/api/v1/accounting/payment-batches/{batch.pk}/')
        assert resp.status_code == 409
        assert PaymentBatchLine.objects.filter(
            batch=batch, is_active_membership=True).exists()

    def test_delete_allowed_while_draft(
        self, db, tenant_api_client, bank_account_for_batch,
        make_posted_payment, superuser,
    ):
        from accounting.models import PaymentBatch

        batch = self._batch(bank_account_for_batch, make_posted_payment, superuser)
        tenant_api_client.force_authenticate(user=superuser)

        resp = tenant_api_client.delete(f'/api/v1/accounting/payment-batches/{batch.pk}/')
        assert resp.status_code == 204
        assert not PaymentBatch.objects.filter(pk=batch.pk).exists()

    def test_patch_cannot_repoint_the_source_account_after_dispatch(
        self, db, tenant_api_client, bank_account_for_batch,
        make_posted_payment, superuser,
    ):
        from accounting.models import PaymentBatch

        batch = self._batch(bank_account_for_batch, make_posted_payment,
                            superuser, PaymentBatch.STATUS_DISPATCHED)
        original = batch.source_bank_account_id
        tenant_api_client.force_authenticate(user=superuser)

        resp = tenant_api_client.patch(
            f'/api/v1/accounting/payment-batches/{batch.pk}/',
            {'notes': 'tampering'}, format='json')

        assert resp.status_code == 409
        batch.refresh_from_db()
        assert batch.source_bank_account_id == original

    def test_patch_allowed_while_draft(
        self, db, tenant_api_client, bank_account_for_batch,
        make_posted_payment, superuser,
    ):
        batch = self._batch(bank_account_for_batch, make_posted_payment, superuser)
        tenant_api_client.force_authenticate(user=superuser)

        resp = tenant_api_client.patch(
            f'/api/v1/accounting/payment-batches/{batch.pk}/',
            {'notes': 'Second tranche'}, format='json')

        assert resp.status_code == 200
        batch.refresh_from_db()
        assert batch.notes == 'Second tranche'


@pytest.mark.integration
class TestDispatchPermissionsAreAddedNotSubstituted:
    """Returning a bare list previously dropped ModuleEnabled + RBAC."""

    def _viewset(self, action):
        from accounting.views.payment_batch import PaymentBatchViewSet
        view = PaymentBatchViewSet()
        view.action = action
        view.request = None
        view.format_kwarg = None
        return view

    def test_dispatch_drops_none_of_the_ordinary_gates(self, db):
        """Asserts the invariant, not a fixed list.

        Naming specific classes would make this test a description of
        today's ``permission_classes``; every gate the ViewSet applies to
        an ordinary read must ALSO apply to the one action that moves
        money, whatever those gates happen to be now or later.
        """
        baseline = {type(p) for p in self._viewset('list').get_permissions()}
        dispatch = {type(p) for p in self._viewset('dispatch_batch').get_permissions()}

        dropped = baseline - dispatch
        assert not dropped, f'dispatch bypasses {sorted(c.__name__ for c in dropped)}'

    def test_dispatch_adds_gates_rather_than_swapping_them(self, db):
        baseline = {type(p) for p in self._viewset('list').get_permissions()}
        dispatch = {type(p) for p in self._viewset('dispatch_batch').get_permissions()}
        assert dispatch - baseline, 'dispatch should be strictly more guarded'

    def test_dispatch_adds_mfa_and_approver(self, db):
        from accounting.permissions import RequiresMFA
        from core.permissions import IsApprover

        classes = {type(p) for p in self._viewset('dispatch_batch').get_permissions()}
        assert RequiresMFA in classes
        assert IsApprover in classes

    def test_other_actions_keep_the_plain_set(self, db):
        from accounting.permissions import RequiresMFA

        classes = {type(p) for p in self._viewset('list').get_permissions()}
        assert RequiresMFA not in classes


@pytest.mark.integration
class TestEligiblePaymentsRespectsMdaIsolation:

    def test_picker_applies_the_org_filter(
        self, db, bank_account_for_batch, make_posted_payment, superuser,
    ):
        """In SEPARATED mode with no organization resolved, the picker must
        return nothing rather than every MDA's payments."""
        from accounting.views.payment_batch import PaymentBatchViewSet
        from accounting.services.payment_batch import PaymentBatchService

        make_posted_payment()

        class _Req:
            mda_isolation_mode = 'SEPARATED'
            organization = None

        view = PaymentBatchViewSet()
        view.request = _Req()

        filtered = view.apply_org_filter(
            PaymentBatchService.eligible_payments(bank_account_for_batch),
            field='allocations__invoice__mda',
        )
        assert filtered.count() == 0

    def test_unified_mode_returns_everything(
        self, db, bank_account_for_batch, make_posted_payment, superuser,
    ):
        from accounting.views.payment_batch import PaymentBatchViewSet
        from accounting.services.payment_batch import PaymentBatchService

        make_posted_payment()

        class _Req:
            mda_isolation_mode = 'UNIFIED'
            organization = None

        view = PaymentBatchViewSet()
        view.request = _Req()

        filtered = view.apply_org_filter(
            PaymentBatchService.eligible_payments(bank_account_for_batch),
            field='allocations__invoice__mda',
        )
        assert filtered.count() == 1
