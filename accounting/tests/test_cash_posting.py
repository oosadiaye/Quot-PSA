"""Cash Posting (the FBCJ equivalent): cash journals, cash documents, the cash book and the day-end count.

Posting writes journals, so these run with ``transaction=True`` (the balance trigger reads the tenant schema).
"""
from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone
from decimal import Decimal
from unittest import mock

import pytest

D = Decimal

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def open_period(db):
    from accounting.models import FiscalPeriod
    today = timezone.localdate()
    FiscalPeriod.objects.get_or_create(
        fiscal_year=today.year, period_number=today.month, period_type='Monthly',
        defaults={'start_date': today.replace(day=1), 'end_date': today, 'status': 'Open', 'is_closed': False},
    )


@pytest.fixture
def desk(db):
    """A cash account with its journal, funded with an opening balance, plus a bank account and GL accounts."""
    from accounting.models import Account, BankAccount, CashJournal, MDA

    def gl(code, name, kind):
        acct, _ = Account.objects.get_or_create(code=code, defaults={'name': name, 'account_type': kind})
        # Accounts persist between runs (they are not flushed), so put each back the way these tests expect it.
        if not acct.is_active or acct.is_reconciliation:
            acct.is_active, acct.is_reconciliation = True, False
            acct.save(update_fields=['is_active', 'is_reconciliation'])
        return acct

    mda, _ = MDA.objects.get_or_create(code='CJ-MDA', defaults={'name': 'Cash Journal MDA', 'short_name': 'CJM'})
    cash_gl = gl('11100991', 'Cash on Hand CJ', 'Asset')
    bank_gl = gl('11100992', 'Bank CJ', 'Asset')
    expense = gl('22100993', 'Stationery CJ', 'Expense')
    revenue = gl('41100994', 'Fines CJ', 'Income')
    shortage = gl('22100995', 'Cash Shortage CJ', 'Expense')

    cash = BankAccount.objects.create(name='Registry Imprest', account_number='CJ-IMP-1', account_type='Imprest',
                                      gl_account=cash_gl, opening_balance=D('1000.00'), currency=None)
    bank = BankAccount.objects.create(name='Registry Bank', account_number='CJ-BANK-1', account_type='Bank',
                                      gl_account=bank_gl, opening_balance=D('0.00'), currency=None)
    journal = CashJournal.objects.get(cash_account=cash)
    journal.mda = mda
    journal.float_amount = D('1000.00')
    journal.save()
    return type('Desk', (), dict(journal=journal, cash=cash, bank=bank, mda=mda, expense=expense, revenue=revenue,
                                 shortage=shortage, cash_gl=cash_gl, bank_gl=bank_gl))


@pytest.fixture
def no_budget_gate():
    """Appropriation behaviour has its own tests; here the cash book is what is under test."""
    with mock.patch('accounting.services.cash_posting._budget_gates'):
        yield


def make_doc(desk, kind, amount, **extra):
    from accounting.models import CashDocument
    from accounting.services import cash_posting as service
    doc = CashDocument(cash_journal=desk.journal, posting_date=extra.pop('posting_date', timezone.localdate()), transaction_type=kind,
                       amount=D(str(amount)), mda=desk.mda, **extra)
    service.assign_number(doc)
    doc.save()
    return doc


class TestJournalFollowsAccount:
    def test_a_cash_account_has_a_journal_and_a_bank_account_does_not(self, desk):
        from accounting.models import CashJournal
        assert CashJournal.objects.filter(cash_account=desk.cash).exists()
        assert not CashJournal.objects.filter(cash_account=desk.bank).exists()

    def test_the_journal_follows_the_account_name_and_status(self, desk):
        desk.cash.name = 'Renamed Desk'
        desk.cash.is_active = False
        desk.cash.save()
        desk.journal.refresh_from_db()
        assert desk.journal.name == 'Renamed Desk'
        assert desk.journal.is_active is False

    def test_an_account_changed_to_bank_keeps_its_journal_but_closes_the_desk(self, desk):
        desk.cash.account_type = 'Bank'
        desk.cash.save()
        desk.journal.refresh_from_db()
        assert desk.journal.is_active is False


