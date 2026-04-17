import csv
import io
import logging
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import transaction
from decimal import Decimal, InvalidOperation
from ..models import (
    BankAccount, Checkbook, Check, BankReconciliation,
    CashFlowCategory, CashFlowForecast, BankStatement, BankStatementLine,
)
from ..serializers import (
    BankAccountSerializer, CheckbookSerializer, CheckSerializer, BankReconciliationSerializer,
    CashFlowCategorySerializer, CashFlowForecastSerializer,
    ReceiptSerializer, PaymentSerializer,
)
from core.utils import api_response

logger = logging.getLogger(__name__)


class BankAccountViewSet(viewsets.ModelViewSet):
    queryset = BankAccount.objects.all().select_related('gl_account', 'currency')
    serializer_class = BankAccountSerializer
    filterset_fields = ['account_type', 'is_active', 'currency']
    search_fields = ['name', 'account_number', 'bank_name']

    def get_queryset(self):
        queryset = super().get_queryset()
        account_type = self.request.query_params.get('account_type')
        if account_type:
            if account_type == 'bank':
                queryset = queryset.filter(account_type='Bank')
            elif account_type == 'cash':
                queryset = queryset.filter(account_type__in=['Cash', 'Petty Cash', 'Imprest'])
        return queryset

    @action(detail=False, methods=['get'])
    def summary(self, request):
        bank_accounts = self.queryset.filter(is_active=True)
        total_bank = sum(ba.current_balance for ba in bank_accounts.filter(account_type='Bank'))
        total_cash = sum(ba.current_balance for ba in bank_accounts.filter(account_type__in=['Cash', 'Petty Cash', 'Imprest']))
        total_customer_advance = sum(ba.advance_customer_balance for ba in bank_accounts)
        total_supplier_advance = sum(ba.advance_supplier_balance for ba in bank_accounts)
        return Response({
            'total_bank_balance': total_bank,
            'total_cash_balance': total_cash,
            'total_customer_advance': total_customer_advance,
            'total_supplier_advance': total_supplier_advance,
            'bank_accounts_count': bank_accounts.filter(account_type='Bank').count(),
            'cash_accounts_count': bank_accounts.filter(account_type__in=['Cash', 'Petty Cash', 'Imprest']).count(),
        })

    @action(detail=True, methods=['get'])
    def transactions(self, request, pk=None):
        bank_account = self.get_object()
        incoming = bank_account.incoming_payments.all().select_related('currency')
        outgoing = bank_account.outgoing_payments.all().select_related('vendor', 'currency')
        return Response({
            'incoming_payments': ReceiptSerializer(incoming, many=True).data,
            'outgoing_payments': PaymentSerializer(outgoing, many=True).data,
        })


class CheckbookViewSet(viewsets.ModelViewSet):
    queryset = Checkbook.objects.all().select_related('bank_account')
    serializer_class = CheckbookSerializer
    filterset_fields = ['bank_account', 'status']


class CheckViewSet(viewsets.ModelViewSet):
    queryset = Check.objects.all().select_related('checkbook', 'payment')
    serializer_class = CheckSerializer
    filterset_fields = ['checkbook', 'status']


class BankReconciliationViewSet(viewsets.ModelViewSet):
    queryset = BankReconciliation.objects.all().select_related('bank_account', 'reconciled_by', 'approved_by')
    serializer_class = BankReconciliationSerializer
    filterset_fields = ['bank_account', 'status']

    @action(detail=True, methods=['post'])
    def reconcile(self, request, pk=None):
        recon = self.get_object()
        book_balance = recon.bank_account.current_balance

        deposits_in_transit = request.data.get('deposits_in_transit', 0)
        outstanding_checks = request.data.get('outstanding_checks', 0)
        bank_charges = request.data.get('bank_charges', 0)

        reconciled_balance = book_balance + deposits_in_transit - outstanding_checks - bank_charges
        difference = reconciled_balance - recon.statement_balance

        with transaction.atomic():
            recon.book_balance = book_balance
            recon.deposits_in_transit = deposits_in_transit
            recon.outstanding_checks = outstanding_checks
            recon.bank_charges = bank_charges
            recon.reconciled_balance = reconciled_balance
            recon.difference = difference
            recon.status = 'Reconciled'
            recon.reconciled_by = request.user
            recon.save()
            recon.complete(approved_by_user=request.user)

        return Response(BankReconciliationSerializer(recon).data)


class CashFlowCategoryViewSet(viewsets.ModelViewSet):
    queryset = CashFlowCategory.objects.all()
    serializer_class = CashFlowCategorySerializer
    filterset_fields = ['category_type', 'is_active']


class CashFlowForecastViewSet(viewsets.ModelViewSet):
    queryset = CashFlowForecast.objects.all().select_related('bank_account')
    serializer_class = CashFlowForecastSerializer
    filterset_fields = ['bank_account']


# ---------------------------------------------------------------------------
# Bank Statement Import
# ---------------------------------------------------------------------------

