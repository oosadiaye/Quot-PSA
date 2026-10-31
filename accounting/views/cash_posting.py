"""Cash Posting API: cash journals (cash desks), cash documents, the day-end count.

The rules live in ``accounting.services.cash_posting``; this module reads the request and turns ``CashPostingError`` into a
400 the cashier can read.

    /cash-journals/                       the desks, read-only: one is made with each Cash / Petty Cash / Imprest account
    /cash-journals/<id>/book/             opening, receipts, payments, closing for a period
    /cash-journals/<id>/replenishment/    what brings an imprest fund back to its float
    /cash-journals/<id>/closings/         the day-end counts so far
    /cash-journals/<id>/close/            count the cash, post any difference, close the day
    /cash-documents/                      the cash book entries; post_document / reverse / history
"""
import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounting.models import CashDocument, CashDocumentLine, CashJournal
from accounting.services import cash_posting as service
from accounting.services.base_posting import TransactionPostingError
from core.mixins import OrganizationFilterMixin
from rest_framework.permissions import IsAuthenticated
from core.permissions import ModuleEnabled, IsApprover, IsTenantAdmin, RBACPermission

from .common import AccountingPagination

logger = logging.getLogger(__name__)


def _fail(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({'error': str(message)}, status=code)


def _parse_date(raw, label):
    if raw in (None, ''):
        return None
    if isinstance(raw, date):
        return raw
    try:
        return datetime.strptime(str(raw)[:10], '%Y-%m-%d').date()
    except ValueError:
        raise service.CashPostingError(f'{label} must be a date (YYYY-MM-DD).')


# -- serializers ----------------------------------------------------------------------------------------------------------
class CashJournalSerializer(serializers.ModelSerializer):
    """Output only. A cash journal is created with its Bank & Cash account (see the cash_journal signal)."""
    cash_account_name = serializers.CharField(source='cash_account.name', read_only=True)
    cash_account_type = serializers.CharField(source='cash_account.account_type', read_only=True)
    difference_account_name = serializers.CharField(source='difference_account.name', read_only=True, default='')
    mda_name = serializers.CharField(source='mda.name', read_only=True, default='')
    balance = serializers.SerializerMethodField()

    class Meta:
        model = CashJournal
        fields = ['id', 'code', 'name', 'mda', 'mda_name', 'cash_account', 'cash_account_name', 'cash_account_type', 'float_amount',
                  'difference_account', 'difference_account_name', 'allow_negative_balance', 'overdraft_limit', 'is_active',
                  'last_closed_date', 'balance', 'created_at']
        read_only_fields = fields

    def get_balance(self, obj):
        """The cash on the book: now, or at the end of ``?as_of=`` so the page's balances follow the period it is showing."""
        return str(service.balance_as_of(obj.cash_account, self.context.get('as_of')))


class CashJournalSettingsSerializer(serializers.ModelSerializer):
    """What can be set on a desk: its MDA, imprest float, cash-difference account and whether the book may go negative."""
    class Meta:
        model = CashJournal
        fields = ['mda', 'float_amount', 'difference_account', 'allow_negative_balance', 'overdraft_limit']

    def validate_difference_account(self, account):
        if account is None:
            return account
        try:
            service._check_gl_account(account, self.instance)
        except service.CashPostingError as exc:
            raise serializers.ValidationError(str(exc))
        return account


#: Fields each transaction type uses; the rest are cleared so a document never carries a stray account.
_USES = {
    CashDocument.EXPENSE: ('offset_account',),
    CashDocument.REVENUE: ('offset_account',),
    CashDocument.BANK_WITHDRAWAL: ('bank_account',),
    CashDocument.BANK_DEPOSIT: ('bank_account',),
}
_FIELDS = ('offset_account', 'bank_account')
_CODING = ('mda', 'fund', 'function', 'program', 'geo')


class CashDocumentLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)

    class Meta:
        model = CashDocumentLine
        fields = ['id', 'account', 'account_code', 'account_name', 'description', 'amount']
        read_only_fields = ['id']


