"""
Treasury Service — Quot PSE
===========================
Handles TSA balance management, cash sweeping, and bank reconciliation.

IPSAS Accrual Flow:
1. Invoice received → DR Expense, CR Accounts Payable (AP recognized)
2. PV approved → Budget validation passes
3. Payment Instruction PROCESSED → DR AP, CR TSA Cash (cash leaves TSA)
   → THIS is where TSA balance updates

Revenue Flow:
1. Revenue collected → DR TSA Cash, CR Revenue (cash enters TSA)
   → TSA balance increases on revenue posting
"""
from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone
import logging

logger = logging.getLogger('treasury')


class TSABalanceService:
    """
    Updates TSA account balances based on cash movements.

    Called when:
    - PaymentInstruction status → PROCESSED (cash out)
    - RevenueCollection status → POSTED (cash in)
    - Cash sweep executed (zero-balance → main TSA)
    """

    @classmethod
    def process_payment(cls, payment_instruction) -> None:
        """
        Debit TSA when payment instruction is processed.
        Called after bank confirms settlement.

        IPSAS Journal (already posted at PV stage):
        DR  Accounts Payable     (clearing the vendor liability)
        CR  TSA Cash             (cash leaves government account)
        """
        tsa = payment_instruction.tsa_account
        amount = payment_instruction.amount

        with transaction.atomic():
            # Lock the account row to prevent concurrent updates
            tsa_locked = type(tsa).objects.select_for_update().get(pk=tsa.pk)
            tsa_locked.current_balance -= amount
            tsa_locked.save(update_fields=['current_balance', 'updated_at'])

            logger.info(
                'TSA DEBIT: %s | Amount: %s | PI: %s | New Balance: %s',
                tsa_locked.account_number, amount,
                payment_instruction.pk, tsa_locked.current_balance,
            )

    @classmethod
    def process_revenue(cls, revenue_collection) -> None:
        """
        Credit TSA when revenue is posted to GL.
        Called after RevenueCollection.status → POSTED.

        IPSAS Journal:
        DR  TSA Cash             (cash enters government account)
        CR  Revenue              (income recognized)
        """
        tsa = revenue_collection.tsa_account
        if not tsa:
            return
        amount = revenue_collection.amount

        with transaction.atomic():
            tsa_locked = type(tsa).objects.select_for_update().get(pk=tsa.pk)
            tsa_locked.current_balance += amount
            tsa_locked.save(update_fields=['current_balance', 'updated_at'])

            logger.info(
                'TSA CREDIT: %s | Amount: %s | Receipt: %s | New Balance: %s',
                tsa_locked.account_number, amount,
                revenue_collection.receipt_number, tsa_locked.current_balance,
            )

    @classmethod
    def reverse_payment(cls, payment_instruction) -> None:
        """Reverse a processed payment (credit TSA back)."""
        tsa = payment_instruction.tsa_account
        amount = payment_instruction.amount

        with transaction.atomic():
            tsa_locked = type(tsa).objects.select_for_update().get(pk=tsa.pk)
            tsa_locked.current_balance += amount
            tsa_locked.save(update_fields=['current_balance', 'updated_at'])

            logger.info(
                'TSA REVERSAL CREDIT: %s | Amount: %s | PI: %s',
                tsa_locked.account_number, amount, payment_instruction.pk,
            )