class TestPosting:
    def test_a_receipt_debits_cash_credits_the_account_and_raises_the_book(self, desk):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        doc = make_doc(desk, CD.REVENUE, '250.00', offset_account=desk.revenue)
        posted = service.post_document(doc)
        assert posted.status == CD.POSTED
        lines = {l.account_id: l for l in posted.journal_entry.lines.all()}
        assert lines[desk.cash_gl.pk].debit == D('250.00') and lines[desk.revenue.pk].credit == D('250.00')
        assert lines[desk.cash_gl.pk].bank_account_id == desk.cash.pk       # the cash line sits on this desk's book
        assert service.balance_as_of(desk.cash) == D('1250.00')
        desk.cash.refresh_from_db()
        assert desk.cash.current_balance == D('250.00')
        assert posted.journal_entry.mda_id == desk.mda.pk                  # the coding block reaches the journal

    def test_a_payment_credits_cash_and_lowers_the_book(self, desk, no_budget_gate):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        doc = make_doc(desk, CD.EXPENSE, '300.00', offset_account=desk.expense, recipient='Ada')
        posted = service.post_document(doc)
        assert service.balance_as_of(desk.cash) == D('700.00')
        assert 'Received by Ada' in posted.journal_entry.lines.first().memo

    def test_a_payment_with_line_items_debits_each_line_and_credits_cash_once(self, desk, no_budget_gate):
        from accounting.models import CashDocument as CD, CashDocumentLine
        from accounting.services import cash_posting as service
        doc = make_doc(desk, CD.EXPENSE, '300.00')
        CashDocumentLine.objects.create(document=doc, account=desk.expense, amount=D('100.00'))
        CashDocumentLine.objects.create(document=doc, account=desk.expense, amount=D('200.00'))
        posted = service.post_document(doc)
        credits = [l for l in posted.journal_entry.lines.all() if l.credit]
        assert len(credits) == 1 and credits[0].credit == D('300.00')
        assert sum(l.debit for l in posted.journal_entry.lines.all()) == D('300.00')

    def test_cash_cannot_be_paid_out_that_is_not_there(self, desk, no_budget_gate):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        doc = make_doc(desk, CD.EXPENSE, '1500.00', offset_account=desk.expense)
        with pytest.raises(service.CashPostingError, match='holds 1,000.00'):
            service.post_document(doc)
        doc.refresh_from_db()
        assert doc.status == CD.DRAFT

    def test_a_journal_that_allows_a_negative_balance_may_overdraw(self, desk, no_budget_gate):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        desk.journal.allow_negative_balance = True
        desk.journal.save()
        service.post_document(make_doc(desk, CD.EXPENSE, '1500.00', offset_account=desk.expense))
        assert service.balance_as_of(desk.cash) == D('-500.00')

    def test_a_payment_to_an_expense_needs_an_appropriation(self, desk):
        """The real gate, not mocked: no appropriation on the expense GL, so the cash payment is refused."""
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        doc = make_doc(desk, CD.EXPENSE, '100.00', offset_account=desk.expense)
        with pytest.raises(service.CashPostingError):
            service.post_document(doc)
        doc.refresh_from_db()
        assert doc.status == CD.DRAFT and doc.journal_entry_id is None

    def test_a_control_account_is_refused(self, desk, no_budget_gate):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        desk.revenue.is_reconciliation = True
        desk.revenue.save()
        with pytest.raises(service.CashPostingError, match='control account'):
            service.post_document(make_doc(desk, CD.REVENUE, '10.00', offset_account=desk.revenue))

    def test_a_posted_document_cannot_be_posted_twice(self, desk):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        doc = service.post_document(make_doc(desk, CD.REVENUE, '10.00', offset_account=desk.revenue))
        with pytest.raises(service.CashPostingError, match='only a Draft'):
            service.post_document(doc)


