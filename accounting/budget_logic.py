import logging
from decimal import Decimal
from .models import Budget, BudgetCheckLog, BudgetPeriod

logger = logging.getLogger(__name__)


def is_dimensions_enabled_for_budget(tenant):
    """Check if dimensions module is enabled for the tenant.

    We default to True when the module-resolver itself is broken (ImportError
    or the function missing), because denying dimensions when we can't tell
    is the safer fallback for multi-dimensional public-sector accounting.
    But any OTHER exception is a real bug that should be logged instead of
    silently swallowed (the old ``except Exception: pass`` style masked
    database errors, permission bugs, etc.).
    """
    try:
        from tenants.models import is_dimensions_enabled
    except ImportError:
        logger.info('tenants.models.is_dimensions_enabled unavailable — defaulting to True')
        return True
    try:
        return is_dimensions_enabled(tenant)
    except (AttributeError, TypeError) as e:
        # tenant missing attributes or wrong type — defensible default
        logger.warning('is_dimensions_enabled fell back to default: %s', e)
        return True


def get_active_budget(dimensions, account, date, tenant=None):
    """
    Find the active budget for a given set of dimensions, account, and date.
    dimensions: dict with 'fund', 'function', 'program', 'geo', 'mda'

    Budget check uses only the 3 control dimensions:
      MDA (Administrative) + Economic Code (account) + Fund

    Function, Programme, and Geo are mandatory on transactions for
    government performance reporting but do NOT gate budget approval.
    """
    if tenant and not is_dimensions_enabled_for_budget(tenant):
        return None

    if not dimensions or not any(dimensions.values()):
        return None

    # Find active budget period for the date — case-insensitive on
    # status so seed scripts that wrote 'Active' or 'active' still match.
    period = BudgetPeriod.objects.filter(
        start_date__lte=date,
        end_date__gte=date,
        status__iexact='ACTIVE'
    ).first()

    if not period:
        period = BudgetPeriod.objects.filter(
            start_date__lte=date,
            end_date__gte=date
        ).first()

    if not period:
        return None

    # Budget control = MDA + Account (Economic Code) + Fund only
    mda = dimensions.get('mda')
    fund = dimensions.get('fund')

    filters = {
        'period': period,
        'account': account,
    }
    if mda:
        filters['mda'] = mda
    if fund:
        filters['fund'] = fund

    return Budget.objects.filter(**filters).first()

def check_budget_availability(dimensions, account, amount, date, transaction_type, transaction_id, user=None, tenant=None):
    """
    Check if a transaction amount is available in the budget.
    Uses select_for_update to prevent race conditions.

    As of the BudgetCheckRule rollout this function is a thin wrapper
    over ``accounting.services.budget_check_rules.check_policy`` — every
    caller (treasury, asset acquisition, vendor invoice post) gets the
    same per-GL-range policy applied through this one doorway. The
    legacy Budget table lookup still runs as a secondary check for
    accounts that don't fall under any BudgetCheckRule.

    Returns: (is_allowed: bool, message: str)
    """
    from django.db import transaction

    # If dimensions are disabled or dimensions are not provided, skip budget check
    if tenant and not is_dimensions_enabled_for_budget(tenant):
        return True, "Dimensions module disabled. Budget check skipped."

    if not dimensions or not any(dimensions.values()):
        return True, "No dimensions provided. Budget check skipped."

    # ── Rule-driven policy — single source of truth ───────────────
    from accounting.services.budget_check_rules import (
        check_policy, find_matching_appropriation,
    )
    appropriation = find_matching_appropriation(
        mda=dimensions.get('mda'),
        fund=dimensions.get('fund'),
        account=account,
    )
    policy = check_policy(
        account_code=account.code if account else '',
        appropriation=appropriation,
        requested_amount=amount,
        transaction_label=transaction_type or 'transaction',
        account_name=account.name if account else '',
    )
    if policy.blocked:
        return False, policy.reason
    if policy.level == 'NONE':
        return True, "Budget check level NONE for this GL — no gate applied."

    with transaction.atomic():
        # Budget control = MDA + Account (Economic Code) + Fund only
        # Function, Programme, Geo are for reporting, not budget gating
        filters = {
            'period__start_date__lte': date,
            'period__end_date__gte': date,
            'account': account,
        }
        if dimensions.get('mda'):
            filters['mda'] = dimensions['mda']
        if dimensions.get('fund'):
            filters['fund'] = dimensions['fund']

        budget = Budget.objects.select_for_update().filter(**filters).first()

        if not budget:
            # If rule-driven policy said WARNING, allow with the policy's
            # own message. Only land in the legacy HARD_STOP default
            # (settings.BUDGET_DEFAULT_CONTROL_LEVEL) when the account
            # has no rule at all and the env default is set to STRICT.
            if policy.level == 'WARNING':
                warn = '; '.join(policy.warnings) or 'Warning: no budget row defined.'
                return True, warn
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


def is_warrant_pre_payment_enforced() -> bool:
    """Whether to enforce the warrant ceiling BEFORE the payment stage.

    Public-sector accounting offers two valid stages at which the
    warrant ceiling can bind:

    - ``commitment`` / ``invoice`` (legacy strict): warrant is
      consumed as soon as a commitment or obligation is recorded
      (PO, vendor invoice, contract, journal). This is what GIFMIS
      central practice does and what IPSAS 24 commitment-stage
      reporting assumes. Pre-payment posting is blocked when no
      warrant is released.
    - ``payment`` (cash-control stage): commitments and obligations
      can be recorded freely; the ceiling binds only at payment time
      so cash never leaves the consolidated account beyond released
      warrants. Useful for sub-national MDAs that release warrants
      monthly against an annualised commitment ledger.

    Controlled by Django setting ``WARRANT_ENFORCEMENT_STAGE``:

    - ``'payment'`` (DEFAULT in this build) → returns ``False``;
      pre-payment paths skip the warrant check.
    - ``'invoice'`` / ``'commitment'`` / anything else → returns
      ``True``; legacy strict behaviour.

    Payment-stage enforcement is unconditional and not gated by
    this helper — see the payment posting view.
    """
    from django.conf import settings
    stage = getattr(settings, 'WARRANT_ENFORCEMENT_STAGE', 'payment')
    return str(stage).lower() != 'payment'