# Expected CSV columns (case-insensitive header matching):
#   date, value_date, description, reference, debit, credit, balance, type
#
# The importer is deliberately permissive: missing optional columns are
# silently skipped; missing required columns (date, description) cause the
# entire import to fail with an HTTP 400 so the caller knows the file is
# malformed before any rows are committed.

_CSV_COL_ALIASES = {
    # canonical key → list of accepted header names
    'date':        ['date', 'transaction_date', 'trans_date', 'txn_date'],
    'value_date':  ['value_date', 'val_date', 'settlement_date'],
    'description': ['description', 'narrative', 'details', 'remarks', 'memo'],
    'reference':   ['reference', 'ref', 'ref_number', 'check_no', 'cheque_no'],
    'debit':       ['debit', 'debit_amount', 'withdrawals', 'dr'],
    'credit':      ['credit', 'credit_amount', 'deposits', 'cr'],
    'balance':     ['balance', 'running_balance', 'closing_balance'],
    'type':        ['type', 'transaction_type', 'txn_type'],
}


def _resolve_csv_headers(fieldnames):
    """
    Map the actual CSV header names to canonical keys.
    Returns a dict: {canonical_key: actual_header} for found columns.
    """
    lower_map = {h.strip().lower(): h for h in (fieldnames or [])}
    resolved = {}
    for canonical, aliases in _CSV_COL_ALIASES.items():
        for alias in aliases:
            if alias in lower_map:
                resolved[canonical] = lower_map[alias]
                break
    return resolved


def _parse_decimal(raw):
    """Parse a decimal value, returning Decimal('0.00') for blank/None."""
    if not raw:
        return Decimal('0.00')
    cleaned = raw.strip().replace(',', '').replace(' ', '')
    if not cleaned:
        return Decimal('0.00')
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal('0.00')


