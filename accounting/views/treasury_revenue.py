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

    @action(detail=False, methods=['get'], url_path='derive-invoice-wht')
    def derive_invoice_wht(self, request):
        """Return the auto-derived WHT deduction implied by an invoice.

        Used by the PV creation form (and the Outgoing Payments form)
        to preview the WHT deduction the system will apply when the
        operator picks an invoice. Returns:
          • 200 with the derived row if WHT applies
          • 200 with ``is_exempt=True, amount=0`` if the invoice is
            exempt (vendor master OR per-transaction)
          • 200 with ``{}`` if the invoice has no WHT determination
          • 404 if the invoice number can't be found

        Query params:
            invoice_number (str, required)
        """
        from decimal import Decimal as _D
        from accounting.services.wht_payment_derivation import (
            derive_wht_for_invoice,
        )
        invoice_number = request.query_params.get('invoice_number', '').strip()
        if not invoice_number:
            return Response(
                {'error': 'invoice_number query parameter is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        derived = derive_wht_for_invoice(invoice_number=invoice_number)
        if derived is None:
            return Response({})
        # Stringify Decimals for JSON safety.
        out = {
            k: (str(v) if isinstance(v, _D) else v)
            for k, v in derived.items()
        }
        return Response(out)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a PV.

        Any user with the ``approve`` permission (and a fresh MFA — see
        ``get_permissions`` for the gate) can promote a voucher to
        APPROVED from any pre-approval state: DRAFT, CHECKED, or
        AUDITED. The intermediate Check / Audit steps remain available
        as optional review gates for tenants that want them, but they
        are no longer mandatory — a Treasury operator with approval
        authority can act on a draft directly.

        Only terminal / post-approval states (already APPROVED,
        SCHEDULED, PAID, CANCELLED, REVERSED) reject the call, since
        re-approving them is meaningless or destructive.
        """
        pv = self.get_object()
        APPROVABLE_STATUSES = ('DRAFT', 'CHECKED', 'AUDITED')
        if pv.status not in APPROVABLE_STATUSES:
            return Response(
                {
                    'error': (
                        f'Cannot approve PV with status "{pv.status}". '
                        f'Approval is only available before the voucher '
                        f'has been approved/scheduled/paid.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        pv.status = 'APPROVED'
        pv.save(update_fields=['status', 'updated_at'])
        return Response(PaymentVoucherSerializer(pv).data)

    @action(detail=True, methods=['post'])
    def schedule_payment(self, request, pk=None):
        """Schedule an approved PV for payment.

        Creates two linked records and flips the PV to ``SCHEDULED``:

        1. **PaymentInstruction** — bank-rail-facing record (TSA + payee
           details + amount + narration) that the bank-integration layer
           consumes to dispatch the actual transfer.
        2. **Payment (Draft)** — operator-facing outgoing-payment row
           that surfaces in the *Outgoing Payments* list. The Treasury
           operator finalises the payment method (Wire / ACH / Cheque)
           and bank account, then posts it — at which point the GL
           journal (DR AP / CR Cash) lands and the cash actually moves.

        Idempotent on retries: a second call when the PV is already
        scheduled returns 400 with a clear message, AND skips creating
        a duplicate Payment if one is already linked.
        """
        from accounting.models import TransactionSequence
        from accounting.models.receivables import Payment
        from datetime import date as _date

        pv = self.get_object()
        # Allow either:
        #   • APPROVED — the canonical "schedule for payment" entry point
        #   • SCHEDULED — re-entry to *backfill* a missing Payment row.
        #     This heals data created before the action started auto-
        #     materialising the Payment. Re-clicking Schedule on an
        #     already-SCHEDULED PV with a draft Payment present is a
        #     no-op; without a draft Payment, the missing row is
        #     created and surfaced in Outgoing Payments.
        if pv.status not in ('APPROVED', 'SCHEDULED'):
            return Response(
                {'error': f'Only APPROVED or SCHEDULED PVs can be scheduled. Current: "{pv.status}"'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # NOTE: no warrant check at schedule time. Scheduling only
        # materialises a draft Payment row in Outgoing Payments — it
        # doesn't disburse cash. The warrant ceiling binds at payment
        # posting (when Draft → Posted writes the GL journal), gated
        # there by ``AccountingSettings.require_warrant_before_payment``.
        # Operators can always schedule an APPROVED PV regardless of
        # warrant availability; the gate fires when they try to post
        # the resulting Draft Payment.

        # PaymentInstruction is created once. On re-entry (SCHEDULED PV
        # that's missing only the Payment) we reuse the existing one.
        instruction = getattr(pv, 'payment_instruction', None)
        if instruction is None:
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

        # ── Draft Payment row for the Outgoing Payments page ─────────
        # Idempotency: if some earlier flow already linked a draft
        # Payment to this PV, reuse it rather than creating a duplicate.
        # ``cash_payments`` is the reverse manager declared on
        # ``Payment.payment_voucher``.
        existing_payment = pv.cash_payments.filter(status='Draft').order_by('id').first()
        if existing_payment is None:
            payment_number = TransactionSequence.get_next('payment', 'PAY-')
            # Resolve the vendor from the linked invoice when available —
            # the Outgoing Payments page groups rows by vendor name.
            vendor = None
            try:
                from accounting.models.receivables import VendorInvoice
                if pv.invoice_number:
                    vi = (
                        VendorInvoice.objects
                        .filter(invoice_number=pv.invoice_number)
                        .select_related('vendor')
                        .first()
                    )
                    if vi and vi.vendor_id:
                        vendor = vi.vendor
            except Exception:  # noqa: BLE001 — vendor inference is best-effort
                vendor = None

            existing_payment = Payment.objects.create(
                payment_number=payment_number,
                payment_date=_date.today(),
                payment_method='Wire',  # Treasury operator can change before posting
                reference_number=pv.voucher_number or '',
                total_amount=pv.net_amount,
                status='Draft',
                payment_voucher=pv,
                vendor=vendor,
                document_number=payment_number,
            )

        # Only flip status on the APPROVED → SCHEDULED transition. On
        # re-entry (already SCHEDULED) we leave status untouched.
        if pv.status == 'APPROVED':
            pv.status = 'SCHEDULED'
            pv.save(update_fields=['status', 'updated_at'])

        return Response({
            'instruction': PaymentInstructionSerializer(instruction).data,
            'payment': {
                'id': existing_payment.pk,
                'payment_number': existing_payment.payment_number,
                'status': existing_payment.status,
                'total_amount': str(existing_payment.total_amount),
            },
        }, status=status.HTTP_201_CREATED)

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
        Create and post the IPSAS payment journal.

        Payment-time recognition model (Nigerian IFMIS, cash basis):
            DR  Expenditure / AP account        NGN gross
            CR  TSA Cash                        NGN net paid
            CR  <Deduction liability>           NGN (one row per deduction)
            ...

        Deductions come from ``pv.deductions`` (PaymentVoucherDeduction
        child rows). Typical kinds: WHT, Stamp Duty, VAT withheld, Bank
        Handling Charges, Insurance, Retention, Other. Each deduction row
        carries its own ``gl_account`` so operators can pick the correct
        liability/revenue account per the CoA.

        Backward-compat: if no deduction lines exist but the legacy
        ``pv.wht_amount`` is non-zero, a single WHT credit row is emitted
        against the configured WHT NCoA code (41200600) so old records
        continue to post correctly.

        All accounts resolved via NCoA -> legacy_account bridge.
        """
        from decimal import Decimal
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

        # DR: Expenditure account from NCoA bridge (full gross — deductions
        # are recognised as separate credits on the same journal).
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

        # Resolve TSA cash GL account.
        # Drives off the PV's configured TSA → its gl_cash_account FK,
        # falling back to AccountingSettings.default_cash_account_code,
        # then to the first 31* asset GL. Never hardcodes a code so a
        # tenant can ship with any cash-account numbering scheme. See
        # accounting.services.tsa_gl_resolver for the full priority chain.
        from accounting.services.tsa_gl_resolver import resolve_tsa_cash_gl
        tsa_gl_account = resolve_tsa_cash_gl(
            tsa_account=getattr(pv, 'tsa_account', None),
        )

        # ── Deduction lines ──────────────────────────────────────────
        deductions = list(pv.deductions.select_related('gl_account').all())
        total_deductions = sum((d.amount for d in deductions), Decimal('0'))

        # Legacy fallback: header-only wht_amount with no deduction rows.
        if not deductions and (pv.wht_amount or Decimal('0')) > 0:
            wht_seg = EconomicSegment.objects.filter(code='41200600').first()
            wht_account = (
                wht_seg.legacy_account if wht_seg
                else Account.objects.filter(code='41200600').first()
                or Account.objects.filter(code__startswith='412', account_type='Liability').first()
            )
            if wht_account:
                JournalLine.objects.create(
                    header=header, account=wht_account,
                    debit=0, credit=pv.wht_amount,
                    memo=f"WHT on PV {pv.voucher_number}",
                )
                total_deductions = pv.wht_amount

        # Emit one credit row per deduction line.
        for d in deductions:
            if d.amount and d.amount > 0 and d.gl_account:
                JournalLine.objects.create(
                    header=header, account=d.gl_account,
                    debit=0, credit=d.amount,
                    memo=(
                        f"{d.get_deduction_type_display()} on PV {pv.voucher_number}"
                        + (f" — {d.description}" if d.description else '')
                    )[:255],
                )

        # CR: TSA cash = gross − Σ deductions (the amount actually paid out).
        net_paid = (pv.gross_amount or Decimal('0')) - total_deductions
        if net_paid > 0:
            JournalLine.objects.create(
                header=header, account=tsa_gl_account,
                debit=0, credit=net_paid,
                memo=(
                    f"TSA payment: {pv.voucher_number}"
                    + (f" (net of {total_deductions} deductions)" if total_deductions > 0 else "")
                ),
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
        DR  Cash in TSA (resolved per-TSA)   NGN amount
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

        # DR: TSA cash GL — driven off the collection's configured TSA
        # (or tenant default), never a hardcoded code. See
        # accounting.services.tsa_gl_resolver for the resolution chain.
        from accounting.services.tsa_gl_resolver import resolve_tsa_cash_gl
        tsa_gl = resolve_tsa_cash_gl(
            tsa_account=getattr(collection, 'tsa_account', None),
        )

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
