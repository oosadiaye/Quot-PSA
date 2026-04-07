"""Bank Reconciliation Service

Provides automated bank reconciliation matching:
- Statement import and parsing
- Auto-matching algorithms
- Outstanding items tracking
- Reconciliation reports
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from django.db import transaction
from django.contrib.auth.models import User
from accounting.models import BankStatement, BankStatementLine


@dataclass
class MatchCandidate:
    """Candidate for bank statement matching."""
    transaction_id: int
    transaction_type: str
    transaction_date: date
    amount: Decimal
    reference: str
    match_score: float
    match_type: str


@dataclass
class ReconciliationResult:
    """Result of reconciliation operation."""
    statement_id: int
    total_lines: int
    matched_lines: int
    unmatched_lines: int
    total_debit: Decimal
    total_credit: Decimal
    matched_debit: Decimal
    matched_credit: Decimal
    difference: Decimal
    is_reconciled: bool
    matches: List[Dict[str, Any]]


class BankReconciliationService:
    """Service for bank reconciliation operations."""

    MATCH_TOLERANCE_AMOUNT = Decimal('0.01')
    MATCH_TOLERANCE_DAYS = 5

    @classmethod
    def import_statement(
        cls,
        bank_account_id: int,
        statement_data: List[Dict[str, Any]],
        user: User,
        statement_number: str = '',
        statement_date: date = None,
        start_date: date = None,
        end_date: date = None,
        opening_balance: Decimal = None,
        closing_balance: Decimal = None,
        file_name: str = ''
    ) -> BankStatement:
        """
        Import a bank statement with all its lines.
        
        Args:
            bank_account_id: Bank account ID
            statement_data: List of transaction dictionaries
            user: User importing the statement
            statement_number: Statement identifier
            statement_date: Date of statement
            start_date: Statement period start
            end_date: Statement period end
            opening_balance: Opening balance
            closing_balance: Closing balance
            file_name: Original file name
            
        Returns:
            BankStatement instance
        """
        with transaction.atomic():
            statement = BankStatement.objects.create(
                bank_account_id=bank_account_id,
                statement_number=statement_number,
                statement_date=statement_date or date.today(),
                start_date=start_date or date.today(),
                end_date=end_date or date.today(),
                opening_balance=opening_balance or Decimal('0'),
                closing_balance=closing_balance or Decimal('0'),
                imported_by=user,
                file_name=file_name,
                status='IMPORTED',
            )
            
            for idx, line_data in enumerate(statement_data, 1):
                BankStatementLine.objects.create(
                    statement=statement,
                    line_number=idx,
                    transaction_date=line_data.get('date', date.today()),
                    value_date=line_data.get('value_date'),
                    description=line_data.get('description', ''),
                    reference=line_data.get('reference', ''),
                    debit_amount=Decimal(str(line_data.get('debit', 0))),
                    credit_amount=Decimal(str(line_data.get('credit', 0))),
                    balance=Decimal(str(line_data.get('balance', 0))),
                    transaction_type=line_data.get('type', ''),
                )
            
            statement.status = 'PROCESSING'
            statement.save()
            
            return statement

    @classmethod
    def find_match_candidates(
        cls,
        statement_line: BankStatementLine,
        bank_account_id: int
    ) -> List[MatchCandidate]:
        """
        Find potential matches for a statement line.
        
        Args:
            statement_line: Bank statement line
            bank_account_id: Bank account ID
            
        Returns:
            List of MatchCandidate sorted by score
        """
        from accounting.models import Payment, Receipt
        
        candidates = []
        amount = statement_line.amount
        
        is_credit = statement_line.is_credit
        
        if is_credit:
            payments = Payment.objects.filter(
                bank_account_id=bank_account_id,
                total_amount=amount,
                status='Posted',
            ).filter(
                payment_date__gte=statement_line.transaction_date - timedelta(days=cls.MATCH_TOLERANCE_DAYS),
                payment_date__lte=statement_line.transaction_date + timedelta(days=cls.MATCH_TOLERANCE_DAYS),
            )
            
            for payment in payments:
                score = cls._calculate_match_score(
                    statement_line,
                    payment.payment_date,
                    payment.total_amount,
                    payment.reference_number or payment.payment_number
                )
                candidates.append(MatchCandidate(
                    transaction_id=payment.id,
                    transaction_type='PAYMENT',
                    transaction_date=payment.payment_date,
                    amount=payment.total_amount,
                    reference=payment.reference_number or payment.payment_number,
                    match_score=score,
                    match_type='EXACT' if score >= 1.0 else 'CANDIDATE',
                ))
        
        else:
            receipts = Receipt.objects.filter(
                bank_account_id=bank_account_id,
                total_amount=amount,
                status='Posted',
            ).filter(
                receipt_date__gte=statement_line.transaction_date - timedelta(days=cls.MATCH_TOLERANCE_DAYS),
                receipt_date__lte=statement_line.transaction_date + timedelta(days=cls.MATCH_TOLERANCE_DAYS),
            )
            
            for receipt in receipts:
                score = cls._calculate_match_score(
                    statement_line,
                    receipt.receipt_date,
                    receipt.total_amount,
                    receipt.reference_number or receipt.receipt_number
                )
                candidates.append(MatchCandidate(
                    transaction_id=receipt.id,
                    transaction_type='RECEIPT',
                    transaction_date=receipt.receipt_date,
                    amount=receipt.total_amount,
                    reference=receipt.reference_number or receipt.receipt_number,
                    match_score=score,
                    match_type='EXACT' if score >= 1.0 else 'CANDIDATE',
                ))
        
        candidates.sort(key=lambda x: x.match_score, reverse=True)
        return candidates

    @classmethod
    def _calculate_match_score(
        cls,
        statement_line: BankStatementLine,
        transaction_date: date,
        amount: Decimal,
        reference: str
    ) -> float:
        """Calculate match score between statement and GL transaction."""
        score = 0.0
        
        if amount == statement_line.amount:
            score += 0.5
        
        date_diff = abs((statement_line.transaction_date - transaction_date).days)
        if date_diff == 0:
            score += 0.3
        elif date_diff <= cls.MATCH_TOLERANCE_DAYS:
            score += 0.3 * (1 - date_diff / cls.MATCH_TOLERANCE_DAYS)
        
        if reference and statement_line.reference:
            if reference.lower() in statement_line.reference.lower():
                score += 0.2
        
        return min(score, 1.0)

    @classmethod
    def auto_match_statement(
        cls,
        statement_id: int,
        match_threshold: float = 0.8
    ) -> ReconciliationResult:
        """
        Automatically match all lines in a statement.
        
        Args:
            statement_id: BankStatement ID
            match_threshold: Minimum score to auto-match
            
        Returns:
            ReconciliationResult with matching statistics
        """
        try:
            statement = BankStatement.objects.get(id=statement_id)
        except BankStatement.DoesNotExist:
            raise ValueError(f"Statement {statement_id} not found")
        
        matched_lines = 0
        matches = []
        matched_debit = Decimal('0')
        matched_credit = Decimal('0')
        
        for line in statement.lines.filter(match_status='UNMATCHED'):
            candidates = cls.find_match_candidates(line, statement.bank_account_id)
            
            if candidates and candidates[0].match_score >= match_threshold:
                best_match = candidates[0]
                
                line.match_status = 'MATCHED'
                line.matched_transaction_type = best_match.transaction_type
                line.matched_transaction_id = best_match.transaction_id
                line.matched_date = datetime.now()
                line.save()
                
                matched_lines += 1
                matched_debit += line.debit_amount
                matched_credit += line.credit_amount
                
                matches.append({
                    'line_id': line.id,
                    'transaction_type': best_match.transaction_type,
                    'transaction_id': best_match.transaction_id,
                    'score': best_match.match_score,
                    'type': best_match.match_type,
                })
        
        total_debit = sum(line.debit_amount for line in statement.lines.all())
        total_credit = sum(line.credit_amount for line in statement.lines.all())
        
        return ReconciliationResult(
            statement_id=statement_id,
            total_lines=statement.lines.count(),
            matched_lines=matched_lines,
            unmatched_lines=statement.lines.filter(match_status='UNMATCHED').count(),
            total_debit=total_debit,
            total_credit=total_credit,
            matched_debit=matched_debit,
            matched_credit=matched_credit,
            difference=abs(total_debit - total_credit),
            is_reconciled=statement.lines.filter(match_status='UNMATCHED').count() == 0,
            matches=matches,
        )

    @classmethod
    def match_line_manually(
        cls,
        line_id: int,
        transaction_type: str,
        transaction_id: int,
        user: User
    ) -> BankStatementLine:
        """
        Manually match a statement line to a GL transaction.
        
        Args:
            line_id: BankStatementLine ID
            transaction_type: Type of GL transaction
            transaction_id: GL transaction ID
            user: User performing the match
            
        Returns:
            Updated BankStatementLine
        """
        line = BankStatementLine.objects.get(id=line_id)
        
        line.match_status = 'MANUAL'
        line.matched_transaction_type = transaction_type
        line.matched_transaction_id = transaction_id
        line.matched_date = datetime.now()
        line.save()
        
        return line

    @classmethod
    def unreconcile_line(
        cls,
        line_id: int,
        user: User
    ) -> BankStatementLine:
        """Remove match from a statement line."""
        line = BankStatementLine.objects.get(id=line_id)
        line.match_status = 'UNMATCHED'
        line.matched_transaction_type = ''
        line.matched_transaction_id = None
        line.matched_date = None
        line.save()
        return line

    @classmethod
    def create_reconciliation(
        cls,
        statement_id: int,
        user: User,
        statement_balance: Decimal = None,
        book_balance: Decimal = None,
        deposits_in_transit: Decimal = Decimal('0'),
        outstanding_checks: Decimal = Decimal('0'),
        bank_charges: Decimal = Decimal('0'),
        other_adjustments: Decimal = Decimal('0')
    ) -> 'BankReconciliation':
        """Create a formal bank reconciliation record."""
        from accounting.models import BankReconciliation as BRModel
        
        statement = BankStatement.objects.get(id=statement_id)
        
        matched_debit = sum(
            line.debit_amount 
            for line in statement.lines.filter(match_status__in=['MATCHED', 'MANUAL'])
        )
        matched_credit = sum(
            line.credit_amount 
            for line in statement.lines.filter(match_status__in=['MATCHED', 'MANUAL'])
        )
        
        if statement_balance is None:
            statement_balance = statement.closing_balance
        
        calculated_book = matched_debit - matched_credit
        
        difference = statement_balance - calculated_book - deposits_in_transit + outstanding_checks - bank_charges - other_adjustments
        
        reconciliation = BRModel.objects.create(
            bank_account=statement.bank_account,
            statement_date=statement.statement_date,
            statement_balance=statement_balance,
            book_balance=calculated_book,
            reconciled_balance=statement_balance - difference,
            deposits_in_transit=deposits_in_transit,
            outstanding_checks=outstanding_checks,
            bank_charges=bank_charges,
            difference=difference,
            reconciled_by=user,
            status='Draft',
        )
        
        return reconciliation

    @classmethod
    def get_unmatched_items(
        cls,
        bank_account_id: int,
        start_date: date = None,
        end_date: date = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all unmatched items for a bank account.
        
        Args:
            bank_account_id: Bank account ID
            start_date: Filter start date
            end_date: Filter end date
            
        Returns:
            Dictionary with deposits_in_transit and outstanding_checks
        """
        from accounting.models import Payment, Receipt
        
        payments = Payment.objects.filter(
            bank_account_id=bank_account_id,
            status='Posted',
        )
        receipts = Receipt.objects.filter(
            bank_account_id=bank_account_id,
            status='Posted',
        )
        
        if start_date:
            payments = payments.filter(payment_date__gte=start_date)
            receipts = receipts.filter(receipt_date__gte=start_date)
        if end_date:
            payments = payments.filter(payment_date__lte=end_date)
            receipts = receipts.filter(receipt_date__lte=end_date)
        
        matched_payment_ids = BankStatementLine.objects.filter(
            bank_account__bank_account_id=bank_account_id,
            matched_transaction_type='PAYMENT',
            match_status__in=['MATCHED', 'MANUAL']
        ).values_list('matched_transaction_id', flat=True)
        
        matched_receipt_ids = BankStatementLine.objects.filter(
            matched_transaction_type='RECEIPT',
            match_status__in=['MATCHED', 'MANUAL']
        ).values_list('matched_transaction_id', flat=True)
        
        outstanding_checks = [
            {
                'id': p.id,
                'date': p.payment_date,
                'reference': p.payment_number,
                'amount': p.total_amount,
                'vendor': str(p.vendor) if p.vendor else 'Unknown',
            }
            for p in payments.exclude(id__in=matched_payment_ids)
        ]
        
        deposits_in_transit = [
            {
                'id': r.id,
                'date': r.receipt_date,
                'reference': r.receipt_number,
                'amount': r.total_amount,
                'customer': str(r.customer) if r.customer else 'Unknown',
            }
            for r in receipts.exclude(id__in=matched_receipt_ids)
        ]
        
        return {
            'outstanding_checks': outstanding_checks,
            'deposits_in_transit': deposits_in_transit,
            'total_checks': sum(item['amount'] for item in outstanding_checks),
            'total_deposits': sum(item['amount'] for item in deposits_in_transit),
        }


from datetime import timedelta
