"""Period Control Service

Provides unified period control across all accounting modules:
- Synchronized locking between FiscalPeriod and BudgetPeriod
- Consistent period status checks
- Period access validation
"""
import logging
from datetime import date
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class PeriodStatusResult:
    """Result of period status check."""
    can_post: bool
    can_adjust: bool
    can_invoice: bool
    can_payment: bool
    status: str
    period_name: str
    messages: List[str]


class PeriodControlService:
    """Service for unified period control across all modules."""

    LOCKED_STATUSES = ['CLOSED', 'LOCKED', 'Closed', 'Locked']
    OPEN_STATUSES = ['OPEN', 'ADJUSTMENT', 'Draft', 'Open', 'YearEnd']
    ADJUSTMENT_STATUSES = ['OPEN', 'ADJUSTMENT', 'YearEnd']

    @classmethod
    def get_period_for_date(
        cls,
        posting_date: date,
        period_type: str = 'MONTHLY'
    ) -> Optional[Any]:
        """
        Get the fiscal period for a given date.
        
        Args:
            posting_date: The date to look up
            period_type: Type of period ('MONTHLY', 'QUARTERLY', etc.)
            
        Returns:
            BudgetPeriod instance or None
        """
        from accounting.models import BudgetPeriod
        
        period = BudgetPeriod.objects.filter(
            start_date__lte=posting_date,
            end_date__gte=posting_date,
            period_type=period_type
        ).first()
        
        if not period:
            from accounting.models import FiscalPeriod
            period = FiscalPeriod.objects.filter(
                start_date__lte=posting_date,
                end_date__gte=posting_date,
                period_type__icontains=period_type.lower()
            ).first()
        
        return period

    @classmethod
    def check_period_status(
        cls,
        posting_date: date,
        document_type: str = 'journal'
    ) -> PeriodStatusResult:
        """
        Check if posting is allowed for a given date.
        
        Args:
            posting_date: The date to check
            document_type: Type of document ('journal', 'invoice', 'payment')
            
        Returns:
            PeriodStatusResult with all checks
        """
        messages = []
        
        budget_period = cls.get_period_for_date(posting_date, 'MONTHLY')
        fiscal_period = cls.get_period_for_date(posting_date, 'Monthly')
        
        can_post = True
        can_adjust = True
        can_invoice = True
        can_payment = True
        status = 'Open'
        period_name = str(posting_date)
        
        if budget_period:
            period_name = f"Budget: {budget_period}"
            status = budget_period.status
            
            if budget_period.status in cls.LOCKED_STATUSES:
                can_post = False
                can_adjust = False
                can_invoice = False
                can_payment = False
                messages.append(f"Budget period {budget_period} is locked")
            elif budget_period.status == 'CLOSED':
                can_post = False
                can_adjust = False
                messages.append(f"Budget period {budget_period} is closed")
            
            if not budget_period.allow_postings:
                can_post = False
                messages.append("Budget period does not allow postings")
            
            if not budget_period.allow_adjustments:
                can_adjust = False
        
        if fiscal_period:
            period_name = f"Fiscal: {fiscal_period}"
            
            if fiscal_period.status in cls.LOCKED_STATUSES:
                can_post = False
                can_adjust = False
                can_invoice = False
                can_payment = False
                messages.append(f"Fiscal period {fiscal_period} is locked")
            elif fiscal_period.is_closed:
                can_post = False
                messages.append(f"Fiscal period {fiscal_period} is closed")
            
            if not getattr(fiscal_period, 'allow_journal_entry', True):
                can_post = False
                messages.append("Fiscal period does not allow journal entries")
            
            if not getattr(fiscal_period, 'allow_invoice', True):
                can_invoice = False
                messages.append("Fiscal period does not allow invoices")
            
            if not getattr(fiscal_period, 'allow_payment', True):
                can_payment = False
                messages.append("Fiscal period does not allow payments")
        
        if not budget_period and not fiscal_period:
            can_post = False
            can_adjust = False
            can_invoice = False
            can_payment = False
            messages.append(f"No period defined for date {posting_date}")
        
        return PeriodStatusResult(
            can_post=can_post,
            can_adjust=can_adjust,
            can_invoice=can_invoice,
            can_payment=can_payment,
            status=status,
            period_name=period_name,
            messages=messages,
        )

    @classmethod
    def can_post_to_period(
        cls,
        posting_date: date,
        user: Any = None
    ) -> Tuple[bool, str]:
        """
        Quick check if posting is allowed.
        
        Args:
            posting_date: The date to check
            user: User performing the action (for access checks)
            
        Returns:
            Tuple of (is_allowed, message)
        """
        result = cls.check_period_status(posting_date)
        
        if user and not result.can_post:
            has_access = cls.check_user_period_access(user, posting_date)
            if has_access:
                return True, "Posting allowed via temporary access"
        
        if not result.can_post:
            return False, '; '.join(result.messages) if result.messages else 'Posting not allowed'
        
        return True, "Posting allowed"

    @classmethod
    def check_user_period_access(
        cls,
        user: Any,
        posting_date: date
    ) -> bool:
        """
        Check if user has temporary period access.
        
        Args:
            user: User to check
            posting_date: Date user is trying to post to
            
        Returns:
            True if user has access, False otherwise
        """
        from accounting.models import PeriodAccess
        
        period = cls.get_period_for_date(posting_date)
        if not period:
            return False
        
        now = timezone.now()
        
        access = PeriodAccess.objects.filter(
            user=user,
            is_active=True,
            start_date__lte=now,
            end_date__gte=now
        ).filter(
            Q(period=period) | Q(period__fiscal_year=period.fiscal_year if hasattr(period, 'fiscal_year') else None)
        ).exists()
        
        return access

    @classmethod
    def synchronize_period_status(
        cls,
        fiscal_year: int,
        period_number: int = None
    ) -> Dict[str, Any]:
        """
        Synchronize BudgetPeriod and FiscalPeriod statuses.
        
        Args:
            fiscal_year: Fiscal year to synchronize
            period_number: Specific period number (optional)
            
        Returns:
            Dictionary with sync results
        """
        from accounting.models import BudgetPeriod, FiscalPeriod
        
        results = {
            'synced': [],
            'errors': [],
        }
        
        fiscal_periods = FiscalPeriod.objects.filter(fiscal_year=fiscal_year)
        if period_number:
            fiscal_periods = fiscal_periods.filter(period_number=period_number)
        
        for fiscal in fiscal_periods:
            budget = BudgetPeriod.objects.filter(
                fiscal_year=fiscal.fiscal_year,
                period_type__icontains=fiscal.period_type.lower().replace('ly', ''),
            ).filter(
                Q(period_number=fiscal.period_number) |
                Q(start_date__month=fiscal.start_date.month)
            ).first()
            
            if budget:
                if fiscal.is_locked and budget.status != 'LOCKED':
                    budget.status = 'LOCKED'
                    budget.save()
                    results['synced'].append(f"Locked BudgetPeriod {budget}")
                
                elif fiscal.is_closed and budget.status == 'OPEN':
                    budget.status = 'CLOSED'
                    budget.save()
                    results['synced'].append(f"Closed BudgetPeriod {budget}")
                
                elif not fiscal.is_closed and not fiscal.is_locked and budget.status in cls.LOCKED_STATUSES:
                    results['errors'].append(
                        f"Cannot unlock BudgetPeriod {budget} - FiscalPeriod {fiscal} is locked"
                    )
        
        return results

    @classmethod
    def lock_period(
        cls,
        fiscal_year: int,
        period_number: int,
        user: Any,
        reason: str = ''
    ) -> Tuple[bool, str]:
        """
        Lock both BudgetPeriod and FiscalPeriod for a given period.
        
        Args:
            fiscal_year: Year to lock
            period_number: Period number to lock
            user: User performing the action
            reason: Reason for locking
            
        Returns:
            Tuple of (success, message)
        """
        from accounting.models import BudgetPeriod, FiscalPeriod
        
        try:
            budget = BudgetPeriod.objects.get(
                fiscal_year=fiscal_year,
                period_number=period_number
            )
            budget.lock(user)
        except BudgetPeriod.DoesNotExist:
            logger.debug(
                "lock_period: no BudgetPeriod found for FY%s-P%s; skipping budget lock",
                fiscal_year, period_number,
            )
        
        try:
            fiscal = FiscalPeriod.objects.get(
                fiscal_year=fiscal_year,
                period_number=period_number
            )
            fiscal.is_locked = True
            fiscal.closed_by = user
            fiscal.closed_date = timezone.now()
            fiscal.closed_reason = reason
            fiscal.save()
        except FiscalPeriod.DoesNotExist:
            return False, f"Period FY{fiscal_year}-P{period_number} not found"
        
        return True, f"Period FY{fiscal_year}-P{period_number} locked successfully"

    @classmethod
    def close_period(
        cls,
        fiscal_year: int,
        period_number: int,
        user: Any
    ) -> Tuple[bool, str]:
        """
        Close a period for month-end processing.
        
        Args:
            fiscal_year: Year to close
            period_number: Period number to close
            user: User performing the action
            
        Returns:
            Tuple of (success, message)
        """
        result = cls.check_period_status(
            date(fiscal_year, period_number * 1, 1)
        )
        
        if not result.can_adjust:
            return False, f"Cannot close period: {result.messages}"
        
        return cls.lock_period(fiscal_year, period_number, user, 'Month-end close')
