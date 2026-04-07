from decimal import Decimal
from django.db.models import Sum
from .models import Budget, BudgetCheckLog, BudgetPeriod


def is_dimensions_enabled_for_budget(tenant):
    """Check if dimensions module is enabled for the tenant."""
    from tenants.models import is_dimensions_enabled
    try:
        return is_dimensions_enabled(tenant)
    except Exception:
        return True


def get_active_budget(dimensions, account, date, tenant=None):
    """
    Find the active budget for a given set of dimensions, account, and date.
    dimensions: dict with 'fund', 'function', 'program', 'geo', 'mda'
    """
    # If dimensions are disabled or dimensions dict is empty, skip dimension-based lookup
    if tenant and not is_dimensions_enabled_for_budget(tenant):
        return None
    
    if not dimensions or not any(dimensions.values()):
        return None

    # Find active budget period for the date
    period = BudgetPeriod.objects.filter(
        start_date__lte=date,
        end_date__gte=date,
        status='ACTIVE'
    ).first()
    
    if not period:
        # Fallback to any period if no ACTIVE one found for the date
        period = BudgetPeriod.objects.filter(
            start_date__lte=date,
            end_date__gte=date
        ).first()
        
    if not period:
        return None
        
    return Budget.objects.filter(
        period=period,
        account=account,
        mda=dimensions.get('mda'),
        fund=dimensions.get('fund'),
        function=dimensions.get('function'),
        program=dimensions.get('program'),
        geo=dimensions.get('geo')
    ).first()

def check_budget_availability(dimensions, account, amount, date, transaction_type, transaction_id, user=None, tenant=None):
    """
    Check if a transaction amount is available in the budget.
    Uses select_for_update to prevent race conditions.
    Returns: (is_allowed: bool, message: str)
    """
    from django.db import transaction
    
    # If dimensions are disabled or dimensions are not provided, skip budget check
    if tenant and not is_dimensions_enabled_for_budget(tenant):
        return True, "Dimensions module disabled. Budget check skipped."
    
    if not dimensions or not any(dimensions.values()):
        return True, "No dimensions provided. Budget check skipped."

    with transaction.atomic():
        budget = Budget.objects.select_for_update().filter(
            period__start_date__lte=date,
            period__end_date__gte=date,
            account=account,
            mda=dimensions.get('mda'),
            fund=dimensions.get('fund'),
            function=dimensions.get('function'),
            program=dimensions.get('program'),
            geo=dimensions.get('geo')
        ).first()

        if not budget:
            # PF-16: When no budget exists, respect the account's control level.
            # Look up the default control level from settings; default to WARNING.
            from django.conf import settings as django_settings
            default_control = getattr(django_settings, 'BUDGET_DEFAULT_CONTROL_LEVEL', 'WARNING')
            if default_control == 'HARD_STOP':
                return False, "No budget defined for this account/period. Transaction blocked."
            return True, "Warning: No budget defined for this account/period. Proceeding without BAC."

        is_available, message, available = budget.check_availability(amount)

        BudgetCheckLog.objects.create(
            budget=budget,
            transaction_type=transaction_type,
            transaction_id=transaction_id,
            requested_amount=amount,
            available_amount=available,
            check_result='PASSED' if is_available else ('WARNING' if budget.control_level == 'WARNING' else 'BLOCKED')
        )

    return is_available, message