class TestBankTransfers:
    def test_a_withdrawal_moves_cash_in_from_the_bank_and_replenishes(self, desk):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        service.post_document(make_doc(desk, CD.REVENUE, '0.01', offset_account=desk.revenue))   # no-op sized receipt
        doc = service.post_document(make_doc(desk, CD.BANK_WITHDRAWAL, '400.00', bank_account=desk.bank))
        assert service.balance_as_of(desk.cash) == D('1400.01')
        assert service.balance_as_of(desk.bank) == D('-400.00')
        assert {l.account_id: l.credit for l in doc.journal_entry.lines.all() if l.credit}[desk.bank_gl.pk] == D('400.00')

    def test_a_deposit_takes_cash_out_to_the_bank(self, desk):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        service.post_document(make_doc(desk, CD.BANK_DEPOSIT, '600.00', bank_account=desk.bank))
        assert service.balance_as_of(desk.cash) == D('400.00')
        assert service.balance_as_of(desk.bank) == D('600.00')

    def test_the_other_account_cannot_be_the_cash_account_itself(self, desk):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        with pytest.raises(service.CashPostingError, match='different account'):
            service.post_document(make_doc(desk, CD.BANK_DEPOSIT, '10.00', bank_account=desk.cash))

    def test_replenishment_is_the_gap_to_the_float(self, desk, no_budget_gate):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        service.post_document(make_doc(desk, CD.EXPENSE, '350.00', offset_account=desk.expense))
        assert service.replenishment(desk.journal)['amount'] == D('350.00')


class TestReversal:
    def test_reversing_a_payment_puts_the_cash_back(self, desk, no_budget_gate):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        doc = service.post_document(make_doc(desk, CD.EXPENSE, '300.00', offset_account=desk.expense))
        service.reverse_document(doc, reason='wrong supplier')
        doc.refresh_from_db()
        assert doc.status == CD.REVERSED and doc.reversal_journal_id
        assert service.balance_as_of(desk.cash) == D('1000.00')
        desk.cash.refresh_from_db()
        assert desk.cash.current_balance == D('0.00')

    def test_a_reversal_that_would_take_out_cash_already_spent_is_refused(self, desk, no_budget_gate):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        receipt = service.post_document(make_doc(desk, CD.REVENUE, '500.00', offset_account=desk.revenue))
        service.post_document(make_doc(desk, CD.EXPENSE, '1400.00', offset_account=desk.expense))
        with pytest.raises(service.CashPostingError, match='takes back out'):
            service.reverse_document(receipt)

    def test_only_a_posted_document_can_be_reversed(self, desk):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        with pytest.raises(service.CashPostingError, match='only a posted'):
            service.reverse_document(make_doc(desk, CD.REVENUE, '10.00', offset_account=desk.revenue))


class TestCashBook:
    def test_the_book_shows_opening_flows_closing_and_drafts(self, desk, no_budget_gate):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        today = timezone.localdate()
        service.post_document(make_doc(desk, CD.REVENUE, '200.00', offset_account=desk.revenue))
        service.post_document(make_doc(desk, CD.EXPENSE, '50.00', offset_account=desk.expense))
        make_doc(desk, CD.EXPENSE, '25.00', offset_account=desk.expense)           # a Draft
        book = service.cash_book(desk.journal, today, today)
        assert book['opening_balance'] == D('1000.00')
        assert (book['receipts'], book['payments'], book['closing_balance']) == (D('200.00'), D('50.00'), D('1150.00'))
        assert book['balance_including_drafts'] == D('1125.00')

    def test_the_opening_balance_of_a_later_period_includes_earlier_days(self, desk):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        service.post_document(make_doc(desk, CD.REVENUE, '200.00', offset_account=desk.revenue))
        tomorrow = timezone.localdate() + timedelta(days=1)
        assert service.cash_book(desk.journal, tomorrow, tomorrow)['opening_balance'] == D('1200.00')


