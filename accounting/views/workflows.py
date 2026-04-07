"""
Comprehensive accounting workflow ViewSets.

Covers: Credit/Debit Notes, Bad Debt, Petty Cash, Cheque Register,
Budget Period management, Suspense Clearing, and Audit Trail integration.
"""

from .common import (
    viewsets, status, Response, action, DjangoFilterBackend,
    transaction, Decimal, AccountingPagination,
)
from ..models import (
    CreditNote, DebitNote,
    BadDebtProvision, BadDebtWriteOff,
    PettyCashFund, PettyCashVoucher, PettyCashReplenishment,
    ChequeRegister,
    SuspenseClearing,
    BudgetPeriod, PeriodStatus,
    Account, BankAccount, JournalHeader, JournalLine, GLBalance, TransactionSequence,
    TransactionAuditLog,
)
from ..serializers import (
    CreditNoteSerializer, DebitNoteSerializer,
    BadDebtProvisionSerializer, BadDebtWriteOffSerializer,
    PettyCashFundSerializer, PettyCashVoucherSerializer, PettyCashReplenishmentSerializer,
    ChequeRegisterSerializer,
    SuspenseClearingSerializer,
    BudgetPeriodSerializer,
)
from accounting.transaction_posting import get_gl_account
from django.utils import timezone


# ===================== Helper =====================

def _update_gl_from_journal(journal):
    """Shared GL update from journal lines — delegates to atomic F()-based service."""
    from accounting.services import update_gl_from_journal
    update_gl_from_journal(journal)


def _log_audit(transaction_type, transaction_id, act, user, request=None, **kwargs):
    """Create a TransactionAuditLog entry."""
    try:
        ip = ''
        ua = ''
        if request:
            ip = request.META.get('REMOTE_ADDR', '')
            ua = request.META.get('HTTP_USER_AGENT', '')[:200]
        TransactionAuditLog.objects.create(
            transaction_type=transaction_type,
            transaction_id=transaction_id,
            action=act,
            user=user,
            username=user.username if user else '',
            ip_address=ip,
            user_agent=ua,
            **kwargs,
        )
    except Exception:
        pass  # Audit logging should never block the operation


# ===================== Credit / Debit Notes =====================

