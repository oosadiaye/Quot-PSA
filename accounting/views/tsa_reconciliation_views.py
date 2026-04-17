"""
Views for TSA Bank Reconciliation
=================================
Three viewsets:

1. ``TSABankStatementViewSet`` — list/retrieve/upload a parsed statement
   and run auto-match.
2. ``TSABankStatementLineViewSet`` — manually link / unlink / ignore a
   line.
3. ``TSAReconciliationViewSet`` — the reconciliation session; start,
   refresh, complete. ``complete`` flags matched PaymentInstruction and
   RevenueCollection rows as reconciled (H1).

Permissions: every action requires ``IsAuthenticated`` *plus* the
``accounting.reconcile_tsa`` model permission (H6) which is granted via
the standard Django permission system.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, MultiPartParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounting.models import (
    TSABankStatement, TSABankStatementLine, TSAReconciliation,
    TreasuryAccount, PaymentInstruction, RevenueCollection,
)
from accounting.serializers_reconciliation import (
    TSABankStatementSerializer,
    TSABankStatementDetailSerializer,
    TSABankStatementLineSerializer,
    TSAReconciliationSerializer,
)
from accounting.services.tsa_bank_reconciliation import (
    parse_statement_file, auto_match_statement,
)


# =============================================================================
# Upload limits
# =============================================================================

# Reject obviously-abusive uploads at the view layer (M4). Real bank
# statements are almost always < 2 MB; we give 10 MB headroom.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {'csv', 'tsv', 'txt'}
ALLOWED_CONTENT_TYPES = {
    'text/csv', 'text/plain', 'text/tab-separated-values',
    'application/csv', 'application/vnd.ms-excel', 'application/octet-stream',
}


# =============================================================================
# Permissions
# =============================================================================

class CanReconcileTSA(IsAuthenticated):
    """Gate for TSA reconciliation actions (H6).

    Any authenticated user with either of these permissions can use the
    endpoints. We accept several granted-name variants so the feature works
    out of the box on existing tenants without needing new permission rows:

    - ``accounting.reconcile_tsa`` (custom permission, preferred)
    - ``accounting.change_tsareconciliation`` (auto-granted to staff)
    - ``accounting.add_tsareconciliation``
    - superuser / staff-user bypass
    """

    _ACCEPTED_PERMS = (
        'accounting.reconcile_tsa',
        'accounting.change_tsareconciliation',
        'accounting.add_tsareconciliation',
    )

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or user.is_staff:
            return True
        return any(user.has_perm(p) for p in self._ACCEPTED_PERMS)


# =============================================================================
# Helpers
# =============================================================================

def _validate_upload(uploaded_file):
    """Reject files that don't look like CSVs (M4). Returns a dict of errors
    if invalid, or empty dict if OK."""
    if not uploaded_file:
        return {'statement_file': 'Please attach a CSV or TSV file.'}

    size = getattr(uploaded_file, 'size', 0)
    if size and size > MAX_UPLOAD_BYTES:
        mb = size / 1024 / 1024
        return {
            'statement_file': (
                f'File is {mb:.1f} MB — exceeds the 10 MB upload limit. '
                'Split the statement into smaller periods and try again.'
            ),
        }

    name = (getattr(uploaded_file, 'name', '') or '').lower()
    ext = name.rsplit('.', 1)[-1] if '.' in name else ''
    if ext and ext not in ALLOWED_EXTENSIONS:
        return {
            'statement_file': (
                f'File extension ".{ext}" is not supported. '
                'Upload a .csv, .tsv, or .txt file.'
            ),
        }

    content_type = (getattr(uploaded_file, 'content_type', '') or '').lower()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        # Browsers sometimes send odd types (e.g. Firefox sends
        # application/octet-stream for .csv on Windows) — we accept those too
        # above, but this catches anything actually unusual.
        if ext not in ALLOWED_EXTENSIONS:
            return {
                'statement_file': (
                    f'File type "{content_type}" is not a supported format.'
                ),
            }

    return {}


def _compute_book_balance_at(tsa: TreasuryAccount, as_of):
    """
    Book balance as of the end of a given day (H5).

    Starts from ``tsa.current_balance`` and backs out every movement after
    ``as_of``. Same algorithm as the ledger endpoint's opening-balance
    calculation — just anchored to a different date.
    """
    if as_of is None:
        return tsa.current_balance or Decimal('0')

    out_since = PaymentInstruction.objects.filter(
        tsa_account=tsa, status='PROCESSED',
        processed_at__date__gt=as_of,
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0')

    in_since_val = RevenueCollection.objects.filter(
        tsa_account=tsa, status__in=['POSTED', 'RECONCILED'],
        value_date__gt=as_of,
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0')

    in_since_col = RevenueCollection.objects.filter(
        tsa_account=tsa, status__in=['POSTED', 'RECONCILED'],
        value_date__isnull=True, collection_date__gt=as_of,
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0')

    current = tsa.current_balance or Decimal('0')
    return current + out_since - in_since_val - in_since_col


# =============================================================================
# Bank Statement Import
# =============================================================================

class TSABankStatementViewSet(viewsets.ModelViewSet):
    """
    List / retrieve / upload bank statements.

    ``POST /api/v1/accounting/tsa-bank-statements/`` with multipart fields:
        tsa_account      — TSA id
        statement_file   — the CSV/TSV file
        opening_balance  — optional opening balance (defaults to 0)
    """
    permission_classes = [CanReconcileTSA]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['tsa_account', 'status']
    search_fields = ['original_filename', 'tsa_account__account_number']
    ordering_fields = ['created_at', 'statement_to']
    ordering = ['-created_at']

    def get_queryset(self):
        """Annotate match counts once per query to avoid N+1 (M1)."""
        return (
            TSABankStatement.objects
            .select_related('tsa_account', 'uploaded_by')
            .annotate(
                annotated_matched_count=Count(
                    'lines',
                    filter=~Q(lines__match_status='UNMATCHED')
                    & ~Q(lines__match_status='IGNORED'),
                ),
                annotated_unmatched_count=Count(
                    'lines', filter=Q(lines__match_status='UNMATCHED'),
                ),
                annotated_ignored_count=Count(
                    'lines', filter=Q(lines__match_status='IGNORED'),
                ),
            )
        )

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return TSABankStatementDetailSerializer
        return TSABankStatementSerializer

    def create(self, request, *args, **kwargs):
        """Upload + parse a bank statement file (M4 size/type guarded)."""
        tsa_id = request.data.get('tsa_account')
        upload = request.FILES.get('statement_file')
        opening_raw = request.data.get('opening_balance') or '0'

        if not tsa_id:
            return Response(
                {'tsa_account': 'TSA account is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        validation_errors = _validate_upload(upload)
        if validation_errors:
            return Response(validation_errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            tsa = TreasuryAccount.objects.get(pk=tsa_id)
        except TreasuryAccount.DoesNotExist:
            return Response(
                {'tsa_account': 'TSA account not found.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            opening_balance = Decimal(str(opening_raw)) if opening_raw else Decimal('0')
        except Exception:
            opening_balance = Decimal('0')

        try:
            header = parse_statement_file(
                tsa_account=tsa,
                uploaded_file=upload,
                opening_balance=opening_balance,
                uploaded_by=request.user if request.user.is_authenticated else None,
            )
        except ValueError as exc:
            return Response(
                {'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TSABankStatementDetailSerializer(
            header, context={'request': request},
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def auto_match(self, request, pk=None):
        """Run the auto-matcher (H3 serialised under row lock)."""
        stmt = self.get_object()
        if stmt.status == 'COMPLETED':
            return Response(
                {
                    'detail': (
                        'This statement is part of a completed reconciliation '
                        'and cannot be re-matched.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = auto_match_statement(
            stmt, actor=request.user if request.user.is_authenticated else None,
        )
        return Response({
            'statement_id': stmt.id,
            'result': result,
        })

    @action(detail=True, methods=['get'])
    def lines(self, request, pk=None):
        """List this statement's lines — used by the match/review UI."""
        stmt = self.get_object()
        match_status_filter = request.query_params.get('match_status')
        qs = stmt.lines.all()
        if match_status_filter:
            qs = qs.filter(match_status=match_status_filter)
        serializer = TSABankStatementLineSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def candidates(self, request, pk=None):
        """Unmatched book-side candidates within this statement's window."""
        stmt = self.get_object()
        window_start = stmt.statement_from - timedelta(days=5)
        window_end = stmt.statement_to + timedelta(days=5)

        claimed_payments = set(
            TSABankStatementLine.objects
            .filter(matched_payment__isnull=False)
            .values_list('matched_payment_id', flat=True)
        )
        claimed_revenues = set(
            TSABankStatementLine.objects
            .filter(matched_revenue__isnull=False)
            .values_list('matched_revenue_id', flat=True)
        )

        payments = PaymentInstruction.objects.filter(
            tsa_account=stmt.tsa_account,
            status='PROCESSED',
            processed_at__date__gte=window_start,
            processed_at__date__lte=window_end,
        ).exclude(id__in=claimed_payments).select_related('payment_voucher')

        revenues = RevenueCollection.objects.filter(
            tsa_account=stmt.tsa_account,
            status__in=['POSTED', 'RECONCILED'],
            collection_date__gte=window_start,
            collection_date__lte=window_end,
        ).exclude(id__in=claimed_revenues)

        return Response({
            'payments': [
                {
                    'id': p.id,
                    'reference': (
                        p.bank_reference
                        or (p.payment_voucher.voucher_number if p.payment_voucher_id else '')
                        or p.batch_reference
                        or f'PI-{p.id}'
                    ),
                    'date': p.processed_at.date() if p.processed_at else None,
                    'amount': p.amount,
                    'beneficiary': p.beneficiary_name,
                    'narration': p.narration,
                }
                for p in payments
            ],
            'revenues': [
                {
                    'id': r.id,
                    'reference': r.payment_reference or r.rrr,
                    'date': r.value_date or r.collection_date,
                    'amount': r.amount,
                    'payer': r.payer_name,
                }
                for r in revenues
            ],
        })

    @action(detail=False, methods=['get'], url_path='sample-csv')
    def sample_csv(self, request):
        """Return a minimal sample CSV for users to model their uploads on
        (M5). Served inline, so the browser will either preview or download
        depending on headers."""
        from django.http import HttpResponse
        csv_body = (
            'date,description,reference,debit,credit,balance\n'
            '2026-04-10,Salary Apr 2026,BATCH-APR-01,1500000,,8500000\n'
            '2026-04-11,IGR - MOH,RRR1234567,,250000,8750000\n'
            '2026-04-12,NIBSS SMS Charge,CHG-2026-04,250,,8749750\n'
            '2026-04-15,Contractor Payment,PV-2026-00042,530000,,8219750\n'
        )
        response = HttpResponse(csv_body, content_type='text/csv')
        response['Content-Disposition'] = (
            'attachment; filename="tsa-statement-sample.csv"'
        )
        return response