class TestClosingTheDay:
    def test_a_count_that_matches_closes_the_day_with_no_difference(self, desk):
        from accounting.services import cash_posting as service
        closing = service.close_journal(desk.journal, closing_date=timezone.localdate(), counted_amount=D('1000.00'))
        assert closing.difference == 0 and closing.difference_journal_id is None
        desk.journal.refresh_from_db()
        assert desk.journal.last_closed_date == timezone.localdate()

    def test_a_shortage_is_posted_to_the_difference_account(self, desk):
        from accounting.services import cash_posting as service
        desk.journal.difference_account = desk.shortage
        desk.journal.save()
        closing = service.close_journal(desk.journal, closing_date=timezone.localdate(), counted_amount=D('970.00'))
        assert closing.difference == D('-30.00')
        assert service.balance_as_of(desk.cash) == D('970.00')                  # the book now agrees with the count
        debit = closing.difference_journal.lines.get(debit__gt=0)
        assert debit.account_id == desk.shortage.pk

    def test_a_difference_without_a_difference_account_is_refused(self, desk):
        from accounting.services import cash_posting as service
        with pytest.raises(service.CashPostingError, match='difference'):
            service.close_journal(desk.journal, closing_date=timezone.localdate(), counted_amount=D('900.00'))

    def test_drafts_must_be_dealt_with_first(self, desk):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        make_doc(desk, CD.REVENUE, '10.00', offset_account=desk.revenue)
        with pytest.raises(service.CashPostingError, match='still Drafts'):
            service.close_journal(desk.journal, closing_date=timezone.localdate(), counted_amount=D('1000.00'))

    def test_nothing_can_be_posted_or_reversed_into_a_closed_day(self, desk):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        posted = service.post_document(make_doc(desk, CD.REVENUE, '10.00', offset_account=desk.revenue))
        service.close_journal(desk.journal, closing_date=timezone.localdate(), counted_amount=D('1010.00'))
        desk.journal.refresh_from_db()
        with pytest.raises(service.CashPostingError, match='closed'):
            service.post_document(make_doc(desk, CD.REVENUE, '5.00', offset_account=desk.revenue))
        with pytest.raises(service.CashPostingError, match='closed'):
            service.reverse_document(posted)

    def test_a_day_cannot_be_closed_before_it_has_happened(self, desk):
        from accounting.services import cash_posting as service
        with pytest.raises(service.CashPostingError, match='before it has happened'):
            service.close_journal(desk.journal, closing_date=timezone.localdate() + timedelta(days=1), counted_amount=D('1000.00'))


class TestReviewFixes:
    def test_a_back_dated_payment_may_not_push_a_later_day_below_zero(self, desk, no_budget_gate):
        from accounting.models import CashDocument as CD
        from accounting.services import cash_posting as service
        today = timezone.localdate()
        # Book: 1000 opening. Day-2 payment of 900 leaves 100; a later receipt then brings it back up.
        service.post_document(make_doc(desk, CD.EXPENSE, '900.00', offset_account=desk.expense, posting_date=today - timedelta(days=2)))
        service.post_document(make_doc(desk, CD.REVENUE, '900.00', offset_account=desk.revenue, posting_date=today))
        back_dated = make_doc(desk, CD.EXPENSE, '500.00', offset_account=desk.expense, posting_date=today - timedelta(days=3))
        with pytest.raises(service.CashPostingError, match='holds'):
            service.post_document(back_dated)

    def test_reversing_a_transfer_with_a_bank_account_that_shares_the_cash_gl_restores_both_books(self, desk):
        from accounting.models import BankAccount, CashDocument as CD
        from accounting.services import cash_posting as service
        shared = BankAccount.objects.create(name='Shared GL Bank', account_number='CJ-BANK-2', account_type='Bank',
                                            gl_account=desk.cash_gl, opening_balance=D('0.00'), currency=None)
        doc = service.post_document(make_doc(desk, CD.BANK_WITHDRAWAL, '300.00', bank_account=shared))
        assert service.balance_as_of(desk.cash) == D('1300.00') and service.balance_as_of(shared) == D('-300.00')
        service.reverse_document(doc)
        assert service.balance_as_of(desk.cash) == D('1000.00') and service.balance_as_of(shared) == D('0.00')