class CashDocumentSerializer(serializers.ModelSerializer):
    transaction_type_label = serializers.CharField(source='get_transaction_type_display', read_only=True)
    cash_journal_name = serializers.CharField(source='cash_journal.name', read_only=True)
    offset_account_name = serializers.CharField(source='offset_account.name', read_only=True, default='')
    offset_account_code = serializers.CharField(source='offset_account.code', read_only=True, default='')
    bank_account_name = serializers.CharField(source='bank_account.name', read_only=True, default='')
    mda_name = serializers.CharField(source='mda.name', read_only=True, default='')
    journal_number = serializers.CharField(source='journal_entry.document_number', read_only=True, default='')
    lines = CashDocumentLineSerializer(many=True, required=False)
    is_receipt = serializers.BooleanField(read_only=True)
    signed_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = CashDocument
        fields = ['id', 'document_number', 'cash_journal', 'cash_journal_name', 'posting_date', 'transaction_type',
                  'transaction_type_label', 'is_receipt', 'amount', 'signed_amount', 'description', 'reference', 'recipient',
                  'offset_account', 'offset_account_code', 'offset_account_name', 'bank_account', 'bank_account_name',
                  'mda', 'mda_name', 'fund', 'function', 'program', 'geo',
                  'status', 'journal_entry', 'journal_number', 'reversal_journal', 'posted_at', 'created_at', 'lines']
        read_only_fields = ['id', 'document_number', 'status', 'journal_entry', 'reversal_journal', 'posted_at', 'created_at']
        # With line items the amount is their total, so it need not be sent.
        extra_kwargs = {'amount': {'required': False}}

    def validate(self, attrs):
        attrs = super().validate(attrs)
        merged = {**{f: getattr(self.instance, f, None) for f in ('cash_journal', 'transaction_type', 'posting_date', 'amount')
                     + _FIELDS}, **attrs} if self.instance else attrs
        kind = merged.get('transaction_type')
        lines = attrs.get('lines')
        if lines is None and self.instance is not None and kind == CashDocument.EXPENSE:
            has_lines = self.instance.lines.exists()
        else:
            has_lines = bool(lines)
        if lines and kind != CashDocument.EXPENSE:
            raise serializers.ValidationError({'lines': 'Line items are only for a cash payment (expense).'})
        if has_lines and lines:
            for number, item in enumerate(lines, start=1):
                if item['amount'] <= 0:
                    raise serializers.ValidationError({'lines': f'Line {number}: the amount must be above zero.'})
            # The document amount is the total of its lines, and the single account no longer applies.
            attrs['amount'] = sum((item['amount'] for item in lines), Decimal('0'))
            attrs['offset_account'] = None
            merged = {**merged, 'amount': attrs['amount'], 'offset_account': None}
        elif merged.get('amount') in (None, ''):
            raise serializers.ValidationError({'amount': 'Enter the amount, or add line items.'})

        problems = {}
        for needed in _USES.get(kind, ()):
            if needed == 'offset_account' and has_lines:
                continue
            if not merged.get(needed):
                problems[needed] = 'This is required for this kind of cash document.'
        if problems:
            raise serializers.ValidationError(problems)

        journal = merged.get('cash_journal')
        when = merged.get('posting_date')
        view = self.context.get('view')
        if journal is not None and view is not None and not view.get_queryset_for_journals().filter(pk=journal.pk).exists():
            raise serializers.ValidationError({'cash_journal': 'You cannot use this cash journal.'})
        if journal is not None and journal.last_closed_date and when <= journal.last_closed_date:
            raise serializers.ValidationError({'posting_date': f'{journal.name} is closed up to {journal.last_closed_date:%d/%m/%Y}.'})

        # A desk that belongs to an MDA charges that MDA: the coding block cannot name another one.
        if journal is not None and journal.mda_id:
            attrs['mda'] = journal.mda
        # A type uses only its own fields: drop the rest so a document never carries a stray account.
        for name in _FIELDS:
            if kind in _USES and name not in _USES[kind] and name in attrs:
                attrs[name] = None
        if kind in _USES:
            for name in _FIELDS:
                if name not in _USES[kind]:
                    attrs.setdefault(name, None)
        if kind != CashDocument.EXPENSE and self.instance is not None and self.instance.lines.exists():
            attrs['lines'] = []                                   # the type was changed away from an expense: its lines go
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop('lines', [])
        document = super().create(validated_data)
        self._write_lines(document, lines)
        return document

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop('lines', None)
        document = super().update(instance, validated_data)
        if lines is not None:
            document.lines.all().delete()
            self._write_lines(document, lines)
        return document

    @staticmethod
    def _write_lines(document, lines):
        CashDocumentLine.objects.bulk_create([CashDocumentLine(document=document, **item) for item in lines])


def _person(user) -> str:
    if user is None:
        return ''
    return (user.get_full_name() or '').strip() or user.get_username()


def _event(event, label, user, when):
    return {'event': event, 'label': label, 'by': _person(user), 'at': when}


def _entry(account, debit, credit, memo):
    return {'account_code': account.code, 'account_name': account.name, 'debit': str(debit), 'credit': str(credit), 'memo': memo or ''}


def _journal_entries(header):
    return [_entry(line.account, line.debit, line.credit, line.memo) for line in header.lines.select_related('account').order_by('id')]


