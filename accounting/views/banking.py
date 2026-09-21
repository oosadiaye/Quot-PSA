import csv
import io
import logging
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import transaction
from django.utils import timezone
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
        # TSA → BankAccount mirrors are kept in lockstep by the
        # ``post_save`` signal in ``accounting/signals/tsa_bank_mirror.py``.
        # The previous in-line sync here ran on every list GET, which
        # broke HTTP idempotency (writes from a read endpoint) and made
        # the response slow on tenants with many TSAs. Existing tenants
        # are already backfilled; new TSAs are mirrored on save.
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

    @action(detail=False, methods=['post'])
    def transfer(self, request):
        """Atomic inter-bank transfer between two BankAccount rows.

        H10 fix: prior to this, no atomic 2-leg path existed for moving
        money between own bank accounts. Operators had to post raw JVs
        and manually adjust ``BankAccount.current_balance`` on each side
        (or the cash position drifted). The TSA cash-sweep path covers
        only TSA accounts.

        Body:
          - source_bank_account_id (int, required)
          - target_bank_account_id (int, required)
          - amount (decimal, required, > 0)
          - transfer_date (date, optional — defaults to today)
          - reference (str, optional — appears on the journal memo)

        Posts:
          DR  target_bank_account.gl_account   amount
          CR  source_bank_account.gl_account   amount

        via IPSASJournalService.post_journal so the chokepoint
        (assert_balanced + invalidate_period_reports + GLBalance roll-up)
        fires; F()-decrements source.current_balance and F()-increments
        target.current_balance under SELECT FOR UPDATE on both rows
        (locked in pk-order to avoid deadlock).
        """
        source_id = request.data.get('source_bank_account_id')
        target_id = request.data.get('target_bank_account_id')
        raw_amount = request.data.get('amount')
        if not (source_id and target_id and raw_amount):
            return Response(
                {'error': 'source_bank_account_id, target_bank_account_id and amount are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            source_id = int(source_id)
            target_id = int(target_id)
        except (TypeError, ValueError):
            return Response(
                {'error': 'Bank account ids must be integers.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if source_id == target_id:
            return Response(
                {'error': 'Source and target bank accounts must differ.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            amount = Decimal(str(raw_amount))
        except (InvalidOperation, ValueError):
            return Response(
                {'error': 'amount must be a decimal value.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount <= Decimal('0'):
            return Response(
                {'error': 'amount must be greater than zero.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from datetime import date as _date
        from django.db.models import F as _F
        from django.utils import timezone
        from accounting.models import JournalHeader, JournalLine, TransactionSequence
        from accounting.services.ipsas_journal_service import IPSASJournalService

        transfer_date = request.data.get('transfer_date') or _date.today().isoformat()
        reference = (request.data.get('reference') or '').strip()

        # Lock both rows in pk-order to avoid deadlocks under concurrent
        # opposite-direction transfers.
        first_id, second_id = sorted([source_id, target_id])
        with transaction.atomic():
            locked = list(
                BankAccount.objects.select_for_update()
                .select_related('gl_account')
                .filter(pk__in=[first_id, second_id])
                .order_by('pk')
            )
            if len(locked) != 2:
                return Response(
                    {'error': 'One or both bank accounts not found.'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            by_id = {ba.pk: ba for ba in locked}
            source = by_id[source_id]
            target = by_id[target_id]

            if not source.gl_account or not target.gl_account:
                return Response(
                    {'error': 'Both bank accounts must have a configured gl_account.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Sufficient-funds guard. We don't allow inter-bank transfers
            # to overdraw a source account from this endpoint — operators
            # who genuinely need overdraft transfers should use a JV with
            # appropriate authorisation.
            if source.current_balance < amount:
                return Response(
                    {'error': (
                        f"Insufficient funds in source account "
                        f"({source.current_balance} < {amount})."
                    )},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            jv_ref = (
                reference or
                f"BT-{TransactionSequence.get_next('bank_transfer', 'BT-')}"
            )
            journal = JournalHeader.objects.create(
                posting_date=transfer_date,
                reference_number=jv_ref,
                description=(
                    f"Bank transfer {source.name} → {target.name} "
                    f"({reference})" if reference else
                    f"Bank transfer {source.name} → {target.name}"
                ),
                status='Draft',
                source_module='banking',
                posted_by=request.user,
            )
            JournalLine.objects.create(
                header=journal,
                account=target.gl_account,
                debit=amount,
                credit=Decimal('0'),
                memo=f"Transfer in from {source.name}",
            )
            JournalLine.objects.create(
                header=journal,
                account=source.gl_account,
                debit=Decimal('0'),
                credit=amount,
                memo=f"Transfer out to {target.name}",
            )

            # Post via the chokepoint — assert_balanced + cache invalidation.
            IPSASJournalService.post_journal(journal, request.user)

            # F()-update both bank-account balances under the same atomic.
            BankAccount.objects.filter(pk=source_id).update(
                current_balance=_F('current_balance') - amount,
                updated_at=timezone.now(),
            )
            BankAccount.objects.filter(pk=target_id).update(
                current_balance=_F('current_balance') + amount,
                updated_at=timezone.now(),
            )

        return Response({
            'status': 'transferred',
            'journal_id': journal.pk,
            'journal_reference': journal.reference_number,
            'amount': str(amount),
        }, status=status.HTTP_201_CREATED)


class CheckbookViewSet(viewsets.ModelViewSet):
    queryset = Checkbook.objects.all().select_related('bank_account')
    serializer_class = CheckbookSerializer
    filterset_fields = ['bank_account', 'status']


class CheckViewSet(viewsets.ModelViewSet):
    queryset = Check.objects.all().select_related('checkbook', 'payment')
    serializer_class = CheckSerializer
    filterset_fields = ['checkbook', 'status']

    @action(detail=False, methods=['post'], url_path='create-from-payments')
    def create_from_payments(self, request):
        """Create ONE cheque covering several POSTED payments (Cheque Register).

        Body: ``{check_number, date_issued, payment_ids: [...]}``. Links the
        selected posted payments to a new ``Check`` via ``Payment.cheque``. No
        GL posting — the payments already posted; this records the physical
        cheque issued against them. Guards: payments must be Posted and not
        already on a cheque, and the cheque number must be unique.
        """
        from decimal import Decimal
        from django.db import transaction
        from django.utils.dateparse import parse_date
        from accounting.models.receivables import Payment, Check

        check_number = (request.data.get('check_number') or '').strip()
        if not check_number:
            return Response({'error': 'Cheque number is required.'}, status=status.HTTP_400_BAD_REQUEST)
        raw_date = request.data.get('date_issued')
        date_issued = parse_date(raw_date) if raw_date else None

        ids = request.data.get('payment_ids') or []
        if not ids:
            return Response({'error': 'Select at least one payment for the cheque.'}, status=status.HTTP_400_BAD_REQUEST)

        payments = list(Payment.objects.select_related('vendor', 'bank_account').filter(pk__in=ids))
        if len(payments) != len(set(ids)):
            return Response({'error': 'One or more selected payments were not found.'}, status=status.HTTP_400_BAD_REQUEST)
        for p in payments:
            if p.status != 'Posted':
                return Response({'error': f'Payment {p.payment_number} is not posted — only posted payments can go on a cheque.'}, status=status.HTTP_400_BAD_REQUEST)
            if p.cheque_id:
                return Response({'error': f'Payment {p.payment_number} is already on a cheque.'}, status=status.HTTP_400_BAD_REQUEST)
        if Check.objects.filter(check_number=check_number).exists():
            return Response({'error': f'Cheque number {check_number} already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        amount = sum((p.total_amount or Decimal('0') for p in payments), Decimal('0'))
        vendor_ids = {p.vendor_id for p in payments}
        payee = (payments[0].vendor.name if (len(vendor_ids) == 1 and payments[0].vendor) else 'Multiple')

        with transaction.atomic():
            check = Check.objects.create(
                check_number=check_number,
                date_issued=date_issued,
                amount=amount,
                payee=payee[:200],
                status='Issued',
            )
            Payment.objects.filter(pk__in=[p.pk for p in payments]).update(cheque=check)
        return Response(CheckSerializer(check).data, status=status.HTTP_201_CREATED)


def _post_bank_charges_journal(recon, amount, actor):
    """Post the bank-charges JV during recon completion.

    DR  Bank Charges Expense   amount
    CR  Bank GL (recon's bank) amount

    Bank Charges Expense GL is resolved via:
      1. Account.reconciliation_type='bank_charges' (CoA-portable)
      2. Settings DEFAULT_GL_ACCOUNTS['BANK_CHARGES']
      3. Expense account name matches /bank.charge|service.charge/i

    Posts via IPSASJournalService.post_journal so the chokepoint
    (assert_balanced + invalidate_period_reports + GLBalance roll-up)
    fires. Raises if neither GL leg can be resolved — recon should
    fail closed rather than silently swallow the bank charge.
    """
    from accounting.models import Account, JournalHeader, JournalLine
    from accounting.services.ipsas_journal_service import IPSASJournalService
    from django.conf import settings as dj_settings

    bank_account = recon.bank_account
    bank_gl = bank_account.gl_account
    if bank_gl is None:
        bank_gl = Account.objects.filter(
            reconciliation_type='bank_accounting', is_active=True,
        ).first()
    if bank_gl is None:
        raise ValueError(
            'Cannot post bank charges: no Bank GL account found on the '
            'BankAccount record nor flagged via reconciliation_type=bank_accounting.'
        )

    charges_gl = Account.objects.filter(
        reconciliation_type='bank_charges', is_active=True,
    ).first()
    if charges_gl is None:
        code = (getattr(dj_settings, 'DEFAULT_GL_ACCOUNTS', {}) or {}).get('BANK_CHARGES')
        if code:
            charges_gl = Account.objects.filter(code=code, is_active=True).first()
    if charges_gl is None:
        charges_gl = Account.objects.filter(
            account_type='Expense', is_active=True,
            name__iregex=r'bank.charge|service.charge|account.maintenance',
        ).first()
    if charges_gl is None:
        raise ValueError(
            'Cannot post bank charges: no Bank Charges Expense GL found. '
            "Configure an Expense account with reconciliation_type='bank_charges' "
            "OR set DEFAULT_GL_ACCOUNTS['BANK_CHARGES']."
        )

    journal = JournalHeader.objects.create(
        posting_date=recon.reconciliation_date if hasattr(recon, 'reconciliation_date') else None,
        reference_number=f"BR-{recon.pk}-CHARGES",
        description=f"Bank charges from reconciliation #{recon.pk} on {bank_account.name}",
        status='Draft',
        source_module='banking',
        source_document_id=recon.pk,
        posted_by=actor,
    )
    JournalLine.objects.create(
        header=journal, account=charges_gl,
        debit=amount, credit=Decimal('0'),
        memo=f"Bank charges — {bank_account.name}",
    )
    JournalLine.objects.create(
        header=journal, account=bank_gl,
        debit=Decimal('0'), credit=amount,
        memo=f"Bank charges debit — {bank_account.name}",
    )
    IPSASJournalService.post_journal(journal, actor)

    # Keep BankAccount.current_balance in sync with the new credit.
    from django.db.models import F as _F
    from django.utils import timezone
    BankAccount.objects.filter(pk=bank_account.pk).update(
        current_balance=_F('current_balance') - amount,
        updated_at=timezone.now(),
    )


class BankReconciliationViewSet(viewsets.ModelViewSet):
    queryset = BankReconciliation.objects.all().select_related('bank_account', 'reconciled_by', 'approved_by')
    serializer_class = BankReconciliationSerializer
    filterset_fields = ['bank_account', 'status']

    @action(detail=True, methods=['post'])
    def reconcile(self, request, pk=None):
        """Complete a bank reconciliation.

        M8 fix: previous code did ``book_balance + deposits_in_transit
        - outstanding_checks - bank_charges`` mixing Decimal (book) and
        floats (JSON-decoded inputs). Python silently downgraded the
        whole expression to float — money math via float is a money bug
        waiting to happen. All inputs are now coerced to ``Decimal`` at
        the boundary.

        M8 fix #2: when ``bank_charges > 0`` we now post a balanced
        JV (DR Bank Charges Expense / CR Bank GL) so the GL reflects
        the charge the operator entered during recon. Without this the
        bank ledger drifts from the GL by exactly bank_charges every
        time recon runs.
        """
        recon = self.get_object()

        def _coerce(raw, default='0'):
            try:
                return Decimal(str(raw if raw is not None else default))
            except (InvalidOperation, ValueError):
                return Decimal(default)

        book_balance = recon.bank_account.current_balance  # already Decimal

        deposits_in_transit = _coerce(request.data.get('deposits_in_transit'))
        outstanding_checks = _coerce(request.data.get('outstanding_checks'))
        bank_charges = _coerce(request.data.get('bank_charges'))

        reconciled_balance = (
            book_balance + deposits_in_transit - outstanding_checks - bank_charges
        )
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

            # M8: book the bank-charge expense to GL if any. Done inside
            # the same atomic so a recon that "finds" a bank charge
            # leaves both the recon record AND the GL in sync.
            if bank_charges > Decimal('0'):
                _post_bank_charges_journal(recon, bank_charges, request.user)

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

    # ── AI assistance over the unmatched residue ────────────────────────
    #
    # Two endpoints, and the split is the whole design. ``ai_suggest``
    # proposes and writes nothing. ``accept_suggestion`` is where a named
    # officer decides, and it is the only one that touches a match.

    def _ai_setting(self):
        """The tenant's reconciliation capability, or None.

        Returns None rather than raising when AI is not configured: a
        reconciliation screen must keep working for the many tenants that
        never switch this on.
        """
        from django.db import connection

        from superadmin.ai_models import AICapability, TenantAISetting

        tenant = getattr(connection, 'tenant', None)
        if tenant is None or getattr(tenant, 'schema_name', 'public') == 'public':
            return None, None
        setting = (
            TenantAISetting.objects
            .select_related('provider')
            .filter(tenant=tenant, capability=AICapability.RECONCILIATION)
            .first()
        )
        return tenant, setting

    @action(detail=True, methods=['post'], url_path='ai-suggest')
    def ai_suggest(self, request, pk=None):
        """Propose explanations for lines the rule matcher could not match.

        Read-only with respect to the ledger. Bounded by ``limit`` because
        each line is its own provider round trip, and a thousand-line
        statement should not become a thousand calls because someone
        clicked a button.
        """
        from accounting.services.ai_reconciliation import propose_for_line

        try:
            statement = BankStatement.objects.get(pk=pk)
        except BankStatement.DoesNotExist:
            return api_response(error='Statement not found.', status=status.HTTP_404_NOT_FOUND)

        tenant, setting = self._ai_setting()
        if setting is None:
            return api_response(
                error='AI reconciliation is not enabled for this organisation.',
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not setting.is_usable:
            # Fail closed, and say which switch is off rather than
            # returning an empty result that reads like "nothing to find".
            return api_response(
                error=(
                    'AI reconciliation is configured but not active. Check the '
                    'capability toggle and that its provider has a key.'
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            limit = min(int(request.data.get('limit', 10)), 25)
        except (TypeError, ValueError):
            limit = 10

        line_ids = request.data.get('line_ids') or []
        qs = statement.lines.filter(match_status='UNMATCHED')
        if line_ids:
            qs = qs.filter(id__in=line_ids)

        results = [
            propose_for_line(
                tenant=tenant,
                setting=setting,
                line=line,
                bank_account_id=statement.bank_account_id,
            )
            for line in qs[:limit]
        ]
        return api_response(data=results, meta={
            'statement_id': statement.id,
            'lines_examined': len(results),
            'unmatched_remaining': statement.lines.filter(match_status='UNMATCHED').count(),
        })

    @action(detail=True, methods=['post'], url_path='accept-suggestion')
    @transaction.atomic
    def accept_suggestion(self, request, pk=None):
        """Record a match a person has accepted.

        The posted proposal is **re-validated against current data**, not
        trusted. Between the suggestion being displayed and the click,
        another line may have claimed one of the vouchers, or a payment
        may have been voided — so the ids, the direction, the exclusivity
        and above all the arithmetic are all recomputed here. A round trip
        through a browser is not a reason to believe something.
        """
        from accounting.services.ai_reconciliation import (
            Proposal, gather_candidates, to_line_record, validate_proposal,
        )

        try:
            statement = BankStatement.objects.get(pk=pk)
        except BankStatement.DoesNotExist:
            return api_response(error='Statement not found.', status=status.HTTP_404_NOT_FOUND)

        line_id = request.data.get('line_id')
        ids = request.data.get('transaction_ids')
        if not line_id or not isinstance(ids, list) or not ids:
            return api_response(
                error='line_id and a non-empty transaction_ids list are required.',
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            line = statement.lines.select_for_update().get(pk=line_id)
        except BankStatementLine.DoesNotExist:
            return api_response(error='Line not found on this statement.',
                                status=status.HTTP_404_NOT_FOUND)

        if line.match_status != 'UNMATCHED':
            return api_response(
                error=f'That line is already {line.match_status.lower()}.',
                status=status.HTTP_409_CONFLICT,
            )

        record = to_line_record(line)
        candidates = gather_candidates(record, statement.bank_account_id)
        outcome = validate_proposal({'transaction_ids': ids}, record, candidates)
        if not isinstance(outcome, Proposal):
            return api_response(
                error=(
                    'That suggestion is no longer valid: '
                    f'{outcome.reason}. {outcome.detail}'.strip()
                ),
                status=status.HTTP_409_CONFLICT,
            )

        who = request.user.get_full_name() or request.user.get_username()
        line.match_status = 'MANUAL'          # a person decided, not a rule
        line.matched_transaction_type = outcome.transaction_type
        line.matched_transaction_ids = list(outcome.transaction_ids)
        # Kept in step for existing readers that know only about one id.
        line.matched_transaction_id = outcome.transaction_ids[0]
        line.matched_date = timezone.now()
        line.match_note = (
            f'AI-proposed {outcome.kind} accepted by {who}; '
            f'{len(outcome.transaction_ids)} transaction(s) totalling '
            f'{outcome.proposed_total} against a line of {outcome.line_amount} '
            f'(variance {outcome.variance}).'
        )
        line.save(update_fields=[
            'match_status', 'matched_transaction_type', 'matched_transaction_ids',
            'matched_transaction_id', 'matched_date', 'match_note',
        ])

        return api_response(data={
            'line_id': line.id,
            'match_status': line.match_status,
            'transaction_ids': line.matched_transaction_ids,
            'kind': outcome.kind,
            'proposed_total': str(outcome.proposed_total),
            'variance': str(outcome.variance),
            'note': line.match_note,
        })

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