class TestApiScoping:
    DOMAIN = 'pytest.localhost'

    def _client(self, role):
        from django.contrib.auth.models import User
        from rest_framework.authtoken.models import Token
        from rest_framework.test import APIClient
        from django_tenants.utils import schema_context
        from tenants.models import Client, Domain, UserTenantRole
        with schema_context('public'):
            tenant, _ = Client.objects.get_or_create(schema_name='pytest_schema', defaults={'name': 'PyTest Tenant'})
            Domain.objects.get_or_create(domain=self.DOMAIN, tenant=tenant, defaults={'is_primary': True})
        user, _ = User.objects.get_or_create(username=f'cash_scope_{role}', defaults={'email': f'{role}@t.test'})
        UserTenantRole.objects.update_or_create(user=user, tenant=tenant, defaults={'role': role, 'is_active': True})
        token, _ = Token.objects.get_or_create(user=user)
        client = APIClient(HTTP_X_TENANT_DOMAIN=self.DOMAIN)
        client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        return client

    def test_a_desk_that_belongs_to_an_mda_charges_that_mda(self, desk):
        from accounting.models import MDA
        other, _ = MDA.objects.get_or_create(code='CJ-OTHER', defaults={'name': 'Other MDA', 'short_name': 'OTH'})
        admin = self._client('admin')
        response = admin.post('/api/v1/accounting/cash-documents/', {
            'cash_journal': desk.journal.pk, 'posting_date': timezone.localdate().isoformat(), 'transaction_type': 'REVENUE',
            'amount': '10.00', 'offset_account': desk.revenue.pk, 'mda': other.pk}, format='json')
        assert response.status_code == 201, response.content
        assert response.json()['mda'] == desk.mda.pk

    def test_only_a_tenant_admin_may_change_a_desks_settings(self, desk):
        url = f'/api/v1/accounting/cash-journals/{desk.journal.pk}/settings/'
        assert self._client('user').patch(url, {'float_amount': '1.00'}, format='json').status_code == 403
        assert self._client('admin').patch(url, {'float_amount': '1.00'}, format='json').status_code == 200

    def test_the_difference_account_must_be_a_usable_gl_account(self, desk):
        desk.cash_gl.refresh_from_db()
        response = self._client('admin').patch(
            f'/api/v1/accounting/cash-journals/{desk.journal.pk}/settings/', {'difference_account': desk.cash_gl.pk}, format='json')
        assert response.status_code == 400 and 'cash account itself' in str(response.json())


