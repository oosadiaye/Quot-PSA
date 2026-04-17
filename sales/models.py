"""
Sales module — STUB for Quot PSE (public sector).
These minimal models exist ONLY to satisfy migration FK references from
accounting/inventory migrations that were created before the sales module
was deleted. No business logic. No views. No serializers.

DO NOT add any new functionality here. These models will be removed
once a squash migration eliminates the historical FK references.
"""
from django.db import models


class CustomerCategory(models.Model):
    """Stub — satisfies historical migration references."""
    name = models.CharField(max_length=100, default='')
    class Meta:
        db_table = 'sales_customercategory'


class Customer(models.Model):
    """Stub — satisfies historical migration FK references from accounting."""
    name = models.CharField(max_length=200, default='')
    customer_code = models.CharField(max_length=20, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    is_active = models.BooleanField(default=True)
    credit_limit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    credit_check_enabled = models.BooleanField(default=False)
    credit_status = models.CharField(max_length=20, blank=True, default='')
    category = models.ForeignKey(CustomerCategory, null=True, blank=True,
                                 on_delete=models.SET_NULL)
    class Meta:
        db_table = 'sales_customer'


class Lead(models.Model):
    """Stub."""
    name = models.CharField(max_length=200, default='')
    class Meta:
        db_table = 'sales_lead'


class Opportunity(models.Model):
    """Stub."""
    name = models.CharField(max_length=200, default='')
    class Meta:
        db_table = 'sales_opportunity'


class Quotation(models.Model):
    """Stub."""
    quotation_number = models.CharField(max_length=50, default='')
    class Meta:
        db_table = 'sales_quotation'


class QuotationLine(models.Model):
    """Stub."""
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, null=True)
    class Meta:
        db_table = 'sales_quotationline'


class SalesOrder(models.Model):
    """Stub — referenced by accounting.CustomerInvoice.sales_order FK."""
    order_number = models.CharField(max_length=50, default='')
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL)
    class Meta:
        db_table = 'sales_salesorder'


class SalesOrderLine(models.Model):
    """Stub — referenced by inventory.Reservation.sales_order_line FK (historical)."""
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, null=True)
    class Meta:
        db_table = 'sales_salesorderline'


class DeliveryNote(models.Model):
    """Stub."""
    delivery_number = models.CharField(max_length=50, default='')
    class Meta:
        db_table = 'sales_deliverynote'


class DeliveryNoteLine(models.Model):
    """Stub."""
    delivery_note = models.ForeignKey(DeliveryNote, on_delete=models.CASCADE, null=True)
    class Meta:
        db_table = 'sales_deliverynoteline'


class PriceList(models.Model):
    """Stub."""
    name = models.CharField(max_length=100, default='')
    class Meta:
        db_table = 'sales_pricelist'


class PriceListItem(models.Model):
    """Stub."""
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, null=True)
    class Meta:
        db_table = 'sales_pricelistitem'


class CreditNote(models.Model):
    """Stub."""
    credit_note_number = models.CharField(max_length=50, default='')
    class Meta:
        db_table = 'sales_creditnote'


class SalesReturn(models.Model):
    """Stub."""
    return_number = models.CharField(max_length=50, default='')
    class Meta:
        db_table = 'sales_salesreturn'


class SalesReturnLine(models.Model):
    """Stub."""
    sales_return = models.ForeignKey(SalesReturn, on_delete=models.CASCADE, null=True)
    class Meta:
        db_table = 'sales_salesreturnline'


class POSRegister(models.Model):
    """Stub."""
    name = models.CharField(max_length=100, default='')
    class Meta:
        db_table = 'sales_posregister'


class POSSession(models.Model):
    """Stub."""
    register = models.ForeignKey(POSRegister, on_delete=models.CASCADE, null=True)
    class Meta:
        db_table = 'sales_possession'


class POSTransaction(models.Model):
    """Stub."""
    session = models.ForeignKey(POSSession, on_delete=models.CASCADE, null=True)
    class Meta:
        db_table = 'sales_postransaction'


class POSTransactionLine(models.Model):
    """Stub."""
    transaction = models.ForeignKey(POSTransaction, on_delete=models.CASCADE, null=True)
    class Meta:
        db_table = 'sales_postransactionline'
