"""Cost Allocation Service

Provides automatic cost allocation and distribution:
- Rule-based cost allocation
- Percentage and actual cost distribution
- Journal generation for allocations
"""
from datetime import date
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from django.db import transaction
from django.contrib.auth.models import User
from accounting.models import CostAllocationRun, CostAllocationDetail


@dataclass
class AllocationResult:
    """Result of allocation calculation for a rule."""
    rule_id: int
    rule_name: str
    source_amount: Decimal
    total_allocated: Decimal
    targets: List[Dict[str, Any]]
    is_complete: bool


class CostAllocationService:
    """Service for cost allocation operations."""

    METHODS = ['Percentage', 'Equal', 'Actual', 'Hours', 'Revenue']

    @classmethod
    def calculate_allocation(
        cls,
        rule: 'CostAllocationRule'
    ) -> AllocationResult:
        """
        Calculate allocation for a single rule.
        
        Args:
            rule: CostAllocationRule instance
            
        Returns:
            AllocationResult with calculated amounts
        """
        source_amount = cls._get_source_amount(rule)
        
        if source_amount <= 0:
            return AllocationResult(
                rule_id=rule.id,
                rule_name=rule.name,
                source_amount=Decimal('0'),
                total_allocated=Decimal('0'),
                targets=[],
                is_complete=True,
            )
        
        percentage = Decimal(str(rule.percentage))
        allocated_amount = (source_amount * percentage / Decimal('100')).quantize(Decimal('0.01'))
        
        targets = [{
            'target_cost_center_id': rule.target_cost_center_id,
            'target_account_id': rule.target_cost_center.gl_account_id if rule.target_cost_center else None,
            'amount': allocated_amount,
            'percentage': percentage,
        }]
        
        return AllocationResult(
            rule_id=rule.id,
            rule_name=rule.name,
            source_amount=source_amount,
            total_allocated=allocated_amount,
            targets=targets,
            is_complete=True,
        )

    @classmethod
    def _get_source_amount(cls, rule: 'CostAllocationRule') -> Decimal:
        """Get the amount available for allocation from the source."""
        from accounting.models import GLBalance
        
        if not rule.source_account:
            return Decimal('0')
        
        balances = GLBalance.objects.filter(
            account=rule.source_account
        )
        
        if rule.source_cost_center:
            balances = balances.filter(cost_center=rule.source_cost_center)
        
        total_debit = sum(b.debit_balance for b in balances)
        total_credit = sum(b.credit_balance for b in balances)
        
        return (total_debit - total_credit).quantize(Decimal('0.01'))

    @classmethod
    def calculate_allocation_run(
        cls,
        run_date: date,
        fiscal_year: int = None,
        period: int = None,
        user: User = None,
        rule_ids: List[int] = None
    ) -> CostAllocationRun:
        """
        Calculate all cost allocations.
        
        Args:
            run_date: Date of allocation run
            fiscal_year: Fiscal year
            period: Period number
            user: User performing run
            rule_ids: Optional specific rule IDs
            
        Returns:
            CostAllocationRun with all calculations
        """
        from accounting.models import CostAllocationRule
        
        if fiscal_year is None:
            fiscal_year = run_date.year
        if period is None:
            period = run_date.month
        
        run = CostAllocationRun.objects.create(
            run_date=run_date,
            fiscal_year=fiscal_year,
            period=period,
            created_by=user,
            status='DRAFT',
        )
        
        rules = CostAllocationRule.objects.filter(is_active=True)
        if rule_ids:
            rules = rules.filter(id__in=rule_ids)
        
        rules_processed = 0
        total_allocated = Decimal('0')
        
        for rule in rules:
            allocation = cls.calculate_allocation(rule)
            
            if allocation.source_amount <= 0:
                continue
            
            for target in allocation.targets:
                if target['amount'] <= 0:
                    continue
                
                CostAllocationDetail.objects.create(
                    run=run,
                    rule=rule,
                    rule_name=rule.name,
                    source_cost_center=rule.source_cost_center,
                    source_account=rule.source_account,
                    source_amount=allocation.source_amount,
                    target_cost_center_id=target['target_cost_center_id'],
                    target_account_id=target['target_account_id'],
                    allocated_amount=target['amount'],
                    allocation_percentage=target['percentage'],
                )
                
                total_allocated += target['amount']
            
            rules_processed += 1
        
        run.rules_processed = rules_processed
        run.total_allocated = total_allocated
        run.status = 'CALCULATED'
        run.save()
        
        return run

    @classmethod
    def post_allocation(
        cls,
        run_id: int,
        user: User
    ) -> Tuple[bool, str, int]:
        """
        Post allocation journal entries.
        
        Args:
            run_id: CostAllocationRun ID
            user: User posting
            
        Returns:
            Tuple of (success, message, journal_id)
        """
        from accounting.models import JournalHeader, JournalLine
        
        try:
            run = CostAllocationRun.objects.get(id=run_id)
        except CostAllocationRun.DoesNotExist:
            return False, "Allocation run not found", 0
        
        if run.status != 'CALCULATED':
            return False, f"Cannot post: status is {run.status}", 0
        
        if run.total_allocated <= 0:
            return False, "Nothing to allocate", 0
        
        journal = None
        
        with transaction.atomic():
            journal = JournalHeader.objects.create(
                posting_date=run.run_date,
                description=f"Cost Allocation FY{run.fiscal_year} P{run.period}",
                reference_number=f"ALLOC-{run.fiscal_year}{run.period:02d}-{run.id}",
                status='Draft',
                source_module='accounting',
                source_document_id=run.pk,
            )
            
            for detail in run.details.all():
                if detail.allocated_amount <= 0:
                    continue
                
                if detail.source_account:
                    JournalLine.objects.create(
                        header=journal,
                        account=detail.source_account,
                        credit=detail.allocated_amount,
                        memo=f"Allocation: {detail.rule_name} -> {detail.target_cost_center}"
                    )
                
                if detail.target_account:
                    JournalLine.objects.create(
                        header=journal,
                        account=detail.target_account,
                        debit=detail.allocated_amount,
                        memo=f"Allocation: {detail.source_cost_center} -> {detail.target_cost_center}"
                    )
                
                detail.journal_line_id = journal.id
                detail.save()
            
            journal.status = 'Posted'
            journal.save()
            
            run.status = 'POSTED'
            run.posted_at = timezone.now()
            run.posted_by = user
            run.journal_id = journal.id
            run.save()
        
        return True, f"Posted allocation journal {journal.id}", journal.id

    @classmethod
    def execute_allocation_for_period(
        cls,
        period_end_date: date,
        fiscal_year: int = None,
        period: int = None,
        user: User = None
    ) -> Dict[str, Any]:
        """
        Execute complete allocation process for a period.
        
        Args:
            period_end_date: End date of the period
            fiscal_year: Fiscal year
            period: Period number
            user: User executing
            
        Returns:
            Dictionary with execution results
        """
        run = cls.calculate_allocation_run(
            run_date=period_end_date,
            fiscal_year=fiscal_year,
            period=period,
            user=user,
        )
        
        if run.total_allocated <= 0:
            return {
                'run_id': run.id,
                'status': 'NO_ALLOCATION',
                'rules_processed': run.rules_processed,
                'total_allocated': float(run.total_allocated),
                'journal_id': None,
            }
        
        success, message, journal_id = cls.post_allocation(run.id, user)
        
        return {
            'run_id': run.id,
            'status': run.status,
            'rules_processed': run.rules_processed,
            'total_allocated': float(run.total_allocated),
            'journal_id': journal_id,
            'message': message,
        }

    @classmethod
    def get_allocation_summary(
        cls,
        fiscal_year: int = None,
        period: int = None
    ) -> Dict[str, Any]:
        """
        Get allocation summary for a period.
        
        Args:
            fiscal_year: Fiscal year
            period: Period number
            
        Returns:
            Dictionary with summary data
        """
        runs = CostAllocationRun.objects.all()
        
        if fiscal_year:
            runs = runs.filter(fiscal_year=fiscal_year)
        if period:
            runs = runs.filter(period=period)
        
        total_allocated = sum(r.total_allocated for r in runs)
        total_posted = sum(
            r.total_allocated for r in runs.filter(status='POSTED')
        )
        
        details = []
        for detail in CostAllocationDetail.objects.filter(
            run__in=runs.filter(status='POSTED')
        ):
            details.append({
                'rule_name': detail.rule_name,
                'source_cost_center': str(detail.source_cost_center) if detail.source_cost_center else 'N/A',
                'target_cost_center': str(detail.target_cost_center) if detail.target_cost_center else 'N/A',
                'allocated_amount': float(detail.allocated_amount),
                'percentage': float(detail.allocation_percentage),
            })
        
        return {
            'fiscal_year': fiscal_year,
            'period': period,
            'total_allocated': float(total_allocated),
            'total_posted': float(total_posted),
            'runs_count': runs.count(),
            'posted_runs': runs.filter(status='POSTED').count(),
            'details': details,
        }

    @classmethod
    def create_allocation_rule(
        cls,
        name: str,
        source_cost_center_id: int,
        source_account_id: int,
        target_cost_center_id: int,
        allocation_method: str = 'Percentage',
        percentage: Decimal = Decimal('0'),
        is_active: bool = True
    ) -> 'CostAllocationRule':
        """
        Create a new cost allocation rule.
        
        Args:
            name: Rule name
            source_cost_center_id: Source cost center
            source_account_id: Source account
            target_cost_center_id: Target cost center
            allocation_method: Allocation method
            percentage: Allocation percentage
            is_active: Whether rule is active
            
        Returns:
            Created CostAllocationRule
        """
        from accounting.models import CostCenter, Account, CostAllocationRule
        
        rule = CostAllocationRule.objects.create(
            name=name,
            source_cost_center_id=source_cost_center_id,
            source_account_id=source_account_id,
            target_cost_center_id=target_cost_center_id,
            allocation_method=allocation_method,
            percentage=percentage,
            is_active=is_active,
        )
        
        return rule


try:
    from django.utils import timezone
except ImportError:
    timezone = None