# =============================================================================
# Bank Statement Line — manual match / unmatch / ignore
# =============================================================================

class TSABankStatementLineViewSet(viewsets.ReadOnlyModelViewSet):
    """Read + custom match/unmatch/ignore actions on a single parsed line."""
    serializer_class = TSABankStatementLineSerializer
    permission_classes = [CanReconcileTSA]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['statement', 'match_status']

    def get_queryset(self):
        return TSABankStatementLine.objects.select_related(
            'statement', 'matched_payment__payment_voucher', 'matched_revenue',
            'matched_by',
        )

    def _locked_line(self, pk):
        """Fetch the line with a row-level lock so concurrent match/unmatch
        can't race on the same row."""
        return TSABankStatementLine.objects.select_for_update().get(pk=pk)

    @action(detail=True, methods=['post'])
    def match(self, request, pk=None):
        """Manually link a line to a PaymentInstruction or RevenueCollection.

        Body:
            { "payment_id": 12 } or { "revenue_id": 34 }

        Rejects if the target is already linked to another line (H4).
        """
        payment_id = request.data.get('payment_id')
        revenue_id = request.data.get('revenue_id')

        if not payment_id and not revenue_id:
            return Response(
                {'detail': 'Provide payment_id or revenue_id.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if payment_id and revenue_id:
            return Response(
                {'detail': 'Provide only one of payment_id or revenue_id.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            line = self._locked_line(pk)

            if line.statement.status == 'COMPLETED':
                return Response(
                    {'detail': 'Statement is completed and cannot be modified.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if payment_id:
                try:
                    pi = PaymentInstruction.objects.get(
                        pk=payment_id,
                        tsa_account=line.statement.tsa_account,
                    )
                except PaymentInstruction.DoesNotExist:
                    return Response(
                        {'detail': 'Payment not found on this TSA.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # H4: candidate must not already be linked to another line.
                clash = (
                    TSABankStatementLine.objects
                    .filter(matched_payment=pi)
                    .exclude(pk=line.pk)
                    .first()
                )
                if clash:
                    return Response(
                        {
                            'detail': (
                                'This payment is already linked to statement '
                                f'line {clash.line_number} on statement '
                                f'"{clash.statement.original_filename}". '
                                'Unlink that line first.'
                            ),
                            'blocking_line_id': clash.id,
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                line.matched_payment = pi
                line.matched_revenue = None
            else:
                try:
                    rc = RevenueCollection.objects.get(
                        pk=revenue_id,
                        tsa_account=line.statement.tsa_account,
                    )
                except RevenueCollection.DoesNotExist:
                    return Response(
                        {'detail': 'Revenue collection not found on this TSA.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                clash = (
                    TSABankStatementLine.objects
                    .filter(matched_revenue=rc)
                    .exclude(pk=line.pk)
                    .first()
                )
                if clash:
                    return Response(
                        {
                            'detail': (
                                'This revenue collection is already linked to '
                                f'statement line {clash.line_number} on '
                                f'"{clash.statement.original_filename}". '
                                'Unlink that line first.'
                            ),
                            'blocking_line_id': clash.id,
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                line.matched_revenue = rc
                line.matched_payment = None

            line.match_status = 'MANUAL'
            line.match_confidence = Decimal('100')
            line.matched_by = request.user if request.user.is_authenticated else None
            line.matched_at = timezone.now()
            line.save(update_fields=[
                'matched_payment', 'matched_revenue',
                'match_status', 'match_confidence',
                'matched_by', 'matched_at', 'updated_at',
            ])

        return Response(TSABankStatementLineSerializer(line).data)

    @action(detail=True, methods=['post'])
    def unmatch(self, request, pk=None):
        """Clear the match on a line — sends it back to UNMATCHED."""
        with transaction.atomic():
            line = self._locked_line(pk)
            if line.statement.status == 'COMPLETED':
                return Response(
                    {'detail': 'Statement is completed and cannot be modified.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            line.matched_payment = None
            line.matched_revenue = None
            line.match_status = 'UNMATCHED'
            line.match_confidence = Decimal('0')
            line.matched_by = None
            line.matched_at = None
            line.save(update_fields=[
                'matched_payment', 'matched_revenue',
                'match_status', 'match_confidence',
                'matched_by', 'matched_at', 'updated_at',
            ])
        return Response(TSABankStatementLineSerializer(line).data)

    @action(detail=True, methods=['post'])
    def ignore(self, request, pk=None):
        """Mark a statement line as intentionally ignored (M7).

        Used for bank-side items that have no book entry (SMS fees, stamp
        duty) and shouldn't be auto-matched or flagged as unreconciled.
        """
        with transaction.atomic():
            line = self._locked_line(pk)
            if line.statement.status == 'COMPLETED':
                return Response(
                    {'detail': 'Statement is completed and cannot be modified.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            line.matched_payment = None
            line.matched_revenue = None
            line.match_status = 'IGNORED'
            line.match_confidence = Decimal('0')
            line.matched_by = request.user if request.user.is_authenticated else None
            line.matched_at = timezone.now()
            line.save(update_fields=[
                'matched_payment', 'matched_revenue',
                'match_status', 'match_confidence',
                'matched_by', 'matched_at', 'updated_at',
            ])
        return Response(TSABankStatementLineSerializer(line).data)


# =============================================================================
# Reconciliation Session
# =============================================================================

class TSAReconciliationViewSet(viewsets.ModelViewSet):
    """
    Create / list / complete reconciliation sessions per TSA.

    On create we compute:
      - book_balance via ``_compute_book_balance_at(period_end)`` (H5)
      - statement_balance from the linked TSABankStatement (if any)
      - unmatched totals from the statement lines

    On complete we flag matched PaymentInstruction / RevenueCollection rows
    as reconciled (H1) and lock the statement.
    """
    serializer_class = TSAReconciliationSerializer
    permission_classes = [CanReconcileTSA]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['tsa_account', 'status']
    ordering_fields = ['period_end', 'created_at']
    ordering = ['-period_end']

    def get_permissions(self):
        # S7-01 — Completing a reconciliation flags every matched
        # PaymentInstruction/RevenueCollection as reconciled. That's
        # an irreversible audit event — MFA required.
        from accounting.permissions import RequiresMFA
        if self.action == 'complete':
            return [CanReconcileTSA(), RequiresMFA()]
        return super().get_permissions()

    def get_queryset(self):
        return TSAReconciliation.objects.select_related(
            'tsa_account', 'completed_by', 'statement_import',
        )

    def perform_create(self, serializer):
        tsa: TreasuryAccount = serializer.validated_data['tsa_account']
        period_end = serializer.validated_data.get('period_end')
        stmt: TSABankStatement | None = serializer.validated_data.get(
            'statement_import'
        )

        # H5: book balance as at period_end, not today.
        book_balance = _compute_book_balance_at(tsa, period_end)
        statement_balance = (
            stmt.closing_balance if stmt else book_balance
        )

        unmatched_debits = Decimal('0')
        unmatched_credits = Decimal('0')
        if stmt:
            for line in stmt.lines.filter(match_status='UNMATCHED'):
                unmatched_debits += line.debit or Decimal('0')
                unmatched_credits += line.credit or Decimal('0')

        adjusted = book_balance + unmatched_credits - unmatched_debits

        serializer.save(
            book_balance=book_balance,
            statement_balance=statement_balance,
            adjusted_balance=adjusted,
            unmatched_debits=unmatched_debits,
            unmatched_credits=unmatched_credits,
        )

    def create(self, request, *args, **kwargs):
        """Handle the unique-constraint clash (same TSA + period) cleanly."""
        try:
            return super().create(request, *args, **kwargs)
        except Exception as exc:  # IntegrityError from uniq constraint
            if 'uniq_tsa_recon_period' in str(exc):
                return Response(
                    {
                        'detail': (
                            'A reconciliation for this TSA and period already '
                            'exists. Open the existing session instead of '
                            'creating a new one.'
                        ),
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            raise

    @action(detail=True, methods=['post'])
    def refresh(self, request, pk=None):
        """Recalculate balances — call after manual matching."""
        recon: TSAReconciliation = self.get_object()
        if recon.status == 'COMPLETED':
            return Response(
                {'detail': 'Reconciliation is already completed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        stmt = recon.statement_import
        recon.book_balance = _compute_book_balance_at(
            recon.tsa_account, recon.period_end,
        )
        recon.statement_balance = (
            stmt.closing_balance if stmt else recon.book_balance
        )
        unmatched_debits = Decimal('0')
        unmatched_credits = Decimal('0')
        if stmt:
            for line in stmt.lines.filter(match_status='UNMATCHED'):
                unmatched_debits += line.debit or Decimal('0')
                unmatched_credits += line.credit or Decimal('0')
        recon.unmatched_debits = unmatched_debits
        recon.unmatched_credits = unmatched_credits
        recon.adjusted_balance = (
            recon.book_balance + unmatched_credits - unmatched_debits
        )
        recon.save()
        return Response(TSAReconciliationSerializer(recon).data)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Close the session and flag matched book records (H1)."""
        recon: TSAReconciliation = self.get_object()
        if recon.status == 'COMPLETED':
            return Response(
                {'detail': 'Already completed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        force = request.data.get('force') in (True, 'true', 1, '1')
        if abs(recon.difference) > Decimal('0.01') and not force:
            return Response(
                {
                    'detail': (
                        f'Book vs statement differ by {recon.difference}. '
                        'Pass {"force": true} to complete anyway, or match '
                        'the remaining unmatched lines first.'
                    ),
                    'difference': str(recon.difference),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            # Lock the recon row.
            recon = (
                TSAReconciliation.objects
                .select_for_update()
                .get(pk=recon.pk)
            )
            if recon.status == 'COMPLETED':
                return Response(
                    {'detail': 'Already completed.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            recon.status = 'COMPLETED'
            recon.completed_at = timezone.now()
            recon.completed_by = (
                request.user if request.user.is_authenticated else None
            )
            recon.save(update_fields=['status', 'completed_at', 'completed_by'])

            # H1 — flag matched book records as reconciled.
            if recon.statement_import_id:
                matched_lines = TSABankStatementLine.objects.filter(
                    statement_id=recon.statement_import_id,
                    match_status__in=['AUTO', 'MANUAL'],
                )
                matched_payment_ids = [
                    l.matched_payment_id for l in matched_lines if l.matched_payment_id
                ]
                matched_revenue_ids = [
                    l.matched_revenue_id for l in matched_lines if l.matched_revenue_id
                ]
                if matched_payment_ids:
                    PaymentInstruction.objects.filter(
                        id__in=matched_payment_ids,
                    ).update(
                        is_reconciled=True,
                        reconciliation=recon,
                    )
                if matched_revenue_ids:
                    RevenueCollection.objects.filter(
                        id__in=matched_revenue_ids,
                    ).update(
                        is_reconciled=True,
                        reconciliation=recon,
                    )

                # Lock the statement from further edits.
                TSABankStatement.objects.filter(
                    pk=recon.statement_import_id,
                ).update(status='COMPLETED')

        return Response(TSAReconciliationSerializer(recon).data)
