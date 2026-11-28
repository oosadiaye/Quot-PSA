"""The rules a tag must obey: the type is on for the record, the value belongs to it, a child sits under its parent,
mandatory dimensions are present, and a posted record's tags never change."""
import pytest

from accounting.models import Account, JournalHeader, JournalLine
from dimensions import services
from dimensions.models import DimensionTag

pytestmark = pytest.mark.django_db


def _line():
    acct, _ = Account.objects.get_or_create(
        code='29990001', defaults=dict(name='Dim test expense', account_type='Expense', is_active=True))
    header = JournalHeader.objects.create(description='dim test', status='Draft')
    return JournalLine.objects.create(header=header, account=acct, debit=100, credit=0)


def test_a_tag_is_stored_and_replaced(zone_ward):
    line = _line()
    services.set_tags('journal_line', line.pk, {'zone': 'Z1', 'ward': 'W1'})
    assert DimensionTag.objects.filter(record_id=line.pk).count() == 2
    services.set_tags('journal_line', line.pk, {'zone': 'Z2', 'ward': 'W2'})
    assert services.get_tags('journal_line', line.pk) == {'zone': 'Z2', 'ward': 'W2'}
    assert DimensionTag.objects.filter(record_id=line.pk).count() == 2


def test_a_child_must_sit_under_the_tagged_parent(zone_ward):
    line = _line()
    with pytest.raises(services.DimensionError, match='not in'):
        services.set_tags('journal_line', line.pk, {'zone': 'Z1', 'ward': 'W2'})


def test_a_child_value_alone_pulls_in_its_parent_tag(zone_ward):
    line = _line()
    services.set_tags('journal_line', line.pk, {'ward': 'W1'})
    # a ward alone implies its zone, so a zone report and a ward report agree about the line
    assert services.get_tags('journal_line', line.pk) == {'zone': 'Z1', 'ward': 'W1'}


def test_unknown_inactive_or_off_type_is_refused(zone_ward):
    line = _line()
    with pytest.raises(services.DimensionError, match='Unknown dimension'):
        services.set_tags('journal_line', line.pk, {'polling_unit': 'P1'})
    with pytest.raises(services.DimensionError, match='Unknown value'):
        services.set_tags('journal_line', line.pk, {'zone': 'NOPE'})
    zone_ward['z1'].is_active = False
    zone_ward['z1'].save()
    with pytest.raises(services.DimensionError, match='inactive'):
        services.set_tags('journal_line', line.pk, {'zone': 'Z1'})
    with pytest.raises(services.DimensionError, match='not switched on'):
        services.set_tags('purchase_order', 1, {'zone': 'Z2'})


def test_a_mandatory_dimension_must_be_present(zone_ward):
    zone_ward['ward'].required_on = ['journal_line']
    zone_ward['ward'].save()
    line = _line()
    with pytest.raises(services.DimensionError, match='Ward is required'):
        services.set_tags('journal_line', line.pk, {'zone': 'Z1'})
    services.set_tags('journal_line', line.pk, {'ward': 'W1'})


@pytest.mark.django_db(transaction=True)
def test_posted_lines_cannot_be_retagged(zone_ward):
    line = _line()
    services.set_tags('journal_line', line.pk, {'ward': 'W1'})
    offset, _ = Account.objects.get_or_create(
        code='19990003', defaults=dict(name='Dim test offset', account_type='Asset', is_active=True))
    JournalLine.objects.create(header=line.header, account=offset, debit=0, credit=100)   # a posted journal must balance
    JournalHeader.all_objects.filter(pk=line.header_id).update(status='Posted')
    with pytest.raises(services.DimensionError, match='posted'):
        services.set_tags('journal_line', line.pk, {'ward': 'W2'})
    assert services.get_tags('journal_line', line.pk) == {'zone': 'Z1', 'ward': 'W1'}


def test_a_journal_level_default_fills_lines_without_their_own_tag(zone_ward):
    a = _line()
    b = JournalLine.objects.create(header=a.header, account=a.account, debit=0, credit=100)
    services.set_tags('journal_line', a.pk, {'ward': 'W2'})
    services.apply_default_to_journal(a.header_id, {'ward': 'W1'})
    assert services.get_tags('journal_line', a.pk) == {'zone': 'Z2', 'ward': 'W2'}      # own tag kept
    assert services.get_tags('journal_line', b.pk) == {'zone': 'Z1', 'ward': 'W1'}      # default filled


def test_deleting_a_line_removes_its_tags(zone_ward):
    line = _line()
    services.set_tags('journal_line', line.pk, {'ward': 'W1'})
    pk = line.pk
    line.delete()
    assert not DimensionTag.objects.filter(record_type='journal_line', record_id=pk).exists()


def test_tagging_a_record_that_does_not_exist_is_refused(zone_ward):
    with pytest.raises(services.DimensionError, match='does not exist'):
        services.set_tags('journal_line', 987654321, {'ward': 'W1'})


def _purchase_request(status='Draft'):
    from procurement.models import PurchaseRequest
    n = PurchaseRequest.objects.count() + 1
    from accounting.models import Fund, Function, Geo, Program
    dims = [m.objects.get_or_create(code='DIM', defaults={'name': 'Dim'})[0] for m in (Fund, Function, Program, Geo)]
    pr = PurchaseRequest(request_number=f'PR-DIM-{n}-{status}', description='dim', status=status,
                         fund=dims[0], function=dims[1], program=dims[2], geo=dims[3])
    pr.save()
    return pr


def test_copy_tags_carries_only_dimensions_switched_on_for_the_target(zone_ward):
    zone_ward['zone'].applies_to = ['journal_line', 'purchase_request', 'purchase_order']
    zone_ward['zone'].save()
    zone_ward['ward'].applies_to = ['journal_line', 'purchase_request']        # not on for orders
    zone_ward['ward'].save()
    pr = _purchase_request()
    services.set_tags('purchase_request', pr.pk, {'zone': 'Z1', 'ward': 'W1'})
    services.copy_tags('purchase_request', pr.pk, 'purchase_order', 424242)
    assert services.get_tags('purchase_order', 424242) == {'zone': 'Z1'}
    # copying again replaces rather than duplicates
    services.copy_tags('purchase_request', pr.pk, 'purchase_order', 424242)
    assert DimensionTag.objects.filter(record_type='purchase_order', record_id=424242).count() == 1


def test_an_approved_request_is_locked_and_a_draft_one_is_not(zone_ward):
    zone_ward['zone'].applies_to = ['journal_line', 'purchase_request']
    zone_ward['zone'].save()
    draft = _purchase_request('Draft')
    services.set_tags('purchase_request', draft.pk, {'zone': 'Z1'})
    approved = _purchase_request('Pending')
    from procurement.models import PurchaseRequest
    PurchaseRequest.objects.filter(pk=approved.pk).update(status='Approved')
    with pytest.raises(services.DimensionError, match='approved'):
        services.set_tags('purchase_request', approved.pk, {'zone': 'Z1'})
