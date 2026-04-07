"""VAT Returns Service

Generates VAT returns per FIRS requirements.
"""
from datetime import date
from decimal import Decimal
from typing import Optional, Dict, Any, List
from django.db.models import Sum, Q
from django.contrib.auth.models import User
from accounting.models import (
    VATReturn, VATReturnDetail, TaxRate, TaxCode,
    CustomerInvoice, VendorInvoice, JournalLine
)


class VATReturnService:
    """Service for VAT return processing per FIRS requirements."""
    
    STANDARD_VAT_RATE = Decimal('7.5')
    
    @classmethod
    def get_output_vat(
        cls,
        period_start: date,
        period_end: date,
        fiscal_year: int = None,
        period: int = None
    ) -> List[Dict[str, Any]]:
        """Get all output VAT transactions for the period."""
        invoices = CustomerInvoice.objects.filter(
            invoice_date__gte=period_start,
            invoice_date__lte=period_end,
            status__in=['POSTED', 'APPROVED']
        )
        
        if fiscal_year:
            invoices = invoices.filter(fiscal_year=fiscal_year)
        
        vat_transactions = []
        
        for invoice in invoices:
            vat_amount = invoice.tax_amount or Decimal('0')
            if vat_amount > 0:
                vat_transactions.append({
                    'document_type': 'CI',
                    'document_id': invoice.id,
                    'document_number': invoice.invoice_number,
                    'document_date': invoice.invoice_date,
                    'customer_name': getattr(invoice, 'customer_name', str(invoice.customer_id)),
                    'taxable_amount': invoice.subtotal or Decimal('0'),
                    'vat_amount': vat_amount,
                    'vat_rate': cls.STANDARD_VAT_RATE,
                    'is_output': True,
                })
        
        return vat_transactions
    
    @classmethod
    def get_input_vat(
        cls,
        period_start: date,
        period_end: date,
        fiscal_year: int = None,
        period: int = None
    ) -> List[Dict[str, Any]]:
        """Get all input VAT transactions for the period."""
        invoices = VendorInvoice.objects.filter(
            invoice_date__gte=period_start,
            invoice_date__lte=period_end,
            status__in=['POSTED', 'APPROVED']
        )
        
        if fiscal_year:
            invoices = invoices.filter(fiscal_year=fiscal_year)
        
        vat_transactions = []
        
        for invoice in invoices:
            vat_amount = invoice.tax_amount or Decimal('0')
            if vat_amount > 0:
                vat_transactions.append({
                    'document_type': 'VI',
                    'document_id': invoice.id,
                    'document_number': invoice.invoice_number,
                    'document_date': invoice.invoice_date,
                    'vendor_name': getattr(invoice, 'vendor_name', str(invoice.vendor_id)),
                    'taxable_amount': invoice.subtotal or Decimal('0'),
                    'vat_amount': vat_amount,
                    'vat_rate': cls.STANDARD_VAT_RATE,
                    'is_output': False,
                })
        
        return vat_transactions
    
    @classmethod
    def calculate_vat_return(
        cls,
        period_start: date,
        period_end: date,
        fiscal_year: int = None,
        period: int = None
    ) -> Dict[str, Any]:
        """Calculate VAT return for a period."""
        output_vat = cls.get_output_vat(period_start, period_end, fiscal_year, period)
        input_vat = cls.get_input_vat(period_start, period_end, fiscal_year, period)
        
        total_output_vat = sum(v['vat_amount'] for v in output_vat)
        total_input_vat = sum(v['vat_amount'] for v in input_vat)
        
        total_output_sales = sum(v['taxable_amount'] for v in output_vat)
        total_input_purchases = sum(v['taxable_amount'] for v in input_vat)
        
        zero_rated_sales = Decimal('0')
        exempt_sales = Decimal('0')
        
        for v in output_vat:
            if getattr(v, 'is_zero_rated', False):
                zero_rated_sales += v['taxable_amount']
            if getattr(v, 'is_exempt', False):
                exempt_sales += v['taxable_amount']
        
        vat_payable = total_output_vat - total_input_vat
        if vat_payable < 0:
            vat_payable = Decimal('0')
        
        vat_refundable = abs(vat_payable) if total_input_vat > total_output_vat else Decimal('0')
        
        return {
            'period_start': period_start,
            'period_end': period_end,
            'fiscal_year': fiscal_year or period_start.year,
            'period': period,
            'output_vat': total_output_vat,
            'input_vat': total_input_vat,
            'vat_payable': vat_payable,
            'vat_refundable': vat_refundable,
            'total_output_sales': total_output_sales,
            'total_input_purchases': total_input_purchases,
            'zero_rated_sales': zero_rated_sales,
            'exempt_sales': exempt_sales,
            'standard_rated_sales': total_output_sales - zero_rated_sales - exempt_sales,
            'output_transactions': len(output_vat),
            'input_transactions': len(input_vat),
            'output_vat_list': output_vat,
            'input_vat_list': input_vat,
        }
    
    @classmethod
    def create_vat_return(
        cls,
        period_start: date,
        period_end: date,
        fiscal_year: int = None,
        period: int = None,
        user: User = None
    ) -> VATReturn:
        """Create and save a VAT return."""
        calc = cls.calculate_vat_return(period_start, period_end, fiscal_year, period)
        
        vat_return = VATReturn.objects.create(
            period_start=period_start,
            period_end=period_end,
            return_type='MONTHLY',
            total_output_vat=calc['output_vat'],
            total_input_vat=calc['input_vat'],
            total_vat_payable=calc['vat_payable'],
            total_vat_refundable=calc['vat_refundable'],
            zero_rated_sales=calc['zero_rated_sales'],
            exempt_sales=calc['exempt_sales'],
            status='DRAFT',
            created_by=user,
        )
        
        for item in calc['output_vat_list']:
            VATReturnDetail.objects.create(
                vat_return=vat_return,
                document_type='CI',
                document_id=item['document_id'],
                document_number=item['document_number'],
                document_date=item['document_date'],
                taxable_amount=item['taxable_amount'],
                vat_amount=item['vat_amount'],
                vat_rate=item['vat_rate'],
                is_output='OUTPUT',
                counterparty_name=item['customer_name'],
            )
        
        for item in calc['input_vat_list']:
            VATReturnDetail.objects.create(
                vat_return=vat_return,
                document_type='VI',
                document_id=item['document_id'],
                document_number=item['document_number'],
                document_date=item['document_date'],
                taxable_amount=item['taxable_amount'],
                vat_amount=item['vat_amount'],
                vat_rate=item['vat_rate'],
                is_output='INPUT',
                counterparty_name=item['vendor_name'],
            )
        
        return vat_return
    
    @classmethod
    def generate_firs_form_vat1(cls, vat_return_id: int) -> Dict[str, Any]:
        """Generate FIRS Form VAT 1 data for filing."""
        vat_return = VATReturn.objects.get(id=vat_return_id)
        details = VATReturnDetail.objects.filter(vat_return=vat_return)
        
        output_details = details.filter(is_output='OUTPUT')
        input_details = details.filter(is_output='INPUT')
        
        return {
            'form_type': 'VAT 1',
            'period': f"{vat_return.period_start.strftime('%B %Y')}",
            'taxpayer_name': 'Company Name',
            'taxpayer_address': 'Company Address',
            'tax_id': 'Tax ID',
            'branch': 'Main Branch',
            'activities': 'Trading/Services',
            'section_a': {
                'total_supplies': float(vat_return.total_output_vat),
                'vat_on_supplies': float(vat_return.total_output_vat),
                'zero_rated_supplies': float(vat_return.zero_rated_sales),
                'exempt_supplies': float(vat_return.exempt_sales),
            },
            'section_b': {
                'total_purchases': float(sum(d.taxable_amount for d in input_details)),
                'vat_on_purchases': float(vat_return.total_input_vat),
            },
            'section_c': {
                'vat_payable': float(vat_return.total_vat_payable),
                'vat_refundable': float(vat_return.total_vat_refundable),
            },
            'output_count': output_details.count(),
            'input_count': input_details.count(),
            'total_transactions': details.count(),
        }