class CashSweepService:
    """
    Daily sweep of zero-balance and sub-accounts to Main TSA.

    Per CBN TSA policy:
    - All MDA sub-accounts are zero-balance accounts
    - End of day: all balances sweep to Main TSA
    - Revenue collection accounts sweep to Consolidated Revenue Fund
    """

    @classmethod
    def execute_daily_sweep(cls) -> dict:
        """
        Sweep all non-main accounts to their parent (or Main TSA).
        Returns summary of sweep operations.
        """
        from accounting.models.treasury import TreasuryAccount

        main_tsa = TreasuryAccount.objects.filter(
            account_type='MAIN_TSA', is_active=True,
        ).first()

        if not main_tsa:
            return {'error': 'No Main TSA account found', 'swept': 0}

        sweep_accounts = TreasuryAccount.objects.filter(
            account_type__in=['ZERO_BALANCE', 'SUB_ACCOUNT', 'REVENUE'],
            is_active=True,
        ).exclude(current_balance=0)

        swept_count = 0
        total_swept = Decimal('0')
        details = []

        with transaction.atomic():
            main_locked = TreasuryAccount.objects.select_for_update().get(pk=main_tsa.pk)

            for acct in sweep_accounts:
                acct_locked = TreasuryAccount.objects.select_for_update().get(pk=acct.pk)
                sweep_amount = acct_locked.current_balance

                if sweep_amount == 0:
                    continue

                # Transfer balance to parent or Main TSA
                target = acct_locked.parent_account or main_locked
                if target.pk == main_locked.pk:
                    main_locked.current_balance += sweep_amount
                else:
                    target_locked = TreasuryAccount.objects.select_for_update().get(pk=target.pk)
                    target_locked.current_balance += sweep_amount
                    target_locked.save(update_fields=['current_balance', 'updated_at'])

                acct_locked.current_balance = Decimal('0')
                acct_locked.save(update_fields=['current_balance', 'updated_at'])

                details.append({
                    'from': acct_locked.account_number,
                    'to': target.account_number,
                    'amount': str(sweep_amount),
                })
                total_swept += sweep_amount
                swept_count += 1

            main_locked.save(update_fields=['current_balance', 'updated_at'])

        logger.info(
            'CASH SWEEP: %d accounts swept, total: %s, Main TSA balance: %s',
            swept_count, total_swept, main_tsa.current_balance,
        )

        return {
            'swept': swept_count,
            'total_amount': str(total_swept),
            'main_tsa_balance': str(main_tsa.current_balance),
            'details': details,
        }


class BankReconciliationService:
    """
    Reconcile TSA transactions against bank statements.

    Flow:
    1. Import bank statement (CSV/manual entry)
    2. Auto-match: bank ref → PaymentInstruction.bank_reference
    3. Flag unmatched items (bank charges, errors, timing)
    4. Mark reconciled
    """

    @classmethod
    def get_unreconciled_items(cls, tsa_account_id: int, date_from=None, date_to=None) -> dict:
        """Get payment instructions not yet matched to bank statements."""
        from accounting.models.treasury import PaymentInstruction, TreasuryAccount

        tsa = TreasuryAccount.objects.get(pk=tsa_account_id)

        # Processed payments without bank reference = unreconciled
        qs = PaymentInstruction.objects.filter(
            tsa_account=tsa,
            status='PROCESSED',
        )
        if date_from:
            qs = qs.filter(processed_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(processed_at__date__lte=date_to)

        unreconciled = qs.filter(bank_reference='')
        reconciled = qs.exclude(bank_reference='')

        return {
            'tsa_account': str(tsa),
            'book_balance': str(tsa.current_balance),
            'last_reconciled': str(tsa.last_reconciled) if tsa.last_reconciled else None,
            'unreconciled_count': unreconciled.count(),
            'unreconciled_total': str(
                unreconciled.aggregate(total=models.Sum('amount'))['total'] or 0
            ),
            'reconciled_count': reconciled.count(),
            'reconciled_total': str(
                reconciled.aggregate(total=models.Sum('amount'))['total'] or 0
            ),
        }

    @classmethod
    def reconcile_item(cls, payment_instruction_id: int, bank_reference: str) -> None:
        """Mark a payment instruction as reconciled with bank statement reference."""
        from accounting.models.treasury import PaymentInstruction

        pi = PaymentInstruction.objects.get(pk=payment_instruction_id)
        pi.bank_reference = bank_reference
        pi.save(update_fields=['bank_reference', 'updated_at'])

    @classmethod
    def mark_account_reconciled(cls, tsa_account_id: int) -> None:
        """Mark TSA account as reconciled as of today."""
        from accounting.models.treasury import TreasuryAccount

        tsa = TreasuryAccount.objects.get(pk=tsa_account_id)
        tsa.last_reconciled = timezone.now().date()
        tsa.save(update_fields=['last_reconciled', 'updated_at'])
