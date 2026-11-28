"""The journal form sends account ids as strings ("6"); the account check must accept them, and still refuse unknown or
non-numeric ones with a readable message instead of a 500."""
import pytest
from django.core.exceptions import ValidationError

from accounting.models import Account
from accounting.services.journal_lines import assert_accounts_exist, validate_journal_lines

pytestmark = pytest.mark.django_db


@pytest.fixture
def postable_account():
    acct, _ = Account.objects.get_or_create(
        code='19990101', defaults=dict(name='String id test', account_type='Asset', is_active=True))
    return acct


def _lines(account):
    return validate_journal_lines([
        {'account': account, 'debit': '10', 'credit': '0'},
        {'account': account, 'debit': '0', 'credit': '10'},
    ])


def test_string_account_ids_from_the_form_are_accepted(postable_account):
    assert_accounts_exist(_lines(str(postable_account.pk)))


def test_integer_account_ids_are_accepted(postable_account):
    assert_accounts_exist(_lines(postable_account.pk))


def test_an_unknown_id_is_refused_with_a_message(postable_account):
    with pytest.raises(ValidationError, match='Unknown account'):
        assert_accounts_exist(_lines('99999999'))


def test_a_non_numeric_id_is_refused_with_a_message():
    with pytest.raises(ValidationError, match='Unknown account'):
        assert_accounts_exist(_lines('abc'))