def check_warrant_availability(*, dimensions, account, amount, exclude_po=None):
    """Verify a transaction amount fits within the released-warrant ceiling
    for the matching Appropriation.

    Public-sector accounting requires TWO independent budget controls:
      1. **Appropriation** — the legislatively approved annual budget.
      2. **Warrant / AIE (Authority to Incur Expenditure)** — the
         quarterly cash release that *actually* makes that appropriation
         spendable. An MDA may have ₦2M appropriated but only ₦500K
         warranted for Q2 — they cannot commit beyond the ₦500K.

    ``check_budget_availability()`` (above) only validates against
    appropriation/UnifiedBudget allocations. This helper adds the second
    control layer.

    Args:
        dimensions: dict with 'mda', 'fund' keys
        account: legacy ``accounting.Account`` instance (Economic Code)
        amount: ``Decimal`` — the transaction amount being checked
        exclude_po: ``PurchaseOrder`` to EXCLUDE from existing-commitments
            sum, used when re-checking an already-approved PO during
            invoice posting (we don't want to double-count its own
            commitment that was already booked at PO approval).

    Returns:
        (allowed: bool, message: str, balance_info: dict)

        balance_info has: warrants_released, already_consumed,
        available_warrant — useful for surfacing exact numbers in the
        error toast.
    """
    from budget.models import Appropriation
    from accounting.models.ncoa import (
        AdministrativeSegment, EconomicSegment, FundSegment,
    )

    mda  = dimensions.get('mda')  if dimensions else None
    fund = dimensions.get('fund') if dimensions else None
    if not (mda and fund and account):
        return True, "Warrant check skipped (incomplete dimensions).", {}

    # Resolve legacy → NCoA segments via the legacy_* OneToOne bridges.
    admin_seg = AdministrativeSegment.objects.filter(legacy_mda=mda).first()
    econ_seg  = EconomicSegment.objects.filter(legacy_account=account).first()
    fund_seg  = FundSegment.objects.filter(legacy_fund=fund).first()
    if not (admin_seg and econ_seg and fund_seg):
        return True, "Warrant check skipped (no NCoA bridge yet).", {}

    # Walk the economic parent chain so a leaf-coded transaction (e.g.
    # 23100100 Acquisition of Land) can validate against an
    # appropriation set at a parent level (e.g. 23000000 Capital
    # Expenditure). Mirrors create_commitment_for_po() lookup.
    candidates = [econ_seg]
    cursor = econ_seg.parent
    while cursor is not None:
        candidates.append(cursor)
        cursor = cursor.parent

    appro = Appropriation.objects.filter(
        administrative=admin_seg,
        economic__in=candidates,
        fund=fund_seg,
        status__iexact='ACTIVE',
    ).first()
    if not appro:
        # No matching appropriation — let check_budget_availability handle the
        # "no budget" message. Warrant check has nothing to validate against.
        return True, "Warrant check skipped (no matching appropriation).", {}

    warrants_released = appro.total_warrants_released or Decimal('0')

    # Actual single-count consumption against the appropriation.
    #
    # ``total_committed`` and ``total_expended`` are DISPLAY columns —
    # they both include the same direct disbursements (direct AP, direct
    # PV, direct JV) by design so the Appropriation report can show the
    # full commitment + expenditure posture in parallel. A naive
    # ``committed + expended`` would double-count every NGN of direct
    # disbursement, which is exactly the bug that produced the
    # "32M already committed/expended" number when the real figure was
    # 16M.
    #
    # The correct identity (matches ``Appropriation.available_balance``):
    #   consumed = approved - available_balance
    #            = open_po + closed_po + direct
    # which equals ``total_committed + total_expended - direct``.
    #
    # We compute it via ``amount_approved - available_balance`` so we
    # reuse the single source of truth the model already exposes.
    approved = appro.amount_approved or Decimal('0')
    already_consumed = approved - (appro.available_balance or Decimal('0'))
    if already_consumed < 0:
        already_consumed = Decimal('0')

    # Optional: exclude one PO's commitment so invoice-verify time
    # doesn't double-count the PO that's about to close out.
    if exclude_po is not None:
        existing_link = appro.commitments.filter(purchase_order=exclude_po).first()
        if existing_link:
            already_consumed -= (existing_link.committed_amount or Decimal('0'))
            already_consumed = max(already_consumed, Decimal('0'))

    available_warrant = warrants_released - already_consumed

    info = {
        'appropriation_id': appro.pk,
        'appropriation_label': (
            f"{appro.administrative.code}/{appro.economic.code}/{appro.fund.code}"
        ),
        'warrants_released': warrants_released,
        'already_consumed': already_consumed,
        'available_warrant': available_warrant,
        'requested': amount,
    }

    if amount > available_warrant:
        msg = (
            f"Warrant ceiling exceeded for {info['appropriation_label']}: "
            f"requested ₦{amount:,.2f} but only ₦{max(available_warrant, Decimal('0')):,.2f} "
            f"is currently available against ₦{warrants_released:,.2f} of warrants released "
            f"(₦{already_consumed:,.2f} already committed/expended). "
            f"Issue an additional warrant before proceeding."
        )
        return False, msg, info

    return True, "OK — within warrant ceiling.", info
