"""
Budget Validation Service — Quot PSE
Called by ALL transactional modules before any payment or commitment.
This is a hard gate — no exceptions, no bypasses.

Gate 1: Appropriation must exist (always enforced)
Gate 2: Warrant must be released (only if tenant.enforce_warrant = True)
Gate 3: Available balance must cover amount (always enforced)
"""
from decimal import Decimal
from django.db import connection


class BudgetExceededError(Exception):
    """Raised when an expenditure would exceed the available appropriation or warrant."""
    pass


def _is_warrant_enforced() -> bool:
    """Check tenant-level setting for warrant enforcement."""
    try:
        tenant = getattr(connection, 'tenant', None)
        if tenant:
            return getattr(tenant, 'enforce_warrant', False)
    except Exception:
        pass
    return False


class BudgetValidationService:

    @classmethod
    def validate_expenditure(
        cls,
        administrative_id: int,
        economic_id: int,
        fund_id: int,
        fiscal_year_id: int,
        amount: Decimal,
        functional_id: int = None,
        programme_id: int = None,
        source: str = 'PAYMENT',
    ) -> dict:
        """
        Hard-stop validation before any expenditure.

        Returns dict with appropriation_id, available_balance, warrant_id on success.
        Raises BudgetExceededError with actionable message on any failure.

        Warrant check is CONDITIONAL — controlled by tenant setting
        ``enforce_warrant``:
        - True  → Gate 2 active: warrant must be released
        - False → Gate 2 bypassed: only appropriation + balance checked
        """
        from budget.models import Appropriation
        from accounting.models.ncoa import EconomicSegment

        # 0. Revenue accounts (type 1) are NEVER hard-stopped — skip validation
        economic_seg = EconomicSegment.objects.filter(pk=economic_id).first()
        if economic_seg and economic_seg.account_type_code == '1':
            return {
                'approved':          True,
                'appropriation_id':  None,
                'warrant_id':        None,
                'available_balance': None,
                'execution_pct':     None,
                'note':              'Revenue account — statistical budget, no enforcement',
            }

        # 1. Find active appropriation (ALWAYS enforced)
        qs = Appropriation.objects.filter(
            administrative_id=administrative_id,
            economic_id=economic_id,
            fund_id=fund_id,
            fiscal_year_id=fiscal_year_id,
            status='ACTIVE',
        )
        if not qs.exists():
            raise BudgetExceededError(
                f"No active appropriation found for MDA "
                f"(Admin ID: {administrative_id}, Economic ID: {economic_id}, "
                f"Fund ID: {fund_id}, Fiscal Year: {fiscal_year_id}). "
                f"Payment cannot proceed without legislative appropriation. "
                f"Contact the Budget Office."
            )

        appropriation = qs.first()

        # 2. Check warrant (CONDITIONAL — based on tenant setting)
        warrant_id = None
        if _is_warrant_enforced():
            active_warrant = appropriation.warrants.filter(status='RELEASED').last()
            if not active_warrant:
                raise BudgetExceededError(
                    f"Appropriation exists (ID: {appropriation.pk}) but no active warrant "
                    f"has been released for {appropriation.administrative.name}. "
                    f"Contact the Accountant General's Office for warrant release."
                )
            warrant_id = active_warrant.pk

        # 3. Check available balance (ALWAYS enforced)
        available = appropriation.available_balance
        if amount > available:
            deficit = amount - available
            raise BudgetExceededError(
                f"Insufficient appropriation balance for "
                f"{appropriation.administrative.name} — {appropriation.economic.name}.\n"
                f"  Requested:  NGN {amount:>15,.2f}\n"
                f"  Available:  NGN {available:>15,.2f}\n"
                f"  Deficit:    NGN {deficit:>15,.2f}\n"
                f"A Supplementary Appropriation or Virement is required."
            )

        return {
            'approved':          True,
            'appropriation_id':  appropriation.pk,
            'warrant_id':        warrant_id,
            'available_balance': available,
            'execution_pct':     appropriation.execution_rate,
        }