class TestApi:
    """The same flow through the HTTP endpoints the Cash Journal page uses."""
    DOMAIN = 'pytest.localhost'

    @pytest.fixture(autouse=True)
    def tenant_domain(self, db):
        """A transaction=True test before this one flushes the public tenant/domain rows; put them back."""
        from django_tenants.utils import schema_context
        from tenants.models import Client, Domain
        with schema_context('public'):
            client, _ = Client.objects.get_or_create(schema_name='pytest_schema', defaults={'name': 'PyTest Tenant'})
            Domain.objects.get_or_create(domain=self.DOMAIN, tenant=client, defaults={'is_primary': True})

    @pytest.fixture
    def admin(self, tenant_domain):
        from django.contrib.auth.models import User
        from rest_framework.authtoken.models import Token
        from rest_framework.test import APIClient
        from tenants.models import Client, UserTenantRole
        user, _ = User.objects.get_or_create(username='cash_api_admin', defaults={'email': 'cash@t.test'})
        user.set_password('Pass-1234-xyz')
        user.save()
        UserTenantRole.objects.update_or_create(
            user=user, tenant=Client.objects.get(schema_name='pytest_schema'), defaults={'role': 'admin', 'is_active': True})
        token, _ = Token.objects.get_or_create(user=user)
        client = APIClient(HTTP_X_TENANT_DOMAIN=self.DOMAIN)
        client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        return client

    def test_create_post_see_in_the_book_and_reverse(self, desk, admin):
        base = '/api/v1/accounting/'
        listed = admin.get(f'{base}cash-journals/')
        assert listed.status_code == 200, listed.content
        row = next(r for r in listed.json()['results'] if r['id'] == desk.journal.pk)
        assert row['balance'] == '1000.00'

        created = admin.post(f'{base}cash-documents/', {
            'cash_journal': desk.journal.pk, 'posting_date': timezone.localdate().isoformat(), 'transaction_type': 'REVENUE',
            'amount': '120.00', 'offset_account': desk.revenue.pk, 'description': 'Fine paid'}, format='json')
        assert created.status_code == 201, created.content
        doc = created.json()
        assert doc['document_number'].startswith('CJ-') and doc['status'] == 'Draft' and doc['mda'] == desk.mda.pk

        posted = admin.post(f'{base}cash-documents/{doc["id"]}/post_document/')
        assert posted.status_code == 200, posted.content
        assert posted.json()['status'] == 'Posted'

        today = timezone.localdate().isoformat()
        book = admin.get(f'{base}cash-journals/{desk.journal.pk}/book/', {'date_from': today, 'date_to': today}).json()
        assert (book['opening_balance'], book['receipts'], book['closing_balance']) == ('1000.00', '120.00', '1120.00')

        history = admin.get(f'{base}cash-documents/{doc["id"]}/history/').json()
        assert history['entries_are_projected'] is False and len(history['entries']) == 2

        assert admin.patch(f'{base}cash-documents/{doc["id"]}/', {'amount': '5.00'}, format='json').status_code == 400
        assert admin.delete(f'{base}cash-documents/{doc["id"]}/').status_code == 400   # a posted document is reversed, not deleted

        reversed_ = admin.post(f'{base}cash-documents/{doc["id"]}/reverse/', {'reason': 'entered twice'}, format='json')
        assert reversed_.status_code == 200 and reversed_.json()['status'] == 'Reversed'
        assert admin.get(f'{base}cash-journals/{desk.journal.pk}/').json()['balance'] == '1000.00'

    def test_a_draft_can_be_edited_and_deleted_and_a_bad_payment_is_explained(self, desk, admin):
        base = '/api/v1/accounting/'
        made = admin.post(f'{base}cash-documents/', {
            'cash_journal': desk.journal.pk, 'posting_date': timezone.localdate().isoformat(), 'transaction_type': 'EXPENSE',
            'lines': [{'account': desk.expense.pk, 'amount': '40.00'}, {'account': desk.expense.pk, 'amount': '60.00'}]},
            format='json')
        assert made.status_code == 201, made.content
        assert made.json()['amount'] == '100.00'                        # the lines' total
        no_account = admin.post(f'{base}cash-documents/', {
            'cash_journal': desk.journal.pk, 'posting_date': timezone.localdate().isoformat(), 'transaction_type': 'REVENUE',
            'amount': '10.00'}, format='json')
        assert no_account.status_code == 400 and 'offset_account' in no_account.json()
        refused = admin.post(f'{base}cash-documents/{made.json()["id"]}/post_document/')
        assert refused.status_code == 400 and 'error' in refused.json()   # no appropriation on the expense
        assert admin.delete(f'{base}cash-documents/{made.json()["id"]}/').status_code == 204

    def test_the_desk_settings_can_be_changed(self, desk, admin):
        response = admin.patch(f'/api/v1/accounting/cash-journals/{desk.journal.pk}/settings/', {
            'float_amount': '2500.00', 'difference_account': desk.shortage.pk, 'allow_negative_balance': True}, format='json')
        assert response.status_code == 200, response.content
        assert response.json()['float_amount'] == '2500.00' and response.json()['allow_negative_balance'] is True

    def test_it_needs_a_signed_in_user(self, desk):
        from rest_framework.test import APIClient
        assert APIClient(HTTP_X_TENANT_DOMAIN=self.DOMAIN).get('/api/v1/accounting/cash-journals/').status_code in (401, 403)