# -- viewsets -------------------------------------------------------------------------------------------------------------
class CashJournalViewSet(OrganizationFilterMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only: the journal is made with its Bank & Cash account. Reading, the book, counts and closing live here."""
    module_key = "accounting"
    queryset = CashJournal.objects.all().select_related('cash_account', 'difference_account', 'mda')
    serializer_class = CashJournalSerializer
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    org_filter_field = 'mda'
    filterset_fields = ['is_active']
    search_fields = ['code', 'name']
    pagination_class = AccountingPagination

    def get_serializer_context(self):
        context = super().get_serializer_context()
        try:
            context['as_of'] = _parse_date(self.request.query_params.get('as_of'), 'The balance date')
        except service.CashPostingError as exc:
            raise serializers.ValidationError({'as_of': str(exc)})
        return context

    @action(detail=True, methods=['patch'], url_path='settings', permission_classes=[IsTenantAdmin])
    def update_settings(self, request, pk=None):
        """Set the desk's MDA, imprest float, cash-difference account and overdraft rules."""
        journal = self.get_object()
        serializer = CashJournalSettingsSerializer(journal, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(self.get_serializer(journal).data)

    @action(detail=True, methods=['get'])
    def book(self, request, pk=None):
        journal = self.get_object()
        today = date.today()
        try:
            date_to = _parse_date(request.query_params.get('date_to'), 'The end date') or today
            date_from = _parse_date(request.query_params.get('date_from'), 'The start date') or date_to.replace(day=1)
        except service.CashPostingError as exc:
            return _fail(exc)
        if date_from > date_to:
            return _fail('The start date is after the end date.')
        book = service.cash_book(journal, date_from, date_to)
        last = journal.closings.first()
        data = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in book.items()}
        data.update({'date_from': date_from, 'date_to': date_to, 'float_amount': str(journal.float_amount),
                     'last_count': None if last is None else {
                         'closing_date': last.closing_date, 'book_balance': str(last.book_balance),
                         'counted_amount': str(last.counted_amount), 'difference': str(last.difference)},
                     'draft_documents': journal.documents.filter(status=CashDocument.DRAFT).count()})
        return Response(data)

    @action(detail=True, methods=['get'])
    def replenishment(self, request, pk=None):
        try:
            as_of = _parse_date(request.query_params.get('as_of'), 'The balance date')
        except service.CashPostingError as exc:
            return _fail(exc)
        figures = service.replenishment(self.get_object(), as_of)
        return Response({k: str(v) for k, v in figures.items()})

    @action(detail=True, methods=['get'])
    def closings(self, request, pk=None):
        rows = self.get_object().closings.select_related('difference_journal')[:60]
        return Response([{
            'id': c.pk, 'closing_date': c.closing_date, 'book_balance': str(c.book_balance), 'counted_amount': str(c.counted_amount),
            'difference': str(c.difference), 'note': c.note,
            'difference_journal': getattr(c.difference_journal, 'document_number', '') or '',
        } for c in rows])

    @action(detail=True, methods=['post'], permission_classes=[RBACPermission, IsApprover('post')])
    def close(self, request, pk=None):
        """Count the cash for a day: ``{closing_date, counted_amount, note}``."""
        journal = self.get_object()
        try:
            closing_date = _parse_date(request.data.get('closing_date'), 'The closing date') or date.today()
            try:
                counted = Decimal(str(request.data.get('counted_amount')))
            except (InvalidOperation, TypeError):
                raise service.CashPostingError('Enter the cash counted, as a number.')
            if not counted.is_finite():
                raise service.CashPostingError('Enter the cash counted, as a number.')
            closing = service.close_journal(journal, closing_date=closing_date, counted_amount=counted, user=request.user,
                                            note=request.data.get('note') or '')
        except (service.CashPostingError, TransactionPostingError) as exc:
            return _fail(exc)
        return Response({'id': closing.pk, 'closing_date': closing.closing_date, 'book_balance': str(closing.book_balance),
                         'counted_amount': str(closing.counted_amount), 'difference': str(closing.difference),
                         'last_closed_date': closing.closing_date}, status=status.HTTP_201_CREATED)


class CashDocumentViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    module_key = "accounting"
    queryset = CashDocument.objects.all().select_related(
        'cash_journal', 'offset_account', 'bank_account', 'journal_entry', 'mda').prefetch_related('lines__account')
    serializer_class = CashDocumentSerializer
    permission_classes = [IsAuthenticated, ModuleEnabled, RBACPermission]
    org_filter_field = 'mda'
    filterset_fields = {'cash_journal': ['exact'], 'status': ['exact'], 'transaction_type': ['exact'],
                        'posting_date': ['exact', 'gte', 'lte']}
    search_fields = ['document_number', 'description', 'reference', 'recipient']
    ordering_fields = ['posting_date', 'document_number', 'amount', 'status']
    ordering = ['-posting_date', '-id']
    pagination_class = AccountingPagination

    def get_permissions(self):
        if self.action in ('post_document', 'reverse'):
            return [RBACPermission(), IsApprover('post')]
        return super().get_permissions()

    def get_queryset_for_journals(self):
        """The cash journals this user may use: the same MDA scoping as the journal list."""
        journals = CashJournalViewSet()
        journals.request, journals.action, journals.format_kwarg, journals.kwargs, journals.args = self.request, 'list', None, {}, ()
        return journals.get_queryset().filter(is_active=True)

    @transaction.atomic
    def perform_create(self, serializer):
        doc = serializer.save(created_by=self.request.user)
        service.assign_number(doc)
        doc.save(update_fields=['document_number'])

    def perform_update(self, serializer):
        if serializer.instance.status != CashDocument.DRAFT:
            raise serializers.ValidationError('Only a Draft cash document can be changed. Reverse a posted one instead.')
        serializer.save(updated_by=self.request.user, edited_at=timezone.now())

    def perform_destroy(self, instance):
        if instance.status != CashDocument.DRAFT:
            raise serializers.ValidationError('Only a Draft cash document can be deleted. Reverse a posted one instead.')
        super().perform_destroy(instance)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """The View screen: who created, changed, posted (approved) and reversed the document, and its accounting entries.

        A Draft has no journal, so it shows the entries it WILL post (the same lines posting writes); a posted one shows its journal;
        a reversed one also shows the mirror journal. Reading changes nothing.
        """
        doc = self.get_object()
        journal = doc.journal_entry
        reversal = doc.reversal_journal
        events = [_event('Created', 'Created by', doc.created_by, doc.created_at)]
        if doc.updated_by_id and doc.edited_at:
            events.append(_event('Changed', 'Changed by', doc.updated_by, doc.edited_at))
        if doc.posted_at:
            events.append(_event('Posted', 'Posted and approved by', doc.posted_by or getattr(journal, 'posted_by', None), doc.posted_at))
        if doc.status == CashDocument.REVERSED:
            events.append(_event('Reversed', 'Reversed by', doc.reversed_by or getattr(reversal, 'posted_by', None),
                                 doc.reversed_at or getattr(reversal, 'posted_at', None)))
        note = ''
        if journal is not None:
            entries, projected = _journal_entries(journal), False
        else:
            projected = True
            try:
                lines = service.gl_lines_for(doc)
            except Exception:  # noqa: BLE001 - an incomplete Draft (no account chosen yet) has nothing to preview
                lines = []
                note = 'Complete the document (accounts, bank account) to see the entries it will post.'
            entries = [_entry(item['account'], item['debit'], item['credit'], item['memo']) for item in lines]
        return Response({
            'id': doc.pk, 'document_number': doc.document_number, 'status': doc.status,
            'events': events, 'entries': entries, 'entries_are_projected': projected, 'note': note,
            'journal_id': journal.pk if journal else None, 'journal_number': journal.document_number if journal else None,
            'reversal_journal_id': reversal.pk if reversal else None,
            'reversal_journal_number': reversal.document_number if reversal else None,
            'reversal_entries': _journal_entries(reversal) if reversal is not None else [],
        })

    @action(detail=True, methods=['post'])
    def post_document(self, request, pk=None):
        doc = self.get_object()
        try:
            doc = service.post_document(doc, user=request.user)
        except (service.CashPostingError, TransactionPostingError) as exc:
            return _fail(exc)
        except DjangoValidationError as exc:
            return _fail('; '.join(exc.messages))
        except Exception:  # noqa: BLE001
            logger.exception('Cash document post failed')
            return _fail('The cash document could not be posted. The error has been logged.', status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({**self.get_serializer(doc).data, 'status_text': f'{doc.document_number} posted.'})

    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        doc = self.get_object()
        try:
            service.reverse_document(doc, user=request.user, reason=request.data.get('reason') or '')
        except (service.CashPostingError, TransactionPostingError) as exc:
            return _fail(exc)
        except DjangoValidationError as exc:
            return _fail('; '.join(exc.messages))
        except Exception:  # noqa: BLE001
            logger.exception('Cash document reversal failed')
            return _fail('The reversal could not be posted. The error has been logged.', status.HTTP_500_INTERNAL_SERVER_ERROR)
        doc.refresh_from_db()
        return Response(self.get_serializer(doc).data)
