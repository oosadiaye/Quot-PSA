from django.core.exceptions import ValidationError
from django.db import transaction


def is_dimensions_enabled(tenant):
    """Check if dimensions module is enabled for the tenant."""
    if not tenant:
        return True
    from tenants.models import is_dimensions_enabled as check_dimensions
    try:
        return check_dimensions(tenant)
    except Exception:
        return True


def check_budget_availability(dimensions, account, amount, date, transaction_type='GENERAL', transaction_id=0, user=None, tenant=None):
    """
    Check if a transaction amount is available in the unified budget.
    Returns: (is_allowed: bool, message: str)
    """
    from .models import UnifiedBudget

    # Skip if dimensions disabled or empty
    if tenant and not is_dimensions_enabled(tenant):
        return True, "Dimensions disabled"

    if not dimensions or not any(dimensions.values()):
        return True, "No dimensions provided"

    # Find matching budget
    fiscal_year = str(date.year) if date else None

    budget = UnifiedBudget.get_budget_for_transaction(
        dimensions=dimensions,
        account=account,
        fiscal_year=fiscal_year,
        period_type='MONTHLY',
        period_number=date.month if date else 1
    )

    if not budget:
        return True, "No budget defined for this account/period"

    return budget.check_availability(amount, transaction_type)


def consume_budget(dimensions, account, amount, date, transaction_type='GENERAL', transaction_id=0, user=None, tenant=None):
    """
    Consume (reserve) budget for a transaction.
    Creates an encumbrance against the budget.
    """
    from .models import UnifiedBudget, UnifiedBudgetEncumbrance

    if tenant and not is_dimensions_enabled(tenant):
        return None

    if not dimensions or not any(dimensions.values()):
        return None

    fiscal_year = str(date.year) if date else None

    with transaction.atomic():
        budget = UnifiedBudget.get_budget_for_transaction(
            dimensions=dimensions,
            account=account,
            fiscal_year=fiscal_year,
            period_type='MONTHLY',
            period_number=date.month if date else 1
        )

        if not budget:
            raise ValidationError(f"No budget found for {account.name}")

        # Lock the budget row to prevent concurrent over-commitment
        budget = UnifiedBudget.objects.select_for_update().get(pk=budget.pk)

        is_allowed, message, available = budget.check_availability(amount, transaction_type)

        if not is_allowed:
            raise ValidationError(f"Budget check failed: {message}")

        # Create encumbrance
        encumbrance = UnifiedBudgetEncumbrance.objects.create(
            budget=budget,
            reference_type=transaction_type,
            reference_id=transaction_id,
            encumbrance_date=date,
            amount=amount,
            status='ACTIVE',
            description=f"Budget reservation for {transaction_type}",
            created_by=user
        )

        return encumbrance
