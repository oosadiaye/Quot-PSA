"""
HRM Payroll Services — Quot PSE
PAYE computation per Nigeria Finance Act + Pension CPS calculation.
"""
from decimal import Decimal, ROUND_HALF_UP


class PAYECalculationService:
    """
    Computes Nigeria PAYE (Pay As You Earn) tax per the Personal Income Tax Act.
    Uses the graduated tax table from NigeriaTaxBracket model.

    Computation flow:
    1. Gross annual income
    2. Deduct exempt items (pension, NHF, NHIS, life assurance)
    3. Apply Consolidated Relief Allowance (CRA):
       CRA = Higher of (NGN 200,000 or 1% of Gross) PLUS 20% of Gross
    4. Taxable income = Gross - exempt deductions - CRA
    5. Apply graduated tax brackets
    6. Minimum tax rule: if PAYE < 1% of gross, charge 1%
    """

    @classmethod
    def compute_annual_paye(
        cls,
        gross_annual: Decimal,
        pension_employee: Decimal = Decimal('0'),
        nhf: Decimal = Decimal('0'),
        nhis: Decimal = Decimal('0'),
        life_assurance: Decimal = Decimal('0'),
    ) -> dict:
        """
        Compute annual PAYE tax.

        Args:
            gross_annual: Total annual gross income
            pension_employee: Employee pension contribution (8% of qualifying)
            nhf: National Housing Fund (2.5% of basic)
            nhis: National Health Insurance
            life_assurance: Life assurance premiums

        Returns:
            dict with taxable_income, paye, effective_rate, cra, min_tax_applied
        """
        if gross_annual <= 0:
            return {
                'gross_annual': Decimal('0'),
                'cra': Decimal('0'),
                'exempt_deductions': Decimal('0'),
                'taxable_income': Decimal('0'),
                'paye': Decimal('0'),
                'effective_rate': Decimal('0'),
                'min_tax_applied': False,
            }

        # 1. Consolidated Relief Allowance (CRA)
        one_percent = gross_annual * Decimal('0.01')
        fixed_amount = Decimal('200000')
        higher_of = max(one_percent, fixed_amount)
        twenty_percent = gross_annual * Decimal('0.20')
        cra = higher_of + twenty_percent

        # 2. Exempt deductions
        exempt_deductions = pension_employee + nhf + nhis + life_assurance

        # 3. Taxable income
        taxable_income = max(Decimal('0'), gross_annual - cra - exempt_deductions)

        # 4. Apply graduated brackets
        paye = cls._apply_brackets(taxable_income)

        # 5. Minimum tax rule: 1% of gross if PAYE is less
        min_tax = gross_annual * Decimal('0.01')
        min_tax_applied = False
        if paye < min_tax:
            paye = min_tax
            min_tax_applied = True

        # Round to 2 decimal places
        paye = paye.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        effective_rate = Decimal('0')
        if gross_annual > 0:
            effective_rate = (paye / gross_annual * 100).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP,
            )

        return {
            'gross_annual': gross_annual,
            'cra': cra.quantize(Decimal('0.01')),
            'exempt_deductions': exempt_deductions.quantize(Decimal('0.01')),
            'taxable_income': taxable_income.quantize(Decimal('0.01')),
            'paye': paye,
            'effective_rate': effective_rate,
            'min_tax_applied': min_tax_applied,
        }

    @classmethod
    def compute_monthly_paye(cls, gross_monthly: Decimal, **kwargs) -> dict:
        """Convenience: compute monthly PAYE from monthly gross."""
        # Annualize, compute, then divide by 12
        annual_kwargs = {k: v * 12 for k, v in kwargs.items()}
        result = cls.compute_annual_paye(
            gross_annual=gross_monthly * 12, **annual_kwargs,
        )
        result['monthly_paye'] = (result['paye'] / 12).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP,
        )
        return result

    @classmethod
    def _apply_brackets(cls, taxable_income: Decimal) -> Decimal:
        """Apply graduated tax brackets from NigeriaTaxBracket model."""
        from hrm.models import NigeriaTaxBracket

        brackets = NigeriaTaxBracket.objects.filter(is_current=True).order_by('lower_bound')
        if not brackets.exists():
            # Fallback to hardcoded Finance Act 2020 brackets
            brackets_data = [
                (Decimal('0'),       Decimal('300000'),    Decimal('7')),
                (Decimal('300001'),  Decimal('600000'),    Decimal('11')),
                (Decimal('600001'),  Decimal('1100000'),   Decimal('15')),
                (Decimal('1100001'), Decimal('1600000'),   Decimal('19')),
                (Decimal('1600001'), Decimal('3200000'),   Decimal('21')),
                (Decimal('3200001'), None,                 Decimal('24')),
            ]
        else:
            brackets_data = [
                (b.lower_bound, b.upper_bound, b.rate) for b in brackets
            ]

        total_tax = Decimal('0')
        remaining = taxable_income

        for lower, upper, rate in brackets_data:
            if remaining <= 0:
                break
            if upper is not None:
                bracket_size = upper - lower
                taxable_in_bracket = min(remaining, bracket_size)
            else:
                taxable_in_bracket = remaining

            tax = taxable_in_bracket * rate / 100
            total_tax += tax
            remaining -= taxable_in_bracket

        return total_tax


class PensionCalculationService:
    """
    Computes Contributory Pension Scheme (CPS) contributions.
    Per Pension Reform Act 2014:
    - Employer: minimum 10% of (basic + housing + transport)
    - Employee: minimum 8% of (basic + housing + transport)
    """

    @classmethod
    def compute_contributions(
        cls,
        basic_salary: Decimal,
        housing_allowance: Decimal = Decimal('0'),
        transport_allowance: Decimal = Decimal('0'),
    ) -> dict:
        """
        Compute monthly pension contributions.
        Returns: employer_amount, employee_amount, total, qualifying_emolument
        """
        from hrm.models import PensionConfiguration

        config = PensionConfiguration.objects.filter(is_current=True).first()
        employer_rate = config.employer_rate if config else Decimal('10.00')
        employee_rate = config.employee_rate if config else Decimal('8.00')

        qualifying = basic_salary + housing_allowance + transport_allowance
        employer = (qualifying * employer_rate / 100).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP,
        )
        employee = (qualifying * employee_rate / 100).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP,
        )

        return {
            'qualifying_emolument': qualifying,
            'employer_rate': employer_rate,
            'employee_rate': employee_rate,
            'employer_amount': employer,
            'employee_amount': employee,
            'total_contribution': employer + employee,
        }

    @classmethod
    def compute_nhf(cls, basic_salary: Decimal) -> Decimal:
        """National Housing Fund: 2.5% of basic salary."""
        return (basic_salary * Decimal('2.5') / 100).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP,
        )
