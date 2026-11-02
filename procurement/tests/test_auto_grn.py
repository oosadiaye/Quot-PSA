"""Auto / manual GRN: a PO resolves its mode, and AUTO books a posted GRN on approval."""
from datetime import date
from decimal import Decimal
from unittest import mock

import pytest


def _po(grn_mode='', status='Pending', qty=('10', '4')):
    from accounting.models.gl import Account, Fund, Function, Program, Geo, MDA
    from procurement.models import PurchaseOrder, PurchaseOrderLine, Vendor

    vendor, _ = Vendor.objects.get_or_create(code='AGRN1', defaults={'name': 'AutoGRN Supplies Ltd'})
    if not vendor.is_active:
        vendor.is_active = True
        vendor.save(update_fields=['is_active'])
    fund, _ = Fund.objects.get_or_create(code='AG1', defaults={'name': 'AG Fund'})
    fn, _ = Function.objects.get_or_create(code='AG1', defaults={'name': 'AG Func'})
    pr, _ = Program.objects.get_or_create(code='AG1', defaults={'name': 'AG Prog'})
    geo, _ = Geo.objects.get_or_create(code='AG1', defaults={'name': 'AG Geo'})
    acct, _ = Account.objects.get_or_create(code='22100991', defaults={'name': 'AG Expense', 'account_type': 'Expense'})
    mda, _ = MDA.objects.get_or_create(code='AGRN-MDA', defaults={'name': 'Auto GRN MDA', 'short_name': 'AGM'})
    po = PurchaseOrder.objects.create(
        mda=mda, vendor=vendor, order_date=date(2026, 3, 1), fund=fund, function=fn, program=pr, geo=geo,
        status=status, grn_mode=grn_mode,
    )
    for i, q in enumerate(qty):
        PurchaseOrderLine.objects.create(
            po=po, item_description=f'Line {i}', quantity=Decimal(q), unit_price=Decimal('100.00'), account=acct,
        )
    return po


def _approve(po):
    # Reload so tax_rate is a Decimal (a freshly created instance still holds the float default).
    po.refresh_from_db()
    po.status = 'Approved'
    with mock.patch('procurement.models.PurchaseOrder._check_warrant_ceiling'),          mock.patch('procurement.models.PurchaseOrder.process_budget_encumbrance'),          mock.patch('accounting.services.procurement_commitments.create_commitment_for_po'):
        po.save()
    return po


@pytest.fixture(autouse=True)
def _no_budget_commitment():
    # Commitment/appropriation behaviour has its own tests; here the PO is only a receiving target.
    with mock.patch('accounting.services.procurement_commitments.create_commitment_for_po'):
        yield


@pytest.fixture(autouse=True)
def _open_period(db):
    from accounting.models import FiscalPeriod
    today = date.today()
    FiscalPeriod.objects.get_or_create(
        fiscal_year=today.year, period_number=today.month, period_type='Monthly',
        defaults={'start_date': today.replace(day=1), 'end_date': today, 'status': 'Open', 'is_closed': False},
    )


@pytest.fixture
def default_mode():
    from inventory.models import InventorySettings

    def _set(mode):
        s = InventorySettings.load()
        s.default_grn_mode = mode
        s.save()
    yield _set
    _set('MANUAL')


@pytest.mark.django_db
class TestResolveMode:
    def test_follows_the_tenant_default_when_the_po_has_no_setting(self, default_mode):
        from procurement.services.auto_grn import resolve_grn_mode
        po = _po()
        default_mode('MANUAL')
        assert resolve_grn_mode(po) == 'MANUAL'
        default_mode('AUTO')
        assert resolve_grn_mode(po) == 'AUTO'

    def test_a_po_setting_beats_the_default(self, default_mode):
        from procurement.services.auto_grn import resolve_grn_mode
        default_mode('AUTO')
        assert resolve_grn_mode(_po(grn_mode='MANUAL')) == 'MANUAL'
        default_mode('MANUAL')
        assert resolve_grn_mode(_po(grn_mode='AUTO')) == 'AUTO'


@pytest.mark.django_db(transaction=True)
class TestAutoReceive:
    def test_books_a_posted_grn_for_every_outstanding_quantity(self):
        from procurement.services.auto_grn import auto_receive_po
        po = _approve(_po())
        grn = auto_receive_po(po)
        assert grn.status == 'Posted'
        assert {l.quantity_received for l in grn.lines.all()} == {Decimal('10.00'), Decimal('4.00')}
        assert all(l.is_fully_received for l in po.lines.all().order_by('id') if (l.refresh_from_db() or True))

    def test_receives_only_what_is_still_outstanding(self):
        from procurement.services.auto_grn import auto_receive_po
        po = _approve(_po())
        first = po.lines.order_by('id').first()
        first.quantity_received = Decimal('6.00')
        first.save()
        grn = auto_receive_po(po)
        assert sorted(l.quantity_received for l in grn.lines.all()) == [Decimal('4.00'), Decimal('4.00')]

    def test_is_idempotent_and_never_doubles_up_on_an_existing_grn(self):
        from procurement.services.auto_grn import auto_receive_po
        po = _approve(_po())
        assert auto_receive_po(po) is not None
        assert auto_receive_po(po) is None
        assert po.goodsreceivednote_set.count() == 1


@pytest.mark.django_db(transaction=True)
class TestApprovalHook:
    def test_approving_an_auto_po_books_the_grn(self):
        po = _po(grn_mode='AUTO', status='Pending')
        _approve(po)
        assert po.goodsreceivednote_set.filter(status='Posted').count() == 1

    def test_approving_a_manual_po_books_nothing(self):
        po = _po(grn_mode='MANUAL', status='Pending')
        _approve(po)
        assert po.goodsreceivednote_set.count() == 0

    def test_a_failed_auto_receipt_does_not_undo_the_approval(self):
        po = _po(grn_mode='AUTO', status='Pending')
        with mock.patch('procurement.services.auto_grn.auto_receive_po', side_effect=RuntimeError('no warehouse')):
            _approve(po)
        assert 'no warehouse' in po.auto_grn_error
        po.refresh_from_db()
        assert po.status == 'Approved'
        assert po.goodsreceivednote_set.count() == 0