class BankStatementViewSet(viewsets.ViewSet):
    """
    Endpoints for importing and listing bank statements.

    POST /api/accounting/bank-statements/import/
        Upload a CSV file to create a BankStatement + BankStatementLine records.

    GET  /api/accounting/bank-statements/
        List all bank statements with summary info.

    GET  /api/accounting/bank-statements/{id}/lines/
        List all lines for a specific statement (with match_status filter).
    """

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def list(self, request):
        """List all bank statements, newest first."""
        bank_account_id = request.query_params.get('bank_account')
        qs = BankStatement.objects.select_related('bank_account', 'imported_by').order_by('-statement_date')
        if bank_account_id:
            qs = qs.filter(bank_account_id=bank_account_id)

        data = [
            {
                'id': s.id,
                'bank_account': s.bank_account_id,
                'bank_account_name': str(s.bank_account),
                'statement_number': s.statement_number,
                'statement_date': str(s.statement_date),
                'start_date': str(s.start_date),
                'end_date': str(s.end_date),
                'opening_balance': str(s.opening_balance),
                'closing_balance': str(s.closing_balance),
                'currency_code': s.currency_code,
                'status': s.status,
                'file_name': s.file_name,
                'import_date': s.import_date.isoformat() if s.import_date else None,
                'imported_by': s.imported_by.get_full_name() if s.imported_by else None,
                'line_count': s.lines.count(),
                'unmatched_count': s.lines.filter(match_status='UNMATCHED').count(),
            }
            for s in qs
        ]
        return api_response(data=data, meta={'total': len(data)})

    @action(detail=True, methods=['get'])
    def lines(self, request, pk=None):
        """List all lines for a specific bank statement."""
        try:
            statement = BankStatement.objects.get(pk=pk)
        except BankStatement.DoesNotExist:
            return api_response(error='Statement not found.', status=status.HTTP_404_NOT_FOUND)

        match_status = request.query_params.get('match_status')
        qs = statement.lines.all()
        if match_status:
            qs = qs.filter(match_status=match_status.upper())

        data = [
            {
                'id': line.id,
                'line_number': line.line_number,
                'transaction_date': str(line.transaction_date),
                'value_date': str(line.value_date) if line.value_date else None,
                'description': line.description,
                'reference': line.reference,
                'debit_amount': str(line.debit_amount),
                'credit_amount': str(line.credit_amount),
                'balance': str(line.balance),
                'transaction_type': line.transaction_type,
                'match_status': line.match_status,
                'matched_transaction_type': line.matched_transaction_type,
                'matched_transaction_id': line.matched_transaction_id,
            }
            for line in qs
        ]
        return api_response(data=data, meta={'statement_id': statement.id, 'total': len(data)})

    @action(detail=False, methods=['post'], url_path='import')
    @transaction.atomic
    def import_csv(self, request):
        """
        Import a CSV bank statement.

        Required form fields:
          - file          : the CSV file upload
          - bank_account  : BankAccount PK
          - statement_number : unique statement reference (e.g. "2024-01")
          - statement_date   : YYYY-MM-DD
          - start_date       : YYYY-MM-DD
          - end_date         : YYYY-MM-DD

        Optional form fields:
          - opening_balance  : decimal (default 0.00)
          - closing_balance  : decimal (default 0.00)
          - currency_code    : 3-letter code (default taken from bank account)
        """
        # ── 1. Validate required fields ──────────────────────────────────────
        required = ['bank_account', 'statement_number', 'statement_date', 'start_date', 'end_date']
        missing = [f for f in required if not request.data.get(f)]
        if missing:
            return api_response(
                error=f"Missing required fields: {', '.join(missing)}",
                status=status.HTTP_400_BAD_REQUEST,
            )

        if 'file' not in request.FILES:
            return api_response(error='No file uploaded. Send the CSV as file.', status=status.HTTP_400_BAD_REQUEST)

        # ── 2. Fetch bank account ─────────────────────────────────────────────
        try:
            bank_account = BankAccount.objects.get(pk=request.data['bank_account'])
        except BankAccount.DoesNotExist:
            return api_response(error='Bank account not found.', status=status.HTTP_400_BAD_REQUEST)

        # ── 3. Check for duplicate statement ─────────────────────────────────
        stmt_number = request.data['statement_number'].strip()
        if BankStatement.objects.filter(bank_account=bank_account, statement_number=stmt_number).exists():
            return api_response(
                error=f"Statement '{stmt_number}' already imported for this bank account.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── 4. Parse the CSV ──────────────────────────────────────────────────
        uploaded_file = request.FILES['file']
        try:
            raw_bytes = uploaded_file.read()
            try:
                text = raw_bytes.decode('utf-8-sig')   # handles BOM from Excel exports
            except UnicodeDecodeError:
                text = raw_bytes.decode('latin-1')     # fallback for legacy bank exports
        except Exception as exc:
            return api_response(error=f'Could not read file: {exc}', status=status.HTTP_400_BAD_REQUEST)

        reader = csv.DictReader(io.StringIO(text))
        col_map = _resolve_csv_headers(reader.fieldnames)

        # Validate required CSV columns
        for req_col in ('date', 'description'):
            if req_col not in col_map:
                return api_response(
                    error=(
                        f"CSV is missing a '{req_col}' column. "
                        f"Found columns: {list(reader.fieldnames or [])}"
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ── 5. Create BankStatement header ────────────────────────────────────
        from accounting.utils import get_base_currency_code
        currency_code = (
            request.data.get('currency_code')
            or getattr(bank_account.currency, 'code', None)
            or get_base_currency_code()
        )

        statement = BankStatement.objects.create(
            bank_account=bank_account,
            statement_number=stmt_number,
            statement_date=request.data['statement_date'],
            start_date=request.data['start_date'],
            end_date=request.data['end_date'],
            opening_balance=_parse_decimal(request.data.get('opening_balance', '0')),
            closing_balance=_parse_decimal(request.data.get('closing_balance', '0')),
            currency_code=currency_code,
            imported_by=request.user,
            file_name=uploaded_file.name,
            status='IMPORTED',
        )

        # ── 6. Build and bulk-insert statement lines ──────────────────────────
        lines = []
        errors = []
        for line_no, row in enumerate(reader, start=1):
            try:
                raw_date = row.get(col_map['date'], '').strip()
                raw_desc = row.get(col_map['description'], '').strip()

                if not raw_date or not raw_desc:
                    errors.append(f"Row {line_no}: skipped (empty date or description)")
                    continue

                lines.append(BankStatementLine(
                    statement=statement,
                    line_number=line_no,
                    transaction_date=raw_date,
                    value_date=row.get(col_map.get('value_date', ''), '').strip() or None,
                    description=raw_desc,
                    reference=row.get(col_map.get('reference', ''), '').strip(),
                    debit_amount=_parse_decimal(row.get(col_map.get('debit', ''), '')),
                    credit_amount=_parse_decimal(row.get(col_map.get('credit', ''), '')),
                    balance=_parse_decimal(row.get(col_map.get('balance', ''), '')),
                    transaction_type=row.get(col_map.get('type', ''), '').strip(),
                    match_status='UNMATCHED',
                ))
            except Exception as exc:
                errors.append(f"Row {line_no}: {exc}")

        if not lines and not errors:
            # CSV had header only — still valid, just empty
            pass
        elif not lines and errors:
            # Every row failed — roll back the statement header and report
            raise Exception(f"All rows failed to parse: {'; '.join(errors[:5])}")

        if lines:
            BankStatementLine.objects.bulk_create(lines)

        logger.info(
            "Bank statement import: statement=%s bank_account=%s rows=%d warnings=%d user=%s",
            statement.id, bank_account.pk, len(lines), len(errors), request.user,
        )

        return api_response(
            data={
                'statement_id': statement.id,
                'statement_number': statement.statement_number,
                'bank_account': bank_account.pk,
                'rows_imported': len(lines),
                'warnings': errors,
            },
            status=status.HTTP_201_CREATED,
        )
