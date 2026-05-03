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
    """Check tenant-level setting for warrant enforcement.

    ``connection.tenant`` may be either:
      * The full ``tenants.Client`` model instance (set by the
        request-dispatch middleware during an HTTP request), or
      * A ``FakeTenant`` placeholder (set by ``schema_context()`` when
        code runs outside a request — management commands, signals
        fired from shell, Celery tasks, etc.) which carries only
        ``schema_name`` and none of the Client model's boolean fields.

    To work in both contexts we fall back to a live Client lookup by
    schema when the attribute is missing. Without this fallback, any
    post performed outside an HTTP request (payroll batch, management
    command, Celery job) would silently skip the warrant gate — which
    is exactly the kind of back-door the centralised enforcement work
    was meant to close.
    """
    try:
        tenant = getattr(connection, 'tenant', None)
        if tenant is None:
            return False
        val = getattr(tenant, 'enforce_warrant', None)
        if val is not None:
            return bool(val)
        schema = getattr(tenant, 'schema_name', None)
        if not schema:
            return False
        from tenants.models import Client
        client = Client.objects.filter(schema_name=schema).only('enforce_warrant').first()
        if client is None:
            return False
        return bool(getattr(client, 'enforce_warrant', False))
    except Exception:
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
        from accounting.services.budget_check_rules import (
            check_policy, resolve_rule_for_account,
        )

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

        # 0b. BudgetCheckRule resolution — single source of truth for
        # per-GL-range policy. NONE → skip the gate. WARNING → allow with
        # advisory note when no appropriation. STRICT → keep hard stop.
        econ_code = economic_seg.code if economic_seg else ''
        rule = resolve_rule_for_account(econ_code)
        rule_level = rule.check_level if rule else None

        # 1. Find active appropriation — case-insensitive status so
        # seed scripts that wrote 'Active' or 'active' still match.
        qs = Appropriation.objects.filter(
            administrative_id=administrative_id,
            economic_id=economic_id,
            fund_id=fund_id,
            fiscal_year_id=fiscal_year_id,
            status__iexact='ACTIVE',
        )
        appropriation = qs.first()

        if appropriation is None:
            # Ask the policy what to do when no appropriation exists.
            econ_name = getattr(economic_seg, 'name', '') if economic_seg else ''
            policy = check_policy(
                account_code=econ_code,
                appropriation=None,
                requested_amount=amount,
                transaction_label=source.lower() if source else 'transaction',
                account_name=econ_name,
            )
            if policy.level == 'NONE':
                return {
                    'approved':          True,
                    'appropriation_id':  None,
                    'warrant_id':        None,
                    'available_balance': None,
                    'execution_pct':     None,
                    'note':              f'GL {econ_code}: budget check disabled by rule.',
                }
            if policy.level == 'WARNING':
                return {
                    'approved':          True,
                    'appropriation_id':  None,
                    'warrant_id':        None,
                    'available_balance': None,
                    'execution_pct':     None,
                    'warnings':          policy.warnings,
                    'note':              (
                        f'GL {econ_code}: posting unbudgeted — no active appropriation. '
                        f'Admin has set this GL to WARNING-only.'
                    ),
                }
            # STRICT — hard stop with the policy's own reason
            raise BudgetExceededError(policy.reason or (
                f"No active appropriation found for MDA "
                f"(Admin ID: {administrative_id}, Economic ID: {economic_id}, "
                f"Fund ID: {fund_id}, Fiscal Year: {fiscal_year_id}). "
                f"Payment cannot proceed without legislative appropriation. "
                f"Contact the Budget Office."
            ))

        # If a rule marked this GL as NONE, skip balance gate entirely
        if rule_level == 'NONE':
            return {
                'approved':          True,
                'appropriation_id':  appropriation.pk,
                'warrant_id':        None,
                'available_balance': appropriation.available_balance,
                'execution_pct':     appropriation.execution_rate,
                'note':              f'GL {econ_code}: budget check disabled by rule.',
            }

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

        # 3. Check available balance — STRICT hard-stops, WARNING soft-flags
        available = appropriation.available_balance
        warnings_out: list = []
        if amount > available:
            deficit = amount - available
            over_msg = (
                f"Insufficient appropriation balance for "
                f"{appropriation.administrative.name} — {appropriation.economic.name}.\n"
                f"  Requested:  NGN {amount:>15,.2f}\n"
                f"  Available:  NGN {available:>15,.2f}\n"
                f"  Deficit:    NGN {deficit:>15,.2f}\n"
                f"A Supplementary Appropriation or Virement is required."
            )
            if rule_level == 'WARNING':
                warnings_out.append(over_msg)
            else:
                # STRICT (explicit rule) or legacy default — hard stop
                raise BudgetExceededError(over_msg)
        else:
            # Check warning threshold for WARNING-level GLs
            if rule_level == 'WARNING' and rule and rule.warning_threshold_pct:
                approved = Decimal(str(appropriation.amount_approved or 0))
                if approved > 0:
                    consumed = approved - available
                    util_pct = (consumed / approved) * Decimal('100')
                    if util_pct >= Decimal(str(rule.warning_threshold_pct)):
                        warnings_out.append(
                            f'GL {econ_code}: utilisation {util_pct:.1f}% is at/above '
                            f'{rule.warning_threshold_pct}% threshold.'
                        )

        result = {
            'approved':          True,
            'appropriation_id':  appropriation.pk,
            'warrant_id':        warrant_id,
            'available_balance': available,
            'execution_pct':     appropriation.execution_rate,
        }
        if warnings_out:
            result['warnings'] = warnings_out
        return result
