"""
HR-H1: Tax Calculation Service.

DEPRECATED — superseded by :class:`hrm.services.payroll_computation.PAYECalculationService`,
which uses the live ``NigeriaTaxBracket`` table with Finance Act 2020 fallback.
This module remains only because some legacy code paths may import
``TaxCalculationService`` via string lookup; importing it now emits a
``DeprecationWarning`` and instance methods raise ``NotImplementedError``.

Use ``PAYECalculationService`` for all new code.
"""
import logging
import warnings
from decimal import Decimal
from django.utils import timezone

logger = logging.getLogger(__name__)

warnings.warn(
    "hrm.services.tax_calculation is deprecated; use "
    "hrm.services.payroll_computation.PAYECalculationService instead.",
    DeprecationWarning,
    stacklevel=2,
)


class TaxCalculationService:
    """DEPRECATED — use ``PAYECalculationService``.

    Every method raises :class:`NotImplementedError` so any silent caller
    fails loudly instead of computing payroll with stale logic.
    """

    _DEPRECATED_MSG = (
        "TaxCalculationService is deprecated. "
        "Use hrm.services.payroll_computation.PAYECalculationService instead."
    )

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(self._DEPRECATED_MSG)

    @staticmethod
    def get_active_brackets(tax_year=None):
        """DEPRECATED — use PAYECalculationService."""
        raise NotImplementedError(TaxCalculationService._DEPRECATED_MSG)
        # Legacy body retained for reference only — never executed.
        from hrm.models import TaxBracket  # noqa: F401

        today = timezone.now().date()
        query = TaxBracket.objects.filter(
            is_active=True,
            effective_date__lte=today
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=today)
        ).order_by('min_income')
        
        return query

    @classmethod
    def calculate_annual_tax(cls, annual_gross, tax_year=None, employee=None):
        """DEPRECATED — use PAYECalculationService.compute_monthly_paye."""
        raise NotImplementedError(cls._DEPRECATED_MSG)
        from django.db import models  # noqa: F401
        
        brackets = cls.get_active_brackets(tax_year)
        if not brackets.exists():
            return {
                'taxable_income': annual_gross,
                'total_tax': Decimal('0.00'),
                'effective_rate': Decimal('0.00'),
                'brackets_used': [],
                'error': 'No tax brackets configured'
            }
        
        total_tax = Decimal('0.00')
        taxable_income = annual_gross
        brackets_used = []
        remaining_income = annual_gross
        
        for bracket in brackets:
            if remaining_income <= 0:
                break
                
            bracket_min = bracket.min_income or Decimal('0')
            bracket_max = bracket.max_income or Decimal('999999999999')
            bracket_rate = bracket.rate / Decimal('100')
            bracket_fixed = bracket.fixed_amount or Decimal('0')
            
            if annual_gross < bracket_min:
                continue
            
            if bracket_max:
                taxable_in_bracket = min(remaining_income, bracket_max - bracket_min)
            else:
                taxable_in_bracket = remaining_income
            
            if taxable_in_bracket > 0:
                tax_in_bracket = (taxable_in_bracket * bracket_rate) + bracket_fixed
                total_tax += tax_in_bracket
                brackets_used.append({
                    'bracket': str(bracket),
                    'rate': bracket.rate,
                    'income_taxed': taxable_in_bracket,
                    'tax': tax_in_bracket
                })
                remaining_income -= taxable_in_bracket
        
        effective_rate = (total_tax / annual_gross * Decimal('100')).quantize(Decimal('0.01')) if annual_gross > 0 else Decimal('0')
        
        return {
            'taxable_income': annual_gross,
            'total_tax': total_tax.quantize(Decimal('0.01')),
            'effective_rate': effective_rate,
            'brackets_used': brackets_used
        }

    @classmethod
    def calculate_monthly_tax(cls, monthly_gross, tax_year=None, employee=None):
        """DEPRECATED — use PAYECalculationService.compute_monthly_paye."""
        raise NotImplementedError(cls._DEPRECATED_MSG)
        annual_gross = monthly_gross * Decimal('12')
        annual_result = cls.calculate_annual_tax(annual_gross, tax_year, employee)
        
        monthly_tax = (annual_result['total_tax'] / Decimal('12')).quantize(Decimal('0.01'))
        
        return {
            'monthly_gross': monthly_gross,
            'annual_gross': annual_gross,
            'monthly_tax': monthly_tax,
            'annual_tax': annual_result['total_tax'],
            'effective_rate': annual_result['effective_rate'],
            'brackets_used': annual_result.get('brackets_used', [])
        }

    @staticmethod
    def calculate_pension(employee, gross_salary):
        """DEPRECATED — use PensionCalculationService.compute_contributions."""
        raise NotImplementedError(TaxCalculationService._DEPRECATED_MSG)
        from django.utils import timezone  # noqa: F401
        
        today = timezone.now().date()
        config = None
        
        try:
            from hrm.models import TaxConfiguration
            config = TaxConfiguration.objects.filter(
                is_active=True,
                tax_year=today.year
            ).first()
        except Exception as exc:
            logger.warning(
                "tax_calculation: could not load TaxConfiguration for pension "
                "(year=%s); using default rates: %s", today.year, exc,
            )

        if not config:
            pension_rate = Decimal('0.05')  # Default 5%
            pension_cap = Decimal('10000')  # Default cap
        else:
            pension_rate = config.pension_rate
            pension_cap = config.pension_cap
        
        pension_amount = min(gross_salary * pension_rate, pension_cap).quantize(Decimal('0.01'))
        employer_contribution = pension_amount  # Usually matched
        
        return {
            'employee_pension': pension_amount,
            'employer_pension': employer_contribution,
            'total_pension': pension_amount * 2,
            'rate_used': pension_rate
        }

    @staticmethod
    def calculate_social_security(employee, gross_salary):
        """DEPRECATED — use PensionCalculationService."""
        raise NotImplementedError(TaxCalculationService._DEPRECATED_MSG)
        from django.utils import timezone  # noqa: F401
        
        today = timezone.now().date()
        config = None
        
        try:
            from hrm.models import TaxConfiguration
            config = TaxConfiguration.objects.filter(
                is_active=True,
                tax_year=today.year
            ).first()
        except Exception as exc:
            logger.warning(
                "tax_calculation: could not load TaxConfiguration for social security "
                "(year=%s); using default rates: %s", today.year, exc,
            )

        if not config:
            ss_rate = Decimal('0.05')  # Default 5%
            ss_cap = Decimal('50000')  # Default cap
        else:
            ss_rate = config.social_security_rate
            ss_cap = config.social_security_cap
        
        ss_amount = min(gross_salary * ss_rate, ss_cap).quantize(Decimal('0.01'))
        
        return {
            'employee_ss': ss_amount,
            'employer_ss': ss_amount,
            'total_ss': ss_amount * 2,
            'rate_used': ss_rate
        }

    @classmethod
    def calculate_full_payroll_tax(cls, employee, gross_salary, tax_year=None):
        """DEPRECATED — use the deterministic payroll pipeline in payroll_runner."""
        raise NotImplementedError(cls._DEPRECATED_MSG)
        tax_result = cls.calculate_monthly_tax(gross_salary, tax_year, employee)
        pension_result = cls.calculate_pension(employee, gross_salary)
        ss_result = cls.calculate_social_security(employee, gross_salary)
        
        total_deductions = (
            tax_result['monthly_tax'] +
            pension_result['employee_pension'] +
            ss_result['employee_ss']
        )
        
        net_salary = gross_salary - total_deductions
        
        return {
            'gross_salary': gross_salary,
            'tax': tax_result,
            'pension': pension_result,
            'social_security': ss_result,
            'total_deductions': total_deductions.quantize(Decimal('0.01')),
            'net_salary': net_salary.quantize(Decimal('0.01'))
        }
