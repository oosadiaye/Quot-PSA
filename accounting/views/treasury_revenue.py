"""
Treasury & Revenue ViewSets — Quot PSE
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.utils import timezone
from django.db import models
from django.db.models import ProtectedError

from accounting.models.treasury import TreasuryAccount, PaymentVoucherGov, PaymentInstruction
from accounting.models.revenue import RevenueHead, RevenueCollection
from accounting.serializers_treasury import (
    TreasuryAccountSerializer,
    PaymentVoucherSerializer, PaymentVoucherCreateSerializer,
    PaymentInstructionSerializer,
    RevenueHeadSerializer, RevenueCollectionSerializer,
)
from core.mixins import OrganizationFilterMixin


class TreasuryAccountViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    org_filter_admin_field = 'mda'
    """TSA account management — Main TSA, sub-accounts, zero-balance accounts."""
    serializer_class = TreasuryAccountSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['account_type', 'is_active', 'mda']
    search_fields = ['account_number', 'account_name']
    ordering_fields = ['account_number', 'current_balance']
    ordering = ['account_type', 'account_number']

    def get_queryset(self):
        return TreasuryAccount.objects.select_related('mda', 'fund_segment', 'parent_account')

    def destroy(self, request, *args, **kwargs):
        """Delete a TSA account. Returns 400 with a readable message when the
        row is referenced by PVs, child accounts, or other protected FKs.
        """
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError as exc:
            # Summarise what's blocking the delete so the user can act on it.
            blockers = {}
            for obj in exc.protected_objects:
                label = obj._meta.verbose_name_plural or obj._meta.model_name
                blockers[str(label)] = blockers.get(str(label), 0) + 1
            parts = ', '.join(f"{name} ({count})" for name, count in blockers.items())
            return Response(
                {
                    'detail': (
                        f"Cannot delete '{instance.account_name}' because it is "
                        f"referenced by: {parts}. Remove or reassign those records first."
                    ),
                    'blockers': blockers,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'])
    def ledger(self, request, pk=None):
        """
        Bank-statement-style ledger for a TSA account.

        Credits (inflows): posted/processed RevenueCollection rows.
        Debits  (outflows): processed PaymentInstruction rows.

        Query params:
          from  YYYY-MM-DD  optional start date (inclusive)
          to    YYYY-MM-DD  optional end date (inclusive)

        Response shape:
          {
            "account":   {id, account_number, account_name, bank, current_balance},
            "opening_balance": Decimal,
            "closing_balance": Decimal,
            "total_debits":    Decimal,  # outflows in the window
            "total_credits":   Decimal,  # inflows in the window
            "entries": [
               {date, type, reference, narration, counterparty,
                debit, credit, running_balance, source}
            ],
          }
        """
        from datetime import datetime
        from decimal import Decimal
        from django.db.models import Sum
        from accounting.models.revenue import RevenueCollection

        account = self.get_object()

        def _parse_date(value):
            if not value:
                return None
            try:
                return datetime.strptime(value, '%Y-%m-%d').date()
            except (TypeError, ValueError):
                return None

        date_from = _parse_date(request.query_params.get('from'))
        date_to = _parse_date(request.query_params.get('to'))

        # --- Pull movements ---------------------------------------------------
        # Outflows: settled payment instructions. We use processed_at (the
        # actual bank-settlement timestamp) rather than submitted_at because
        # only processed instructions affect the TSA balance.
        outflow_qs = PaymentInstruction.objects.filter(
            tsa_account=account,
            status='PROCESSED',
            processed_at__isnull=False,
        ).select_related('payment_voucher')
        if date_from:
            outflow_qs = outflow_qs.filter(processed_at__date__gte=date_from)
        if date_to:
            outflow_qs = outflow_qs.filter(processed_at__date__lte=date_to)

        # Inflows: revenue collections that have been credited. We accept both
        # POSTED and RECONCILED — anything that's hit the account.
        inflow_qs = RevenueCollection.objects.filter(
            tsa_account=account,
            status__in=['POSTED', 'RECONCILED'],
        ).select_related('revenue_head', 'collecting_mda')
        # Use value_date when available (date funds actually cleared), else
        # fall back to collection_date (when the payer paid).
        if date_from:
            inflow_qs = inflow_qs.filter(
                models.Q(value_date__gte=date_from) |
                models.Q(value_date__isnull=True, collection_date__gte=date_from)
            )
        if date_to:
            inflow_qs = inflow_qs.filter(
                models.Q(value_date__lte=date_to) |
                models.Q(value_date__isnull=True, collection_date__lte=date_to)
            )

        # --- Opening balance --------------------------------------------------
        # Start with the account's current_balance, then back out every
        # movement *within or after* the window. Whatever remains is the
        # balance at the instant before the window begins.
        opening_balance = account.current_balance or Decimal('0')
        if date_from:
            # Back out all movements from date_from onwards.
            out_since = PaymentInstruction.objects.filter(
                tsa_account=account, status='PROCESSED',
                processed_at__date__gte=date_from,
            ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
            in_since_pi = RevenueCollection.objects.filter(
                tsa_account=account, status__in=['POSTED', 'RECONCILED'],
                value_date__gte=date_from,
            ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
            in_since_cd = RevenueCollection.objects.filter(
                tsa_account=account, status__in=['POSTED', 'RECONCILED'],
                value_date__isnull=True, collection_date__gte=date_from,
            ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
            opening_balance = (
                opening_balance + out_since - in_since_pi - in_since_cd
            )

        # --- Build merged, date-ordered entry list ----------------------------
        entries = []
        for pi in outflow_qs:
            entry_date = pi.processed_at.date() if pi.processed_at else None
            entries.append({
                'date': entry_date,
                'type': 'DEBIT',
                'reference': (
                    pi.bank_reference
                    or (pi.payment_voucher.voucher_number if pi.payment_voucher_id else '')
                    or pi.batch_reference
                    or f'PI-{pi.id}'
                ),
                'narration': pi.narration or '',
                'counterparty': pi.beneficiary_name or '',
                'debit': pi.amount,
                'credit': Decimal('0'),
                'source': 'PAYMENT',
                'source_id': pi.id,
            })

        for rc in inflow_qs:
            entry_date = rc.value_date or rc.collection_date
            entries.append({
                'date': entry_date,
                'type': 'CREDIT',
                'reference': rc.payment_reference or rc.rrr or f'RC-{rc.id}',
                'narration': getattr(rc.revenue_head, 'name', '') or '',
                'counterparty': rc.payer_name or '',
                'debit': Decimal('0'),
                'credit': rc.amount,
                'source': 'REVENUE',
                'source_id': rc.id,
            })

        # Chronological; tie-break by source so debits and credits on the same
        # day are deterministically ordered.
        entries.sort(key=lambda e: (e['date'] or datetime.min.date(), e['source']))

        # --- Running balance + totals ----------------------------------------
        running = opening_balance
        total_debits = Decimal('0')
        total_credits = Decimal('0')
        for e in entries:
            running = running + e['credit'] - e['debit']
            e['running_balance'] = running
            total_debits += e['debit']
            total_credits += e['credit']

        return Response({
            'account': {
                'id': account.id,
                'account_number': account.account_number,
                'account_name': account.account_name,
                'bank': account.bank,
                'account_type': account.account_type,
                'current_balance': account.current_balance,
                'mda_name': getattr(account.mda, 'name', None),
            },
            'from': date_from.isoformat() if date_from else None,
            'to': date_to.isoformat() if date_to else None,
            'opening_balance': opening_balance,
            'closing_balance': running,
            'total_debits': total_debits,
            'total_credits': total_credits,
            'entries': entries,
        })

    @action(detail=False, methods=['get'])
    def cash_position(self, request):
        """Real-time TSA cash position summary."""
        from django.db.models import Sum, Count
        qs = TreasuryAccount.objects.filter(is_active=True)
        summary = qs.aggregate(
            total_balance=Sum('current_balance'),
            account_count=Count('id'),
        )
        by_type = list(
            qs.values('account_type')
            .annotate(balance=Sum('current_balance'), count=Count('id'))
            .order_by('account_type')
        )
        return Response({
            'total_balance': summary['total_balance'] or 0,
            'account_count': summary['account_count'] or 0,
            'by_type': by_type,
        })


class PaymentVoucherViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    org_filter_admin_field = 'appropriation__administrative'
    """Government Payment Voucher — create, approve, schedule, pay."""
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'payment_type', 'tsa_account']
    search_fields = ['voucher_number', 'payee_name', 'narration']
    ordering_fields = ['created_at', 'gross_amount', 'voucher_number']
    ordering = ['-created_at']

    def get_permissions(self):
        # S7-01 — MFA-gate the sensitive PV lifecycle actions. Approval,
        # scheduling, and payment are all money-movement events that
        # require a fresh MFA verification on top of normal auth.
        from accounting.permissions import RequiresMFA
        if self.action in ('approve', 'schedule', 'pay', 'reverse', 'cancel'):
            return [perm() for perm in (IsAuthenticated, RequiresMFA)]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentVoucherCreateSerializer
        return PaymentVoucherSerializer

    def get_queryset(self):
        return PaymentVoucherGov.objects.select_related(
            'ncoa_code__economic', 'ncoa_code__administrative',
            'appropriation', 'warrant', 'tsa_account',
        )

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a PV (moves from CHECKED/AUDITED to APPROVED)."""
        pv = self.get_object()
        if pv.status not in ('CHECKED', 'AUDITED'):
            return Response(
                {'error': f'Cannot approve PV with status "{pv.status}". Must be CHECKED or AUDITED.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        pv.status = 'APPROVED'
        pv.save(update_fields=['status', 'updated_at'])
        return Response(PaymentVoucherSerializer(pv).data)

    @action(detail=True, methods=['post'])
    def schedule_payment(self, request, pk=None):
        """Schedule an approved PV for payment — creates PaymentInstruction."""
        pv = self.get_object()
        if pv.status != 'APPROVED':
            return Response(
                {'error': f'Only APPROVED PVs can be scheduled. Current: "{pv.status}"'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if hasattr(pv, 'payment_instruction'):
            return Response(
                {'error': 'Payment instruction already exists for this PV.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        instruction = PaymentInstruction.objects.create(
            payment_voucher=pv,
            tsa_account=pv.tsa_account,
            beneficiary_name=pv.payee_name,
            beneficiary_account=pv.payee_account,
            beneficiary_bank=pv.payee_bank,
            beneficiary_sort=pv.payee_sort_code,
            amount=pv.net_amount,
            narration=pv.narration[:200],
        )
        pv.status = 'SCHEDULED'
        pv.save(update_fields=['status', 'updated_at'])

        return Response(PaymentInstructionSerializer(instruction).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        """Mark a PV as paid (after bank confirmation) and post IPSAS journal."""
        pv = self.get_object()
        if pv.status != 'SCHEDULED':
            return Response(
                {'error': f'Only SCHEDULED PVs can be marked paid. Current: "{pv.status}"'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bank_reference = request.data.get('bank_reference', '')

        # Update payment instruction
        if hasattr(pv, 'payment_instruction'):
            pi = pv.payment_instruction
            pi.status = 'PROCESSED'
            pi.bank_reference = bank_reference
            pi.processed_at = timezone.now()
            pi.save(update_fields=['status', 'bank_reference', 'processed_at', 'updated_at'])

            # ── Update TSA balance (cash leaves government account) ──
            from accounting.services.treasury_service import TSABalanceService
            TSABalanceService.process_payment(pi)

        # Post IPSAS journal entry
        journal = self._post_payment_journal(pv, request.user)

        pv.status = 'PAID'
        pv.journal = journal
        pv.save(update_fields=['status', 'journal', 'updated_at'])

        return Response(PaymentVoucherSerializer(pv).data)

    def _post_payment_journal(self, pv: PaymentVoucherGov, user):
        """
        Create and post IPSAS journal for a payment.
        DR  Expenditure account (NCoA economic segment)  NGN gross
        CR  TSA Sub-Account (31100100/31100200)          NGN net
        CR  WHT Payable (41200600) if applicable         NGN wht

        All accounts resolved via NCoA -> legacy_account bridge.
        """
        from accounting.models.gl import JournalHeader, JournalLine, TransactionSequence, Account
        from accounting.models.ncoa import EconomicSegment
        from accounting.services.ipsas_journal_service import IPSASJournalService

        ref = TransactionSequence.get_next('journal', prefix='JE-')
        header = JournalHeader.objects.create(
            reference_number=ref,
            description=f"Payment: {pv.narration}",
            posting_date=timezone.now().date(),
            status='Draft',
            source_module='treasury',
            source_document_id=pv.pk,
            posted_by=user,
        )

        # DR: Expenditure account from NCoA bridge
        expenditure_account = pv.ncoa_code.economic.legacy_account
        if not expenditure_account:
            raise ValueError(
                f"NCoA segment {pv.ncoa_code.economic.code} has no linked GL account. "
                f"Run: python manage.py seed_ncoa_as_coa"
            )

        JournalLine.objects.create(
            header=header,
            account=expenditure_account,
            debit=pv.gross_amount,
            credit=0,
            memo=f"PV {pv.voucher_number}: {pv.payee_name}",
            ncoa_code=pv.ncoa_code,
        )

        # CR: TSA account — use specific NCoA code 31100100 (Cash in TSA Main)
        # or 31100200 (Cash in TSA Sub-Accounts)
        tsa_seg = EconomicSegment.objects.filter(code='31100100').first()
        tsa_gl_account = tsa_seg.legacy_account if tsa_seg else Account.objects.filter(code='31100100').first()
        if not tsa_gl_account:
            raise ValueError("TSA GL account (31100100) not found. Run: python manage.py seed_ncoa_as_coa")

        if pv.wht_amount > 0:
            JournalLine.objects.create(
                header=header, account=tsa_gl_account,
                debit=0, credit=pv.net_amount,
                memo=f"TSA payment: {pv.voucher_number}",
            )
            # CR: WHT Payable — NCoA code 41200600
            wht_seg = EconomicSegment.objects.filter(code='41200600').first()
            wht_account = wht_seg.legacy_account if wht_seg else Account.objects.filter(code='41200600').first()
            if not wht_account:
                # Fallback to any WHT payable
                wht_account = Account.objects.filter(code__startswith='412', account_type='Liability').first()
            JournalLine.objects.create(
                header=header, account=wht_account,
                debit=0, credit=pv.wht_amount,
                memo=f"WHT on PV {pv.voucher_number}",
            )
        else:
            JournalLine.objects.create(
                header=header, account=tsa_gl_account,
                debit=0, credit=pv.gross_amount,
                memo=f"TSA payment: {pv.voucher_number}",
            )

        IPSASJournalService.post_journal(header, user)
        return header


class PaymentInstructionViewSet(viewsets.ModelViewSet):
    """Payment instructions sent to CBN/bank for TSA settlement."""
    serializer_class = PaymentInstructionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status']
    search_fields = ['beneficiary_name', 'batch_reference', 'bank_reference']
    ordering = ['-created_at']

    def get_queryset(self):
        return PaymentInstruction.objects.select_related(
            'payment_voucher', 'tsa_account',
        )


class RevenueHeadViewSet(viewsets.ModelViewSet):
    """Revenue head classification — maps to NCoA economic segment."""
    serializer_class = RevenueHeadSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['revenue_type', 'is_active']
    search_fields = ['code', 'name']
    ordering = ['code']

    def get_queryset(self):
        return RevenueHead.objects.select_related('economic_segment', 'collection_mda')


class RevenueCollectionViewSet(OrganizationFilterMixin, viewsets.ModelViewSet):
    org_filter_admin_field = 'collecting_mda'
    """Revenue receipt — individual IGR collection transactions."""
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'revenue_head', 'collection_channel']
    search_fields = ['receipt_number', 'payer_name', 'payer_tin', 'payment_reference']
    ordering_fields = ['collection_date', 'amount', 'created_at']
    ordering = ['-collection_date']

    def get_serializer_class(self):
        return RevenueCollectionSerializer

    def get_queryset(self):
        return RevenueCollection.objects.select_related(
            'revenue_head', 'ncoa_code__economic', 'tsa_account', 'collecting_mda',
        )

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Confirm a pending revenue collection."""
        collection = self.get_object()
        if collection.status != 'PENDING':
            return Response(
                {'error': f'Only PENDING collections can be confirmed. Current: "{collection.status}"'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        collection.status = 'CONFIRMED'
        collection.value_date = timezone.now().date()
        collection.save(update_fields=['status', 'value_date', 'updated_at'])
        return Response(RevenueCollectionSerializer(collection).data)

    @action(detail=True, methods=['post'])
    def post_to_gl(self, request, pk=None):
        """Post a confirmed revenue collection to GL. DR TSA / CR Revenue."""
        collection = self.get_object()
        if collection.status != 'CONFIRMED':
            return Response(
                {'error': f'Only CONFIRMED collections can be posted. Current: "{collection.status}"'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        journal = self._post_revenue_journal(collection, request.user)
        collection.status = 'POSTED'
        collection.journal = journal
        collection.save(update_fields=['status', 'journal', 'updated_at'])

        # ── Update TSA balance (cash enters government account) ──
        from accounting.services.treasury_service import TSABalanceService
        TSABalanceService.process_revenue(collection)

        return Response(RevenueCollectionSerializer(collection).data)

    def _post_revenue_journal(self, collection: RevenueCollection, user):
        """
        IPSAS Revenue Journal:
        DR  Cash in TSA (31100100)           NGN amount
        CR  Revenue Account (1xxxxxxx)       NGN amount

        All accounts resolved via NCoA -> legacy_account bridge.
        """
        from accounting.models.gl import JournalHeader, JournalLine, TransactionSequence, Account
        from accounting.models.ncoa import EconomicSegment
        from accounting.services.ipsas_journal_service import IPSASJournalService

        ref = TransactionSequence.get_next('journal', prefix='JE-')
        header = JournalHeader.objects.create(
            reference_number=ref,
            description=f"Revenue: {collection.revenue_head.name} from {collection.payer_name}",
            posting_date=collection.collection_date,
            status='Draft',
            source_module='revenue',
            source_document_id=collection.pk,
        )

        # DR: TSA account — NCoA code 31100100 (Cash in TSA Main)
        tsa_seg = EconomicSegment.objects.filter(code='31100100').first()
        tsa_gl = tsa_seg.legacy_account if tsa_seg else Account.objects.filter(code='31100100').first()
        if not tsa_gl:
            raise ValueError("TSA GL account (31100100) not found. Run: python manage.py seed_ncoa_as_coa")

        JournalLine.objects.create(
            header=header, account=tsa_gl,
            debit=collection.amount, credit=0,
            memo=f"Revenue receipt: {collection.receipt_number}",
            ncoa_code=collection.ncoa_code,
        )

        # CR: Revenue account from NCoA bridge
        revenue_gl = collection.revenue_head.economic_segment.legacy_account
        if not revenue_gl:
            raise ValueError(
                f"Revenue head '{collection.revenue_head.name}' has no linked GL account. "
                f"Run: python manage.py seed_ncoa_as_coa"
            )
        JournalLine.objects.create(
            header=header, account=revenue_gl,
            debit=0, credit=collection.amount,
            memo=f"Revenue: {collection.revenue_head.name}",
        )

        IPSASJournalService.post_journal(header, user)
        return header

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Revenue collection summary by revenue head and status."""
        from django.db.models import Sum, Count
        qs = self.get_queryset()

        # Filter by date range if provided
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(collection_date__gte=date_from)
        if date_to:
            qs = qs.filter(collection_date__lte=date_to)

        by_head = list(
            qs.values('revenue_head__name', 'revenue_head__code')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('-total')
        )
        by_status = list(
            qs.values('status')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('status')
        )
        total = qs.aggregate(total=Sum('amount'))['total'] or 0

        return Response({
            'total_collected': total,
            'by_revenue_head': by_head,
            'by_status': by_status,
        })

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """Download CSV template for bulk revenue collection import."""
        import io
        import csv
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'revenue_head_code', 'payer_name', 'payer_tin', 'amount',
            'collection_date', 'collection_channel', 'payment_reference',
            'rrr', 'description',
        ])
        writer.writerow([
            'IGR-PAYE', 'Acme Nigeria Ltd', 'TIN-00123456', '150000.00',
            '2026-01-15', 'BANK', 'TELLER-001', 'RRR-12345', 'January PAYE',
        ])
        writer.writerow([
            'IGR-FEES', 'John Doe', '', '25000.00',
            '2026-01-15', 'ONLINE', 'REF-002', '', 'Business registration fee',
        ])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="revenue_collection_template.csv"'
        return response

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        """Bulk import revenue collections from CSV/Excel."""
        import pandas as pd
        from accounting.models.revenue import RevenueHead

        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'CSV or Excel file required'}, status=status.HTTP_400_BAD_REQUEST)
        if file.size > 5 * 1024 * 1024:
            return Response({'error': 'File too large (max 5MB)'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = pd.read_excel(file, nrows=10000) if file.name.endswith('.xlsx') else pd.read_csv(file, nrows=10000)
        except Exception as e:
            return Response({'error': f'Failed to parse: {e}'}, status=status.HTTP_400_BAD_REQUEST)

        df.columns = df.columns.str.strip().str.lower()
        required = {'revenue_head_code', 'payer_name', 'amount', 'collection_date'}
        missing = required - set(df.columns)
        if missing:
            return Response({'error': f'Missing columns: {", ".join(missing)}'}, status=status.HTTP_400_BAD_REQUEST)

        head_lookup = {h.code: h for h in RevenueHead.objects.all()}
        created, skipped, errors = 0, 0, []

        for idx, row in df.iterrows():
            row_num = idx + 2
            try:
                head_code = str(row['revenue_head_code']).strip()
                head = head_lookup.get(head_code)
                if not head:
                    errors.append(f'Row {row_num}: Revenue head "{head_code}" not found')
                    continue

                amt = row.get('amount', 0)
                if pd.isna(amt) or float(amt) <= 0:
                    errors.append(f'Row {row_num}: Invalid amount')
                    continue

                channel = str(row.get('collection_channel', 'BANK')).strip().upper()
                if channel not in ('BANK', 'ONLINE', 'USSD', 'AGENT', 'COUNTER', 'POS'):
                    channel = 'BANK'

                ref = str(row.get('payment_reference', '')).strip()
                if ref and RevenueCollection.objects.filter(payment_reference=ref).exists():
                    skipped += 1
                    continue

                RevenueCollection.objects.create(
                    revenue_head=head,
                    payer_name=str(row['payer_name']).strip(),
                    payer_tin=str(row.get('payer_tin', '')).strip() if not pd.isna(row.get('payer_tin')) else '',
                    amount=float(amt),
                    collection_date=str(row['collection_date']).strip()[:10],
                    collection_channel=channel,
                    payment_reference=ref or None,
                    rrr=str(row.get('rrr', '')).strip() if not pd.isna(row.get('rrr')) else '',
                    description=str(row.get('description', '')).strip() if not pd.isna(row.get('description')) else '',
                )
                created += 1
            except Exception as e:
                errors.append(f'Row {row_num}: {e}')

        return Response({
            'success': True,
            'created': created,
            'updated': 0,
            'skipped': skipped,
            'errors': errors,
        })


# ── Treasury Operations API ─────────────────────────────────────

from rest_framework.decorators import api_view, permission_classes as perm_classes
from rest_framework.permissions import IsAuthenticated as IsAuth


@api_view(['POST'])
@perm_classes([IsAuth])
def execute_cash_sweep(request):
    """Execute daily cash sweep — moves all sub-account balances to Main TSA."""
    from accounting.services.treasury_service import CashSweepService
    result = CashSweepService.execute_daily_sweep()
    if 'error' in result:
        return Response(result, status=status.HTTP_400_BAD_REQUEST)
    return Response(result)


@api_view(['GET'])
@perm_classes([IsAuth])
def reconciliation_status(request):
    """Get reconciliation status for a TSA account."""
    from accounting.services.treasury_service import BankReconciliationService
    tsa_id = request.query_params.get('tsa_account_id')
    if not tsa_id:
        return Response({'error': 'tsa_account_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')
    result = BankReconciliationService.get_unreconciled_items(
        int(tsa_id), date_from=date_from, date_to=date_to,
    )
    return Response(result)


@api_view(['POST'])
@perm_classes([IsAuth])
def reconcile_payment(request):
    """Mark a payment instruction as reconciled with bank reference."""
    from accounting.services.treasury_service import BankReconciliationService
    pi_id = request.data.get('payment_instruction_id')
    bank_ref = request.data.get('bank_reference')
    if not pi_id or not bank_ref:
        return Response(
            {'error': 'payment_instruction_id and bank_reference are required'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    BankReconciliationService.reconcile_item(int(pi_id), bank_ref)
    return Response({'success': True})


@api_view(['POST'])
@perm_classes([IsAuth])
def mark_reconciled(request):
    """Mark a TSA account as fully reconciled as of today."""
    from accounting.services.treasury_service import BankReconciliationService
    tsa_id = request.data.get('tsa_account_id')
    if not tsa_id:
        return Response({'error': 'tsa_account_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    BankReconciliationService.mark_account_reconciled(int(tsa_id))
    return Response({'success': True, 'reconciled_date': str(timezone.now().date())})