class CreditNoteViewSet(viewsets.ModelViewSet):
    queryset = CreditNote.objects.all().select_related('customer', 'original_invoice')
    serializer_class = CreditNoteSerializer
    filterset_fields = ['customer', 'status', 'reason_type']
    pagination_class = AccountingPagination

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a credit note."""
        cn = self.get_object()
        if cn.status != 'DRAFT':
            return Response({"error": "Only draft credit notes can be approved."}, status=status.HTTP_400_BAD_REQUEST)
        cn.status = 'APPROVED'
        cn.save(update_fields=['status'])
        _log_audit('CI', cn.id, 'APPROVE', request.user, request)
        return Response({"status": "Credit note approved."})

    @action(detail=True, methods=['post'])
    def post_note(self, request, pk=None):
        """Post credit note to GL — Dr Revenue / Cr AR."""
        cn = self.get_object()
        if cn.status not in ('APPROVED',):
            return Response({"error": "Credit note must be approved first."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                ar_account = get_gl_account('ACCOUNTS_RECEIVABLE', 'Asset', 'Receivable')
                rev_account = get_gl_account('SALES_REVENUE', 'Income', 'Revenue')
                if not ar_account or not rev_account:
                    return Response({"error": "AR or Revenue account not configured."}, status=status.HTTP_400_BAD_REQUEST)

                journal = JournalHeader.objects.create(
                    reference_number=f"CN-{cn.credit_note_number}",
                    description=f"Credit Note {cn.credit_note_number}",
                    posting_date=cn.credit_note_date,
                    status='Posted',
                )
                journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
                journal.save(update_fields=['document_number'], _allow_status_change=True)

                amount = cn.total_amount
                JournalLine.objects.create(
                    header=journal, account=rev_account,
                    debit=amount, credit=Decimal('0.00'),
                    memo=f"Credit Note {cn.credit_note_number}", document_number=journal.document_number,
                )
                JournalLine.objects.create(
                    header=journal, account=ar_account,
                    debit=Decimal('0.00'), credit=amount,
                    memo=f"AR adjustment {cn.credit_note_number}", document_number=journal.document_number,
                )

                _update_gl_from_journal(journal)
                cn.journal_id = journal.id
                cn.status = 'APPLIED'
                cn.applied_amount = amount
                cn.save()

                _log_audit('CI', cn.id, 'POST', request.user, request)

            return Response({"status": "Credit note posted.", "journal_id": journal.id})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class DebitNoteViewSet(viewsets.ModelViewSet):
    queryset = DebitNote.objects.all().select_related('vendor', 'original_invoice')
    serializer_class = DebitNoteSerializer
    filterset_fields = ['vendor', 'status', 'reason_type']
    pagination_class = AccountingPagination

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        dn = self.get_object()
        if dn.status != 'DRAFT':
            return Response({"error": "Only draft debit notes can be approved."}, status=status.HTTP_400_BAD_REQUEST)
        dn.status = 'APPROVED'
        dn.save(update_fields=['status'])
        return Response({"status": "Debit note approved."})

    @action(detail=True, methods=['post'])
    def post_note(self, request, pk=None):
        """Post debit note to GL — Dr AP / Cr Expense."""
        dn = self.get_object()
        if dn.status not in ('APPROVED',):
            return Response({"error": "Debit note must be approved first."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                ap_account = get_gl_account('ACCOUNTS_PAYABLE', 'Liability', 'Payable')
                exp_account = get_gl_account('PURCHASE_EXPENSE', 'Expense', 'Purchase')
                if not ap_account or not exp_account:
                    return Response({"error": "AP or Expense account not configured."}, status=status.HTTP_400_BAD_REQUEST)

                journal = JournalHeader.objects.create(
                    reference_number=f"DN-{dn.debit_note_number}",
                    description=f"Debit Note {dn.debit_note_number}",
                    posting_date=dn.debit_note_date,
                    status='Posted',
                )
                journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
                journal.save(update_fields=['document_number'], _allow_status_change=True)

                amount = dn.total_amount
                JournalLine.objects.create(
                    header=journal, account=ap_account,
                    debit=amount, credit=Decimal('0.00'),
                    memo=f"Debit Note {dn.debit_note_number}", document_number=journal.document_number,
                )
                JournalLine.objects.create(
                    header=journal, account=exp_account,
                    debit=Decimal('0.00'), credit=amount,
                    memo=f"Expense reversal {dn.debit_note_number}", document_number=journal.document_number,
                )

                _update_gl_from_journal(journal)
                dn.journal_id = journal.id
                dn.status = 'APPLIED'
                dn.applied_amount = amount
                dn.save()

            return Response({"status": "Debit note posted.", "journal_id": journal.id})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ===================== Bad Debt =====================

class BadDebtProvisionViewSet(viewsets.ModelViewSet):
    queryset = BadDebtProvision.objects.all()
    serializer_class = BadDebtProvisionSerializer
    filterset_fields = ['fiscal_year', 'status']
    pagination_class = AccountingPagination

    @action(detail=True, methods=['post'])
    def post_provision(self, request, pk=None):
        """Post bad debt provision — Dr Bad Debt Expense / Cr Allowance for Doubtful Accounts."""
        provision = self.get_object()
        if provision.status == 'POSTED':
            return Response({"error": "Already posted."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                expense_account = Account.objects.filter(
                    name__icontains='Bad Debt', account_type='Expense',
                ).first()
                allowance_account = Account.objects.filter(
                    name__icontains='Allowance', account_type='Asset',
                ).first()

                if not expense_account or not allowance_account:
                    return Response(
                        {"error": "Bad Debt Expense or Allowance account not found."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                amount = provision.new_provisions
                journal = JournalHeader.objects.create(
                    reference_number=f"BDP-{provision.fiscal_year}-{provision.period}",
                    description=f"Bad Debt Provision {provision.fiscal_year} P{provision.period}",
                    posting_date=provision.provision_date,
                    status='Posted',
                )
                journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
                journal.save(update_fields=['document_number'], _allow_status_change=True)

                JournalLine.objects.create(
                    header=journal, account=expense_account,
                    debit=amount, credit=Decimal('0.00'),
                    memo="Bad debt provision", document_number=journal.document_number,
                )
                JournalLine.objects.create(
                    header=journal, account=allowance_account,
                    debit=Decimal('0.00'), credit=amount,
                    memo="Allowance for doubtful accounts", document_number=journal.document_number,
                )

                _update_gl_from_journal(journal)
                provision.journal_id = journal.id
                provision.status = 'POSTED'
                provision.save()

            return Response({"status": "Provision posted.", "journal_id": journal.id})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class BadDebtWriteOffViewSet(viewsets.ModelViewSet):
    queryset = BadDebtWriteOff.objects.all().select_related('customer', 'original_invoice')
    serializer_class = BadDebtWriteOffSerializer
    filterset_fields = ['customer', 'status']
    pagination_class = AccountingPagination

    @action(detail=True, methods=['post'])
    def post_writeoff(self, request, pk=None):
        """Post write-off — Dr Allowance / Cr AR."""
        wo = self.get_object()
        if wo.status == 'POSTED':
            return Response({"error": "Already posted."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                ar_account = get_gl_account('ACCOUNTS_RECEIVABLE', 'Asset', 'Receivable')
                allowance_account = Account.objects.filter(
                    name__icontains='Allowance', account_type='Asset',
                ).first()

                if not ar_account or not allowance_account:
                    return Response({"error": "AR or Allowance account not found."}, status=status.HTTP_400_BAD_REQUEST)

                journal = JournalHeader.objects.create(
                    reference_number=f"BDWO-{wo.write_off_number}",
                    description=f"Bad Debt Write-Off {wo.write_off_number}",
                    posting_date=wo.write_off_date,
                    status='Posted',
                )
                journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
                journal.save(update_fields=['document_number'], _allow_status_change=True)

                amount = wo.amount_written_off
                JournalLine.objects.create(
                    header=journal, account=allowance_account,
                    debit=amount, credit=Decimal('0.00'),
                    memo=f"Write-off {wo.write_off_number}", document_number=journal.document_number,
                )
                JournalLine.objects.create(
                    header=journal, account=ar_account,
                    debit=Decimal('0.00'), credit=amount,
                    memo=f"AR write-off {wo.write_off_number}", document_number=journal.document_number,
                )

                _update_gl_from_journal(journal)
                wo.journal_id = journal.id
                wo.status = 'POSTED'
                wo.save()

            return Response({"status": "Write-off posted.", "journal_id": journal.id})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ===================== Petty Cash =====================

class PettyCashFundViewSet(viewsets.ModelViewSet):
    queryset = PettyCashFund.objects.all().select_related('bank_account', 'custodian')
    serializer_class = PettyCashFundSerializer
    filterset_fields = ['is_active']
    pagination_class = AccountingPagination

    def perform_create(self, serializer):
        """
        Auto-provision GL account + BankAccount when a new Petty Cash Fund is created.

        Flow:
          1. Create an Asset GL account (reconciliation_type='bank_accounting') in the COA.
          2. Create a BankAccount (account_type='Petty Cash') linked to the GL account.
          3. Save the fund with the new bank_account wired in.

        If the caller already supplied a bank_account, skip auto-provisioning.
        """
        with transaction.atomic():
            fund_code = serializer.validated_data.get('code', '')
            fund_name = serializer.validated_data.get('name', '')
            float_amount = serializer.validated_data.get('float_amount', Decimal('0'))

            # Only auto-provision if no bank_account was explicitly provided
            if not serializer.validated_data.get('bank_account'):
                gl_code = f'PCF-{fund_code}'

                # Ensure code uniqueness — append suffix if collision exists
                base = gl_code
                suffix = 1
                while Account.objects.filter(code=gl_code).exists():
                    gl_code = f'{base}-{suffix}'
                    suffix += 1

                # 1. Create GL account in COA
                gl_account = Account.objects.create(
                    code=gl_code,
                    name=f'Petty Cash — {fund_name}',
                    account_type='Asset',
                    is_active=True,
                    is_reconciliation=True,
                    reconciliation_type='bank_accounting',
                )

                # 2. Create BankAccount linked to GL
                bank_acct_number = f'CASH-{fund_code}'
                if BankAccount.objects.filter(account_number=bank_acct_number).exists():
                    bank_acct_number = f'CASH-{fund_code}-{suffix}'

                bank_account = BankAccount.objects.create(
                    name=f'{fund_name} (Petty Cash)',
                    account_number=bank_acct_number,
                    account_type='Petty Cash',
                    gl_account=gl_account,
                    opening_balance=float_amount,
                    current_balance=float_amount,
                    is_active=True,
                )

                # 3. Save fund with the provisioned bank_account
                serializer.save(bank_account=bank_account)
            else:
                serializer.save()


class PettyCashVoucherViewSet(viewsets.ModelViewSet):
    queryset = PettyCashVoucher.objects.all().select_related('petty_cash_fund', 'account', 'cost_center')
    serializer_class = PettyCashVoucherSerializer
    filterset_fields = ['petty_cash_fund', 'approval_status']
    pagination_class = AccountingPagination

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        voucher = self.get_object()
        if voucher.approval_status != 'PENDING':
            return Response({"error": "Only pending vouchers can be approved."}, status=status.HTTP_400_BAD_REQUEST)
        voucher.approval_status = 'APPROVED'
        voucher.approved_by = request.user
        voucher.approved_at = timezone.now()
        voucher.save()
        return Response({"status": "Voucher approved."})

    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        """Pay voucher and post to GL — Dr Expense / Cr Petty Cash."""
        voucher = self.get_object()
        if voucher.approval_status != 'APPROVED':
            return Response({"error": "Voucher must be approved first."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                expense_account = voucher.account
                if not expense_account:
                    return Response({"error": "No expense account on voucher."}, status=status.HTTP_400_BAD_REQUEST)

                pc_bank = voucher.petty_cash_fund.bank_account
                cash_gl = pc_bank.gl_account if pc_bank else None
                if not cash_gl:
                    cash_gl = get_gl_account('CASH_ACCOUNT', 'Asset', 'Cash')
                if not cash_gl:
                    return Response({"error": "No cash GL account found."}, status=status.HTTP_400_BAD_REQUEST)

                journal = JournalHeader.objects.create(
                    reference_number=f"PCV-{voucher.voucher_number}",
                    description=f"Petty Cash Voucher {voucher.voucher_number}",
                    posting_date=voucher.voucher_date,
                    status='Posted',
                )
                journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
                journal.save(update_fields=['document_number'], _allow_status_change=True)

                JournalLine.objects.create(
                    header=journal, account=expense_account,
                    debit=voucher.amount, credit=Decimal('0.00'),
                    memo=f"PCV {voucher.voucher_number}: {voucher.description}",
                    document_number=journal.document_number,
                )
                JournalLine.objects.create(
                    header=journal, account=cash_gl,
                    debit=Decimal('0.00'), credit=voucher.amount,
                    memo=f"Petty cash payment {voucher.voucher_number}",
                    document_number=journal.document_number,
                )

                _update_gl_from_journal(journal)

                voucher.journal_id = journal.id
                voucher.approval_status = 'PAID'
                voucher.save()

                # Update petty cash balance
                fund = voucher.petty_cash_fund
                fund.current_balance -= voucher.amount
                fund.save(update_fields=['current_balance'])

            return Response({"status": "Voucher paid and posted.", "journal_id": journal.id})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PettyCashReplenishmentViewSet(viewsets.ModelViewSet):
    queryset = PettyCashReplenishment.objects.all().select_related('petty_cash_fund', 'bank_account')
    serializer_class = PettyCashReplenishmentSerializer
    filterset_fields = ['petty_cash_fund', 'status']
    pagination_class = AccountingPagination

    @action(detail=True, methods=['post'])
    def post_replenishment(self, request, pk=None):
        """Post replenishment — Dr Petty Cash / Cr Bank."""
        replen = self.get_object()
        if replen.status == 'POSTED':
            return Response({"error": "Already posted."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                pc_gl = replen.petty_cash_fund.bank_account.gl_account if replen.petty_cash_fund.bank_account else None
                bank_gl = replen.bank_account.gl_account if replen.bank_account else None
                if not pc_gl:
                    pc_gl = get_gl_account('CASH_ACCOUNT', 'Asset', 'Cash')
                if not bank_gl:
                    bank_gl = get_gl_account('BANK_ACCOUNT', 'Asset', 'Bank')
                if not pc_gl or not bank_gl:
                    return Response({"error": "Cash or Bank GL account not found."}, status=status.HTTP_400_BAD_REQUEST)

                journal = JournalHeader.objects.create(
                    reference_number=f"PCR-{replen.replenishment_number}",
                    description=f"Petty Cash Replenishment {replen.replenishment_number}",
                    posting_date=replen.replenishment_date,
                    status='Posted',
                )
                journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
                journal.save(update_fields=['document_number'], _allow_status_change=True)

                amount = replen.reimbursement_amount
                JournalLine.objects.create(
                    header=journal, account=pc_gl,
                    debit=amount, credit=Decimal('0.00'),
                    memo=f"Replenishment {replen.replenishment_number}", document_number=journal.document_number,
                )
                JournalLine.objects.create(
                    header=journal, account=bank_gl,
                    debit=Decimal('0.00'), credit=amount,
                    memo=f"Bank payment {replen.replenishment_number}", document_number=journal.document_number,
                )

                _update_gl_from_journal(journal)
                replen.journal_id = journal.id
                replen.status = 'POSTED'
                replen.save()

                # Restore petty cash balance
                fund = replen.petty_cash_fund
                fund.current_balance += amount
                fund.save(update_fields=['current_balance'])

            return Response({"status": "Replenishment posted.", "journal_id": journal.id})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ===================== Cheque Register =====================

class ChequeRegisterViewSet(viewsets.ModelViewSet):
    queryset = ChequeRegister.objects.all().select_related('bank_account')
    serializer_class = ChequeRegisterSerializer
    filterset_fields = ['bank_account', 'status', 'cheque_type']
    pagination_class = AccountingPagination

    @action(detail=True, methods=['post'])
    def present(self, request, pk=None):
        """Mark cheque as presented to bank."""
        cheque = self.get_object()
        if cheque.status != 'ISSUED':
            return Response({"error": "Only issued cheques can be presented."}, status=status.HTTP_400_BAD_REQUEST)
        cheque.status = 'PRESENTED'
        cheque.presented_by = request.user
        cheque.presented_at = timezone.now()
        cheque.save()
        return Response({"status": "Cheque marked as presented."})

    @action(detail=True, methods=['post'])
    def clear(self, request, pk=None):
        """Mark cheque as cleared/paid by bank."""
        cheque = self.get_object()
        if cheque.status != 'PRESENTED':
            return Response({"error": "Only presented cheques can be cleared."}, status=status.HTTP_400_BAD_REQUEST)
        cheque.status = 'PAID'
        cheque.save(update_fields=['status'])
        return Response({"status": "Cheque cleared."})

    @action(detail=True, methods=['post'])
    def bounce(self, request, pk=None):
        """Mark cheque as bounced — creates reversal journal entry."""
        cheque = self.get_object()
        if cheque.status not in ('PRESENTED', 'PAID'):
            return Response({"error": "Only presented/paid cheques can bounce."}, status=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get('reason', 'Insufficient funds')

        try:
            with transaction.atomic():
                cheque.status = 'BOUNCED'
                cheque.bounce_reason = reason
                cheque.save()

                # If there was a linked journal, create a reversal
                if cheque.journal_id:
                    original = JournalHeader.objects.prefetch_related('lines').filter(id=cheque.journal_id).first()
                    if original:
                        reversal = JournalHeader.objects.create(
                            reference_number=f"CHQ-BOUNCE-{cheque.cheque_number}",
                            description=f"Bounced cheque reversal: {cheque.cheque_number}",
                            posting_date=timezone.now().date(),
                            fund=original.fund, function=original.function,
                            program=original.program, geo=original.geo,
                            status='Posted',
                        )
                        reversal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
                        reversal.save(update_fields=['document_number'], _allow_status_change=True)

                        for line in original.lines.all():
                            JournalLine.objects.create(
                                header=reversal, account=line.account,
                                debit=line.credit, credit=line.debit,
                                memo=f"Bounce reversal: {cheque.cheque_number}",
                                document_number=reversal.document_number,
                            )

                        _update_gl_from_journal(reversal)

            return Response({"status": "Cheque marked as bounced."})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """Stop payment on a cheque."""
        cheque = self.get_object()
        if cheque.status in ('PAID', 'CANCELLED'):
            return Response({"error": "Cannot stop a paid/cancelled cheque."}, status=status.HTTP_400_BAD_REQUEST)
        cheque.status = 'STOPPED'
        cheque.stop_reason = request.data.get('reason', '')
        cheque.save()
        return Response({"status": "Cheque stopped."})


# ===================== Budget Period Management =====================

class BudgetPeriodManagementViewSet(viewsets.ModelViewSet):
    """Extended budget period ViewSet with close/lock/reopen actions."""
    queryset = BudgetPeriod.objects.all()
    serializer_class = BudgetPeriodSerializer
    filterset_fields = ['fiscal_year', 'period_type', 'status']
    pagination_class = AccountingPagination

    @action(detail=True, methods=['post'])
    def close_period(self, request, pk=None):
        """Close a budget period."""
        period = self.get_object()
        if period.status in ('CLOSED', 'LOCKED'):
            return Response({"error": f"Period is already {period.status}."}, status=status.HTTP_400_BAD_REQUEST)
        period.status = 'CLOSED'
        period.allow_postings = False
        period.closed_by = request.user
        period.closed_date = timezone.now()
        period.save()
        return Response({"status": f"Period {period} closed."})

    @action(detail=True, methods=['post'])
    def lock_period(self, request, pk=None):
        """Lock a budget period permanently."""
        period = self.get_object()
        period.status = 'LOCKED'
        period.allow_postings = False
        period.allow_adjustments = False
        period.locked_by = request.user
        period.locked_date = timezone.now()
        period.save()
        return Response({"status": f"Period {period} locked."})

    @action(detail=True, methods=['post'])
    def reopen_period(self, request, pk=None):
        """Reopen a closed budget period."""
        period = self.get_object()
        if period.status == 'LOCKED':
            return Response({"error": "Cannot reopen a locked period."}, status=status.HTTP_400_BAD_REQUEST)
        period.status = 'OPEN'
        period.allow_postings = True
        period.allow_adjustments = True
        period.closed_by = None
        period.closed_date = None
        period.save()
        return Response({"status": f"Period {period} reopened."})


# ===================== Suspense Clearing =====================

class SuspenseClearingViewSet(viewsets.ModelViewSet):
    queryset = SuspenseClearing.objects.all().select_related(
        'journal_header', 'suspense_account', 'clearing_account',
    )
    serializer_class = SuspenseClearingSerializer
    filterset_fields = ['status']
    pagination_class = AccountingPagination

    @action(detail=True, methods=['post'])
    def clear(self, request, pk=None):
        """Clear suspense amount — Dr Clearing Account / Cr Suspense Account."""
        clearing = self.get_object()
        if clearing.status == 'CLEARED':
            return Response({"error": "Already cleared."}, status=status.HTTP_400_BAD_REQUEST)

        clear_amount = Decimal(str(request.data.get('amount', clearing.balance)))
        if clear_amount <= 0 or clear_amount > clearing.balance:
            return Response(
                {"error": f"Invalid amount. Balance is {clearing.balance}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                journal = JournalHeader.objects.create(
                    reference_number=f"SUSP-CLR-{clearing.clearing_number}",
                    description=f"Suspense Clearing {clearing.clearing_number}",
                    posting_date=timezone.now().date(),
                    status='Posted',
                )
                journal.document_number = TransactionSequence.get_next('journal_voucher', 'JV-')
                journal.save(update_fields=['document_number'], _allow_status_change=True)

                JournalLine.objects.create(
                    header=journal, account=clearing.clearing_account,
                    debit=clear_amount, credit=Decimal('0.00'),
                    memo=f"Suspense clearing {clearing.clearing_number}",
                    document_number=journal.document_number,
                )
                JournalLine.objects.create(
                    header=journal, account=clearing.suspense_account,
                    debit=Decimal('0.00'), credit=clear_amount,
                    memo=f"Clear suspense {clearing.clearing_number}",
                    document_number=journal.document_number,
                )

                _update_gl_from_journal(journal)

                new_balance = clearing.balance - clear_amount
                clearing.cleared_amount += clear_amount
                clearing.balance = new_balance
                if new_balance <= 0:
                    clearing.status = 'CLEARED'
                else:
                    clearing.status = 'PARTIAL'
                clearing.save()
                # Note: Unlike GL/vendor/customer balances, suspense clearing balance
                # is not subject to concurrent updates since it's per-clearing-record.

            return Response({
                "status": "Suspense cleared.",
                "journal_id": journal.id,
                "cleared_amount": str(clear_amount),
                "remaining_balance": str(clearing.balance),
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
