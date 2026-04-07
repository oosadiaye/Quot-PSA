from django.contrib import admin
from .models import Customer, Lead, Opportunity, Quotation, QuotationLine, SalesOrder, SalesOrderLine, DeliveryNote, DeliveryNoteLine

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['customer_code', 'name', 'credit_limit', 'balance', 'credit_available', 'credit_status']
    list_filter = ['industry']
    search_fields = ['name', 'customer_code', 'contact_email']

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'email', 'status', 'estimated_value']
    list_filter = ['status', 'source']
    search_fields = ['name', 'company', 'email']

@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ['name', 'customer', 'stage', 'expected_value', 'probability', 'expected_close_date']
    list_filter = ['stage']
    search_fields = ['name', 'customer__name']


class QuotationLineInline(admin.TabularInline):
    model = QuotationLine
    extra = 0


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ['quotation_number', 'customer', 'quotation_date', 'valid_until', 'status']
    list_filter = ['status']
    search_fields = ['quotation_number', 'customer__name']
    inlines = [QuotationLineInline]


class SalesOrderLineInline(admin.TabularInline):
    model = SalesOrderLine
    extra = 0


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'customer', 'order_date', 'status']
    list_filter = ['status']
    search_fields = ['order_number', 'customer__name']
    inlines = [SalesOrderLineInline]


class DeliveryNoteLineInline(admin.TabularInline):
    model = DeliveryNoteLine
    extra = 0


@admin.register(DeliveryNote)
class DeliveryNoteAdmin(admin.ModelAdmin):
    list_display = ['delivery_number', 'sales_order', 'delivery_date', 'status']
    list_filter = ['status']
    search_fields = ['delivery_number']
    inlines = [DeliveryNoteLineInline]
