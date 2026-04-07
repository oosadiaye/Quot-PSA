"""Tax Calculation Service

Provides automatic tax and withholding tax calculation for:
- Vendor invoices (AP)
- Customer invoices (AR)
- Automatic tax code application
"""
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from django.db.models import Sum


@dataclass
class TaxCalculationResult:
    """Result of a tax calculation."""
    subtotal: Decimal
    tax_amount: Decimal
    withholding_tax_amount: Decimal
    total_amount: Decimal
    tax_lines: List[Dict[str, Any]]
    withholding_lines: List[Dict[str, Any]]


class TaxCalculationService:
    """Service for calculating taxes and withholding on invoices."""

    @classmethod
    def calculate_line_tax(
        cls,
        amount: Decimal,
        tax_rate: Decimal,
        tax_direction: str = 'purchase'
    ) -> Decimal:
        """
        Calculate tax amount for a single line.
        
        Args:
            amount: The line amount
            tax_rate: Tax rate as decimal (e.g., 0.10 for 10%)
            tax_direction: 'purchase' or 'sales'
            
        Returns:
            Calculated tax amount
        """
        if amount <= 0 or tax_rate <= 0:
            return Decimal('0')
        return (amount * tax_rate).quantize(Decimal('0.01'))

    @classmethod
    def calculate_withholding_tax(
        cls,
        amount: Decimal,
        wht_rate: Decimal
    ) -> Decimal:
        """
        Calculate withholding tax amount.
        
        Args:
            amount: The gross amount
            wht_rate: WHT rate as decimal (e.g., 0.05 for 5%)
            
        Returns:
            Calculated withholding tax amount
        """
        if amount <= 0 or wht_rate <= 0:
            return Decimal('0')
        return (amount * wht_rate).quantize(Decimal('0.01'))

    @classmethod
    def calculate_invoice_tax(
        cls,
        lines: List[Dict[str, Any]],
        include_wht: bool = True,
        vendor_wht_category: Optional[Any] = None
    ) -> TaxCalculationResult:
        """
        Calculate all taxes for an invoice.
        
        Args:
            lines: List of invoice line dictionaries with:
                   - amount: Line amount
                   - tax_code: TaxCode instance or None
                   - withholding_tax: WithholdingTax instance or None
            include_wht: Whether to include withholding tax calculation
            vendor_wht_category: Vendor's default WHT category
            
        Returns:
            TaxCalculationResult with all calculated amounts
        """
        subtotal = Decimal('0')
        tax_amount = Decimal('0')
        withholding_tax_amount = Decimal('0')
        tax_lines = []
        withholding_lines = []
        
        for line in lines:
            amount = Decimal(str(line.get('amount', 0)))
            subtotal += amount
            
            tax_code = line.get('tax_code')
            if tax_code and hasattr(tax_code, 'rate'):
                rate = Decimal(str(tax_code.rate))
                calculated_tax = cls.calculate_line_tax(amount, rate)
                tax_amount += calculated_tax
                tax_lines.append({
                    'tax_code': str(tax_code.code),
                    'rate': rate,
                    'amount': amount,
                    'tax': calculated_tax,
                })
            
            withholding = line.get('withholding_tax')
            if withholding and include_wht and hasattr(withholding, 'rate'):
                rate = Decimal(str(withholding.rate))
                calculated_wht = cls.calculate_withholding_tax(amount, rate)
                withholding_tax_amount += calculated_wht
                withholding_lines.append({
                    'wht_code': str(withholding.code),
                    'rate': rate,
                    'amount': amount,
                    'wht': calculated_wht,
                })
        
        if include_wht and vendor_wht_category and hasattr(vendor_wht_category, 'rate'):
            vendor_wht_rate = Decimal(str(vendor_wht_category.rate))
            vendor_wht = cls.calculate_withholding_tax(subtotal, vendor_wht_rate)
            withholding_tax_amount += vendor_wht
            withholding_lines.append({
                'wht_code': str(vendor_wht_category.code),
                'rate': vendor_wht_rate,
                'amount': subtotal,
                'wht': vendor_wht,
                'is_vendor_default': True,
            })
        
        total_amount = subtotal + tax_amount - withholding_tax_amount
        
        return TaxCalculationResult(
            subtotal=subtotal,
            tax_amount=tax_amount,
            withholding_tax_amount=withholding_tax_amount,
            total_amount=total_amount,
            tax_lines=tax_lines,
            withholding_lines=withholding_lines,
        )

    @classmethod
    def calculate_tax_on_amount(
        cls,
        gross_amount: Decimal,
        tax_rate: Decimal,
        is_inclusive: bool = False
    ) -> Tuple[Decimal, Decimal]:
        """
        Calculate tax and net amount.
        
        Args:
            gross_amount: The gross or net amount
            tax_rate: Tax rate as decimal
            is_inclusive: True if gross_amount includes tax
            
        Returns:
            Tuple of (tax_amount, net_amount)
        """
        if gross_amount <= 0 or tax_rate <= 0:
            return Decimal('0'), gross_amount
        
        if is_inclusive:
            net_amount = gross_amount / (1 + tax_rate)
            tax_amount = gross_amount - net_amount
        else:
            net_amount = gross_amount
            tax_amount = gross_amount * tax_rate
        
        return tax_amount.quantize(Decimal('0.01')), net_amount.quantize(Decimal('0.01'))

    @classmethod
    def get_invoice_taxes_summary(
        cls,
        invoice_lines: List[Any],
        vendor: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Get a summary of all taxes on an invoice.
        
        Args:
            invoice_lines: Django model instances of invoice lines
            vendor: Vendor instance for WHT lookup
            
        Returns:
            Dictionary with tax summary
        """
        lines_data = []
        vendor_wht = None
        
        for line in invoice_lines:
            line_dict = {
                'amount': Decimal(str(line.amount)),
                'tax_code': getattr(line, 'tax_code', None),
                'withholding_tax': getattr(line, 'withholding_tax', None),
            }
            lines_data.append(line_dict)
        
        if vendor:
            vendor_wht = getattr(vendor, 'wht_category', None)
        
        result = cls.calculate_invoice_tax(lines_data, include_wht=True, vendor_wht_category=vendor_wht)
        
        return {
            'subtotal': result.subtotal,
            'tax_amount': result.tax_amount,
            'withholding_tax_amount': result.withholding_tax_amount,
            'total_amount': result.total_amount,
            'tax_breakdown': result.tax_lines,
            'wht_breakdown': result.withholding_lines,
        }

    @classmethod
    def validate_tax_configuration(cls, tax_code: Any, direction: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that a tax code can be used for a given direction.
        
        Args:
            tax_code: TaxCode instance
            direction: 'purchase' or 'sales'
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not tax_code:
            return True, None
        
        code_direction = getattr(tax_code, 'direction', '')
        
        if code_direction == 'both':
            return True, None
        
        if code_direction != direction:
            return False, (
                f"Tax code '{tax_code.code}' cannot be used for {direction}. "
                f"It is configured for {code_direction}."
            )
        
        return True, None


class TaxCalculationMixin:
    """Mixin to add tax calculation capabilities to invoice serializers."""

    def calculate_taxes(self, lines_data: List[Dict], vendor: Any = None) -> TaxCalculationResult:
        """
        Calculate taxes for invoice lines.
        
        Args:
            lines_data: List of invoice line dictionaries
            vendor: Vendor instance (optional)
            
        Returns:
            TaxCalculationResult
        """
        return TaxCalculationService.calculate_invoice_tax(lines_data, vendor_wht_category=vendor)
