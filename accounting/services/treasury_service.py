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
    def process_transfer(
        cls,
        *,
        source_tsa,
        target_tsa,
        amount,
        actor,
        transfer_date=None,
        narration: str = '',
    ):
        """Atomic inter-TSA transfer.

        Moves cash between two ``TreasuryAccount`` rows — used for
        manual liquidity rebalancing between Main TSA, sub-accounts,
        and consolidated/revenue accounts when the daily auto-sweep
        is not the right fit (e.g. an ad-hoc fund top-up to an MDA
        zero-balance account ahead of a large warrant).

        Mirrors the BankAccount.transfer pattern (audit fix H10) but
        keyed on ``gl_cash_account`` (TSA-side FK) rather than
        ``gl_account``. Posts the JV via ``IPSASJournalService.post_journal``
        so the chokepoint (``assert_balanced`` +
        ``invalidate_period_reports`` + GLBalance roll-up) fires —
        keeping the GL view of cash, TSA balances, and reports in
        lockstep.

            DR  target_tsa.gl_cash_account     amount
            CR  source_tsa.gl_cash_account     amount

        Race-safety: both TSA rows are locked in pk-order via
        ``select_for_update`` to avoid deadlocks under concurrent
        opposite-direction transfers. Sufficient-funds check is done
        AFTER the lock, against the freshly-locked balance.

        Args:
            source_tsa:    TreasuryAccount cash leaves
            target_tsa:    TreasuryAccount cash arrives
            amount:        Decimal — must be > 0
            actor:         User initiating the transfer (audit trail)
            transfer_date: Optional date (defaults to today)
            narration:     Optional human description appended to journal

        Returns:
            JournalHeader of the posted transfer JV.

        Raises:
            ValueError: invalid inputs (same TSA, non-positive amount,
                        missing gl_cash_account, insufficient funds).
        """
        from datetime import date as _date
        from decimal import Decimal as _Decimal
        from django.db.models import F as _F
        from django.utils import timezone
        from accounting.models import (
            JournalHeader, JournalLine, TransactionSequence,
        )
        from accounting.models.treasury import TreasuryAccount
        from accounting.services.ipsas_journal_service import IPSASJournalService

        # Coerce amount to Decimal at the boundary so float-string-from-
        # JSON inputs don't sneak through (M8 lesson).
        try:
            amount = _Decimal(str(amount))
        except Exception as exc:
            raise ValueError(f'amount must be a decimal value: {exc}')

        if amount <= _Decimal('0'):
            raise ValueError('amount must be greater than zero.')

        if source_tsa.pk == target_tsa.pk:
            raise ValueError('Source and target TSA accounts must differ.')

        if not source_tsa.is_active or not target_tsa.is_active:
            raise ValueError('Both source and target TSAs must be active.')

        if not source_tsa.gl_cash_account_id or not target_tsa.gl_cash_account_id:
            raise ValueError(
                'Both source and target TSAs must have gl_cash_account configured. '
                'Edit the TreasuryAccount records to assign GL control accounts before transferring.'
            )

        first_pk = min(source_tsa.pk, target_tsa.pk)
        second_pk = max(source_tsa.pk, target_tsa.pk)

        with transaction.atomic():
            # Lock both rows in pk-order — pulls fresh
            # ``current_balance`` for the funds check below.
            # ``of=('self',)`` locks only the TreasuryAccount rows: without
            # it, ``select_related('gl_cash_account')`` (a nullable FK → LEFT
            # OUTER JOIN) makes Postgres refuse — "FOR UPDATE cannot be
            # applied to the nullable side of an outer join" — and every
            # transfer 500s.
            locked = list(
                TreasuryAccount.objects
                .select_for_update(of=('self',))
                .select_related('gl_cash_account')
                .filter(pk__in=[first_pk, second_pk])
                .order_by('pk')
            )
            if len(locked) != 2:
                raise ValueError('One or both TSA accounts not found.')
            by_id = {ta.pk: ta for ta in locked}
            source_locked = by_id[source_tsa.pk]
            target_locked = by_id[target_tsa.pk]

            if (source_locked.current_balance or _Decimal('0')) < amount:
                raise ValueError(
                    f'Insufficient funds in source TSA '
                    f'({source_locked.account_number}): '
                    f'{source_locked.current_balance} < {amount}.'
                )

            # get_next already prepends the prefix, so pass it once.
            jv_ref = TransactionSequence.get_next('tsa_transfer', 'TT-')
            description = (
                f"TSA transfer {source_locked.account_number} → "
                f"{target_locked.account_number}"
            )
            if narration:
                description = f"{description} | {narration}"

            journal = JournalHeader.objects.create(
                posting_date=transfer_date or _date.today(),
                reference_number=jv_ref,
                description=description,
                # Inherit MDA from the source TSA (when set) so the GL
                # roll-up lands on that MDA's bucket — matches how
                # other TSA-cash postings (process_payment /
                # process_revenue) already work. JournalHeader.mda is a
                # legacy MDA; TreasuryAccount.mda is an AdministrativeSegment,
                # so bridge via legacy_mda (or None).
                mda=getattr(getattr(source_locked, 'mda', None), 'legacy_mda', None),
                fund=getattr(source_locked.fund_segment, 'legacy_fund', None) if source_locked.fund_segment_id else None,
                status='Draft',
                source_module='treasury',
                posted_by=actor,
            )
            JournalLine.objects.create(
                header=journal,
                account=target_locked.gl_cash_account,
                debit=amount,
                credit=_Decimal('0'),
                memo=f"Transfer in from TSA {source_locked.account_number}",
            )
            JournalLine.objects.create(
                header=journal,
                account=source_locked.gl_cash_account,
                debit=_Decimal('0'),
                credit=amount,
                memo=f"Transfer out to TSA {target_locked.account_number}",
            )

            # Post via the chokepoint — assert_balanced + cache invalidation.
            # Capture the re-fetched posted row so the returned journal is
            # not the stale Draft object.
            journal = IPSASJournalService.post_journal(journal, actor)

            # F()-update both TSA balances under the same atomic.
            TreasuryAccount.objects.filter(pk=source_locked.pk).update(
                current_balance=_F('current_balance') - amount,
                updated_at=timezone.now(),
            )
            TreasuryAccount.objects.filter(pk=target_locked.pk).update(
                current_balance=_F('current_balance') + amount,
                updated_at=timezone.now(),
            )

            logger.info(
                'TSA TRANSFER: %s -> %s | Amount: %s | JV: %s | by=%s',
                source_locked.account_number, target_locked.account_number,
                amount, jv_ref, getattr(actor, 'username', actor),
            )

            return journal

    @classmethod
    def gl_cash_balance(cls, tsa) -> 'Decimal':
        """The authoritative cash position: the net of the TSA's GL cash
        account over every posted journal line (a debit raises cash, a
        credit lowers it). This is the number ``current_balance`` should
        equal — double-entry is the source of truth, the denormalised
        field is a cache of it."""
        from decimal import Decimal as _Decimal
        from django.db.models import Sum
        from accounting.models.gl import JournalLine

        if not tsa.gl_cash_account_id:
            return _Decimal('0')
        agg = (
            JournalLine.objects
            .filter(account_id=tsa.gl_cash_account_id, header__status='Posted')
            .aggregate(dr=Sum('debit'), cr=Sum('credit'))
        )
        return (agg['dr'] or _Decimal('0')) - (agg['cr'] or _Decimal('0'))

    @classmethod
    def reconcile_balance(cls, tsa) -> 'Decimal':
        """Set one TSA's ``current_balance`` to its GL cash net and return it.

        Repairs drift from any posting path that touched the GL cash
        account without updating the field (e.g. vendor advances). Idempotent
        — running it twice leaves the same result.
        """
        from django.db.models import F  # noqa: F401  (kept for symmetry)
        from django.utils import timezone
        from accounting.models.treasury import TreasuryAccount

        gl_net = cls.gl_cash_balance(tsa)
        TreasuryAccount.objects.filter(pk=tsa.pk).update(
            current_balance=gl_net, updated_at=timezone.now(),
        )
        logger.info(
            'TSA RECONCILE: %s | %s -> %s',
            tsa.account_number, tsa.current_balance, gl_net,
        )
        return gl_net

    @classmethod
    def reconcile_from_gl_account(cls, gl_account) -> None:
        """Reconcile every TSA that uses ``gl_account`` as its cash control.

        Called right after a posting that credits/debits a TSA cash GL
        account outside the balance-updating services (vendor advances,
        their clearances), so ``current_balance`` never lags the GL for
        those paths again.
        """
        from accounting.models.treasury import TreasuryAccount

        acct_id = getattr(gl_account, 'pk', gl_account)
        for tsa in TreasuryAccount.objects.filter(gl_cash_account_id=acct_id):
            cls.reconcile_balance(tsa)

    @classmethod
    def reconcile_all(cls, *, dry_run: bool = False):
        """Reconcile every TSA with a GL cash account. Returns a list of
        ``(tsa, before, after)`` for reporting. ``dry_run`` computes the
        target without writing."""
        from accounting.models.treasury import TreasuryAccount

        out = []
        for tsa in TreasuryAccount.objects.exclude(gl_cash_account__isnull=True):
            before = tsa.current_balance
            after = cls.gl_cash_balance(tsa) if dry_run else cls.reconcile_balance(tsa)
            out.append((tsa, before, after))
        return out

    @classmethod
    def record_cash_movement(
        cls,
        *,
        tsa,
        direction: str,
        amount,
        contra_account,
        actor,
        entry_date=None,
        narration: str = '',
    ):
        """Record a manual cash-book entry on a TSA account.

        A direct incoming or outgoing movement whose other leg the
        operator chooses — for cash that neither arrives as a
        ``RevenueCollection`` nor leaves as a ``PaymentInstruction``:
        bank charges, interest, refunds, direct lodgements, corrections.
        Any active TSA can record either direction.

        Posts a balanced JV through the same chokepoint as a transfer
        (``IPSASJournalService.post_journal`` → assert_balanced + cache
        invalidation + GL roll-up), so the GL, the TSA balance, and the
        ledger stay in lockstep — and the entry shows in the ledger,
        because its ``source_module`` is not a revenue/payment document.

            Incoming:  DR  TSA cash        CR  contra
            Outgoing:  DR  contra          CR  TSA cash

        Args:
            tsa:            TreasuryAccount the cash moves on.
            direction:      'IN' (incoming) or 'OUT' (outgoing).
            amount:         Decimal — must be > 0.
            contra_account: the Account forming the other leg.
            actor:          User recording the entry (audit trail).
            entry_date:     Optional posting date (defaults to today).
            narration:      Optional human description.

        Returns:
            The posted JournalHeader.

        Raises:
            ValueError: invalid inputs (bad direction, non-positive
                        amount, inactive TSA, missing gl_cash_account,
                        missing/duplicate contra, insufficient funds).
        """
        from datetime import date as _date
        from decimal import Decimal as _Decimal
        from django.db.models import F as _F
        from django.utils import timezone
        from accounting.models import (
            JournalHeader, JournalLine, TransactionSequence,
        )
        from accounting.models.treasury import TreasuryAccount
        from accounting.services.ipsas_journal_service import IPSASJournalService

        try:
            amount = _Decimal(str(amount))
        except Exception as exc:
            raise ValueError(f'amount must be a decimal value: {exc}')
        if amount <= _Decimal('0'):
            raise ValueError('amount must be greater than zero.')

        direction = (direction or '').upper()
        if direction not in ('IN', 'OUT'):
            raise ValueError("direction must be 'IN' (incoming) or 'OUT' (outgoing).")

        if not tsa.is_active:
            raise ValueError('TSA account must be active.')
        if not tsa.gl_cash_account_id:
            raise ValueError(
                'This TSA has no gl_cash_account configured; assign a GL '
                'control account on the TreasuryAccount first.'
            )
        if contra_account is None:
            raise ValueError(
                'A contra GL account is required — it is the other side of the entry.'
            )
        if contra_account.pk == tsa.gl_cash_account_id:
            raise ValueError('The contra account must differ from the TSA cash account.')

        with transaction.atomic():
            # ``of=('self',)`` locks only the TreasuryAccount row. Without it,
            # ``select_related('gl_cash_account')`` (a nullable FK → LEFT OUTER
            # JOIN) makes Postgres refuse: "FOR UPDATE cannot be applied to the
            # nullable side of an outer join".
            tsa_locked = (
                TreasuryAccount.objects
                .select_for_update(of=('self',))
                .select_related('gl_cash_account')
                .get(pk=tsa.pk)
            )

            if direction == 'OUT' and (tsa_locked.current_balance or _Decimal('0')) < amount:
                raise ValueError(
                    f'Insufficient funds in {tsa_locked.account_number}: '
                    f'{tsa_locked.current_balance} < {amount}.'
                )

            label = 'Incoming' if direction == 'IN' else 'Outgoing'
            # get_next already prepends the prefix, so pass it once.
            jv_ref = TransactionSequence.get_next('tsa_cashbook', 'CB-')
            description = f"TSA cash book ({label}) {tsa_locked.account_number}"
            if narration:
                description = f"{description} | {narration}"

            journal = JournalHeader.objects.create(
                posting_date=entry_date or _date.today(),
                reference_number=jv_ref,
                description=description,
                # JournalHeader.mda is a legacy MDA; TreasuryAccount.mda is
                # an AdministrativeSegment. Bridge via legacy_mda (or None).
                mda=getattr(getattr(tsa_locked, 'mda', None), 'legacy_mda', None),
                fund=(
                    getattr(tsa_locked.fund_segment, 'legacy_fund', None)
                    if tsa_locked.fund_segment_id else None
                ),
                status='Draft',
                source_module='treasury_cashbook',
                posted_by=actor,
            )
            cash = tsa_locked.gl_cash_account
            memo = narration or f'Cash book {label.lower()}'
            if direction == 'IN':
                JournalLine.objects.create(
                    header=journal, account=cash, debit=amount, credit=_Decimal('0'), memo=memo,
                )
                JournalLine.objects.create(
                    header=journal, account=contra_account, debit=_Decimal('0'), credit=amount, memo=memo,
                )
            else:
                JournalLine.objects.create(
                    header=journal, account=contra_account, debit=amount, credit=_Decimal('0'), memo=memo,
                )
                JournalLine.objects.create(
                    header=journal, account=cash, debit=_Decimal('0'), credit=amount, memo=memo,
                )

            # Post via the chokepoint — assert_balanced + cache invalidation.
            # post_journal re-fetches under select_for_update and returns the
            # posted row, so capture it (the local object is otherwise stale).
            journal = IPSASJournalService.post_journal(journal, actor)

            delta = amount if direction == 'IN' else -amount
            TreasuryAccount.objects.filter(pk=tsa_locked.pk).update(
                current_balance=_F('current_balance') + delta,
                updated_at=timezone.now(),
            )

            logger.info(
                'TSA CASHBOOK %s: %s | Amount: %s | JV: %s | by=%s',
                label, tsa_locked.account_number, amount, jv_ref,
                getattr(actor, 'username', actor),
            )
            return journal

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
