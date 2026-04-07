"""Aging Reports Service

Generates AR/AP aging reports for collection planning and credit management.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from django.db.models import Sum, Q, F
from accounting.models import (
    CustomerInvoice, VendorInvoice, Payment, Receipt,
    CustomerAging, CostCenter
)


@dataclass
class AgingBucket:
    """A single aging bucket."""
    bucket_name: str
    min_days: int
    max_days: int
    total_amount: Decimal
    invoice_count: int


@dataclass
class AgingCustomerDetail:
    """Customer aging detail."""
    customer_id: int
    customer_name: str
    credit_limit: Decimal
    current_balance: Decimal
    past_due_amount: Decimal
    buckets: List[AgingBucket]
    is_over_credit_limit: bool


@dataclass
class AgingReportResult:
    """Complete aging report."""
    report_date: date
    as_of_date: date
    fiscal_year: int
    period: int
    
    total_receivables: Decimal
    total_current: Decimal
    total_30_days: Decimal
    total_60_days: Decimal
    total_90_days: Decimal
    total_over_120_days: Decimal
    
    customer_count: int
    overdue_count: int
    
    customers: List[Dict[str, Any]]
    
    bucket_summary: Dict[str, Decimal]


class AgingReportService:
    """Service for AR/AP aging reports."""
    
    DEFAULT_BUCKETS = [
        {'name': 'Current', 'min': 0, 'max': 30},
        {'name': '31-60 Days', 'min': 31, 'max': 60},
        {'name': '61-90 Days', 'min': 61, 'max': 90},
        {'name': '91-120 Days', 'min': 91, 'max': 120},
        {'name': 'Over 120 Days', 'min': 121, 'max': 9999},
    ]
    
    @classmethod
    def get_days_overdue(cls, invoice_date: date, as_of_date: date) -> int:
        """Calculate days overdue from invoice date."""
        return (as_of_date - invoice_date).days
    
    @classmethod
    def get_bucket_for_days(cls, days: int, buckets: List[Dict] = None) -> Dict:
        """Get the aging bucket for a given number of days."""
        if buckets is None:
            buckets = cls.DEFAULT_BUCKETS
        
        for bucket in buckets:
            if bucket['min'] <= days <= bucket['max']:
                return bucket
        return buckets[-1]
    
    @classmethod
    def calculate_customer_aging(
        cls,
        customer_id: int,
        as_of_date: date = None,
        cost_center_id: int = None
    ) -> AgingCustomerDetail:
        """Calculate aging for a single customer."""
        from sales.models import Customer
        
        if as_of_date is None:
            as_of_date = date.today()
        
        try:
            customer = Customer.objects.get(id=customer_id)
            customer_name = customer.name
            credit_limit = getattr(customer, 'credit_limit', Decimal('0')) or Decimal('0')
        except:
            customer_name = f"Customer {customer_id}"
            credit_limit = Decimal('0')
        
        invoices = CustomerInvoice.objects.filter(
            customer_id=customer_id,
            status__in=['POSTED', 'APPROVED']
        )
        
        if cost_center_id:
            invoices = invoices.filter(cost_center_id=cost_center_id)
        
        buckets_data = {}
        for bucket_def in cls.DEFAULT_BUCKETS:
            buckets_data[bucket_def['name']] = {
                'total': Decimal('0'),
                'count': 0,
                'min_days': bucket_def['min'],
                'max_days': bucket_def['max'],
            }
        
        total_balance = Decimal('0')
        past_due_amount = Decimal('0')
        
        for invoice in invoices:
            amount = invoice.total_amount or Decimal('0')
            paid_amount = invoice.amount_paid or Decimal('0')
            balance = amount - paid_amount
            
            if balance <= 0:
                continue
            
            days = cls.get_days_overdue(invoice.invoice_date, as_of_date)
            bucket = cls.get_bucket_for_days(days)
            bucket_name = bucket['name']
            
            buckets_data[bucket_name]['total'] += balance
            buckets_data[bucket_name]['count'] += 1
            
            total_balance += balance
            if days > 30:
                past_due_amount += balance
        
        buckets = [
            AgingBucket(
                bucket_name=name,
                min_days=data['min_days'],
                max_days=data['max_days'],
                total_amount=data['total'],
                invoice_count=data['count']
            )
            for name, data in buckets_data.items()
        ]
        
        return AgingCustomerDetail(
            customer_id=customer_id,
            customer_name=customer_name,
            credit_limit=credit_limit,
            current_balance=total_balance,
            past_due_amount=past_due_amount,
            buckets=buckets,
            is_over_credit_limit=total_balance > credit_limit if credit_limit > 0 else False,
        )
    
    @classmethod
    def generate_ar_aging_report(
        cls,
        as_of_date: date = None,
        fiscal_year: int = None,
        period: int = None,
        cost_center_id: int = None,
        customer_ids: List[int] = None,
        include_zero_balance: bool = False
    ) -> AgingReportResult:
        """Generate complete AR aging report."""
        if as_of_date is None:
            as_of_date = date.today()
        
        invoices_query = CustomerInvoice.objects.filter(
            status__in=['POSTED', 'APPROVED']
        )
        
        if customer_ids:
            invoices_query = invoices_query.filter(customer_id__in=customer_ids)
        
        if cost_center_id:
            invoices_query = invoices_query.filter(cost_center_id=cost_center_id)
        
        if fiscal_year:
            invoices_query = invoices_query.filter(fiscal_year=fiscal_year)
        
        customer_ids_with_balance = invoices_query.values_list(
            'customer_id', flat=True
        ).distinct()
        
        total_receivables = Decimal('0')
        total_current = Decimal('0')
        total_30 = Decimal('0')
        total_60 = Decimal('0')
        total_90 = Decimal('0')
        total_over_120 = Decimal('0')
        
        customer_details = []
        overdue_count = 0
        
        for cust_id in customer_ids_with_balance:
            aging = cls.calculate_customer_aging(cust_id, as_of_date, cost_center_id)
            
            if not include_zero_balance and aging.current_balance == 0:
                continue
            
            customer_details.append({
                'customer_id': aging.customer_id,
                'customer_name': aging.customer_name,
                'credit_limit': aging.credit_limit,
                'current_balance': aging.current_balance,
                'past_due_amount': aging.past_due_amount,
                'is_over_credit_limit': aging.is_over_credit_limit,
                'buckets': [
                    {
                        'name': b.bucket_name,
                        'total': b.total_amount,
                        'count': b.invoice_count,
                    }
                    for b in aging.buckets
                ]
            })
            
            total_receivables += aging.current_balance
            
            for bucket in aging.buckets:
                if bucket.bucket_name == 'Current':
                    total_current += bucket.total_amount
                elif bucket.bucket_name == '31-60 Days':
                    total_30 += bucket.total_amount
                elif bucket.bucket_name == '61-90 Days':
                    total_60 += bucket.total_amount
                elif bucket.bucket_name == '91-120 Days':
                    total_90 += bucket.total_amount
                elif bucket.bucket_name == 'Over 120 Days':
                    total_over_120 += bucket.total_amount
            
            if aging.past_due_amount > 0:
                overdue_count += 1
        
        customer_details.sort(key=lambda x: x['current_balance'], reverse=True)
        
        return AgingReportResult(
            report_date=date.today(),
            as_of_date=as_of_date,
            fiscal_year=fiscal_year or date.today().year,
            period=period or ((date.today().month - 1) % 12) + 1,
            total_receivables=total_receivables,
            total_current=total_current,
            total_30_days=total_30,
            total_60_days=total_60,
            total_90_days=total_90,
            total_over_120_days=total_over_120,
            customer_count=len(customer_details),
            overdue_count=overdue_count,
            customers=customer_details,
            bucket_summary={
                'Current': total_current,
                '31-60 Days': total_30,
                '61-90 Days': total_60,
                '91-120 Days': total_90,
                'Over 120 Days': total_over_120,
            },
        )
    
    @classmethod
    def generate_ap_aging_report(
        cls,
        as_of_date: date = None,
        fiscal_year: int = None,
        period: int = None,
        vendor_ids: List[int] = None,
        include_zero_balance: bool = False
    ) -> AgingReportResult:
        """Generate complete AP aging report."""
        if as_of_date is None:
            as_of_date = date.today()
        
        invoices_query = VendorInvoice.objects.filter(
            status__in=['POSTED', 'APPROVED']
        )
        
        if vendor_ids:
            invoices_query = invoices_query.filter(vendor_id__in=vendor_ids)
        
        if fiscal_year:
            invoices_query = invoices_query.filter(fiscal_year=fiscal_year)
        
        vendor_ids_with_balance = invoices_query.values_list(
            'vendor_id', flat=True
        ).distinct()
        
        total_payables = Decimal('0')
        total_current = Decimal('0')
        total_30 = Decimal('0')
        total_60 = Decimal('0')
        total_90 = Decimal('0')
        total_over_120 = Decimal('0')
        
        vendor_details = []
        
        for vend_id in vendor_ids_with_balance:
            try:
                from procurement.models import Vendor
                vendor = Vendor.objects.get(id=vend_id)
                vendor_name = vendor.name
            except:
                vendor_name = f"Vendor {vend_id}"
            
            invoices = invoices_query.filter(vendor_id=vend_id)
            
            buckets_data = {}
            for bucket_def in cls.DEFAULT_BUCKETS:
                buckets_data[bucket_def['name']] = {
                    'total': Decimal('0'),
                    'count': 0,
                }
            
            total_balance = Decimal('0')
            
            for invoice in invoices:
                amount = invoice.total_amount or Decimal('0')
                paid_amount = invoice.amount_paid or Decimal('0')
                balance = amount - paid_amount
                
                if balance <= 0:
                    continue
                
                days = cls.get_days_overdue(invoice.invoice_date, as_of_date)
                bucket = cls.get_bucket_for_days(days)
                bucket_name = bucket['name']
                
                buckets_data[bucket_name]['total'] += balance
                buckets_data[bucket_name]['count'] += 1
                
                total_balance += balance
            
            if not include_zero_balance and total_balance == 0:
                continue
            
            vendor_details.append({
                'vendor_id': vend_id,
                'vendor_name': vendor_name,
                'current_balance': total_balance,
                'buckets': [
                    {
                        'name': name,
                        'total': data['total'],
                        'count': data['count'],
                    }
                    for name, data in buckets_data.items()
                ]
            })
            
            total_payables += total_balance
            
            for name, data in buckets_data.items():
                if name == 'Current':
                    total_current += data['total']
                elif name == '31-60 Days':
                    total_30 += data['total']
                elif name == '61-90 Days':
                    total_60 += data['total']
                elif name == '91-120 Days':
                    total_90 += data['total']
                elif name == 'Over 120 Days':
                    total_over_120 += data['total']
        
        vendor_details.sort(key=lambda x: x['current_balance'], reverse=True)
        
        return AgingReportResult(
            report_date=date.today(),
            as_of_date=as_of_date,
            fiscal_year=fiscal_year or date.today().year,
            period=period or ((date.today().month - 1) % 12) + 1,
            total_receivables=total_payables,
            total_current=total_current,
            total_30_days=total_30,
            total_60_days=total_60,
            total_90_days=total_90,
            total_over_120_days=total_over_120,
            customer_count=len(vendor_details),
            overdue_count=0,
            customers=vendor_details,
            bucket_summary={
                'Current': total_current,
                '31-60 Days': total_30,
                '61-90 Days': total_60,
                '91-120 Days': total_90,
                'Over 120 Days': total_over_120,
            },
        )
    
    @classmethod
    def save_aging_snapshot(
        cls,
        as_of_date: date,
        fiscal_year: int,
        period: int
    ) -> List[CustomerAging]:
        """Save aging snapshot to database for historical reporting."""
        report = cls.generate_ar_aging_report(
            as_of_date=as_of_date,
            fiscal_year=fiscal_year,
            period=period,
            include_zero_balance=False
        )
        
        snapshots = []
        
        for customer_data in report.customers:
            aging = CustomerAging(
                customer_id=customer_data['customer_id'],
                as_of_date=as_of_date,
                current=Decimal('0'),
                days_30=Decimal('0'),
                days_60=Decimal('0'),
                days_90=Decimal('0'),
                days_120=Decimal('0'),
                total=customer_data['current_balance'],
            )
            
            for bucket in customer_data['buckets']:
                if bucket['name'] == 'Current':
                    aging.current = bucket['total']
                elif bucket['name'] == '31-60 Days':
                    aging.days_30 = bucket['total']
                elif bucket['name'] == '61-90 Days':
                    aging.days_60 = bucket['total']
                elif bucket['name'] == '91-120 Days':
                    aging.days_90 = bucket['total']
                elif bucket['name'] == 'Over 120 Days':
                    aging.days_120 = bucket['total']
            
            aging.save()
            snapshots.append(aging)
        
        return snapshots
