from django.contrib import admin
from .models import (
    Vendor, VendorCategory, PurchaseRequest, PurchaseOrder, PurchaseOrderLine,
    GoodsReceivedNote, GoodsReceivedNoteLine, InvoiceMatching,
    VendorCreditNote, VendorDebitNote, PurchaseReturn, PurchaseReturnLine,
    VendorPerformanceMetrics,
)


@admin.register(VendorCategory)
class VendorCategoryAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'reconciliation_account', 'is_active']
    search_fields = ['code', 'name']
    list_filter = ['is_active']


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'is_active', 'quality_score']
    search_fields = ['code', 'name']
    list_filter = ['is_active']


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = ['request_number', 'description', 'status']
    search_fields = ['request_number', 'description']
    list_filter = ['status']


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ['po_number', 'vendor', 'status', 'order_date']
    search_fields = ['po_number']
    list_filter = ['status', 'vendor']
    inlines = [PurchaseOrderLineInline]


class GoodsReceivedNoteLineInline(admin.TabularInline):
    model = GoodsReceivedNoteLine
    extra = 0


@admin.register(GoodsReceivedNote)
class GoodsReceivedNoteAdmin(admin.ModelAdmin):
    list_display = ['grn_number', 'purchase_order', 'status']
    search_fields = ['grn_number']
    list_filter = ['status']
    inlines = [GoodsReceivedNoteLineInline]


@admin.register(InvoiceMatching)
class InvoiceMatchingAdmin(admin.ModelAdmin):
    list_display = ['purchase_order', 'status', 'match_type']
    list_filter = ['status', 'match_type']


@admin.register(VendorCreditNote)
class VendorCreditNoteAdmin(admin.ModelAdmin):
    list_display = ['credit_note_number', 'vendor', 'amount', 'status']
    list_filter = ['status']
    search_fields = ['credit_note_number', 'vendor__name']


@admin.register(VendorDebitNote)
class VendorDebitNoteAdmin(admin.ModelAdmin):
    list_display = ['debit_note_number', 'vendor', 'amount', 'status']
    list_filter = ['status']
    search_fields = ['debit_note_number', 'vendor__name']


class PurchaseReturnLineInline(admin.TabularInline):
    model = PurchaseReturnLine
    extra = 0


@admin.register(PurchaseReturn)
class PurchaseReturnAdmin(admin.ModelAdmin):
    list_display = ['return_number', 'vendor', 'total_amount', 'status']
    list_filter = ['status']
    search_fields = ['return_number', 'vendor__name']
    inlines = [PurchaseReturnLineInline]


@admin.register(VendorPerformanceMetrics)
class VendorPerformanceMetricsAdmin(admin.ModelAdmin):
    list_display = ['vendor', 'period_start', 'period_end', 'quality_score']
    list_filter = ['vendor']


# ─── BPP Due Process Admin ───────────────────────────────────────────

from .models import ProcurementThreshold, CertificateOfNoObjection, ProcurementBudgetLink


@admin.register(ProcurementThreshold)
class ProcurementThresholdAdmin(admin.ModelAdmin):
    list_display = ['category', 'authority_level', 'min_amount', 'max_amount',
                    'requires_bpp_no', 'is_active']
    list_filter = ['category', 'authority_level', 'is_active']
    ordering = ['category', 'min_amount']


@admin.register(CertificateOfNoObjection)
class CertificateOfNoObjectionAdmin(admin.ModelAdmin):
    list_display = ['certificate_number', 'purchase_order', 'authority_level',
                    'issued_date', 'expiry_date', 'is_valid']
    list_filter = ['is_valid', 'authority_level']
    search_fields = ['certificate_number']
    raw_id_fields = ['purchase_order']


@admin.register(ProcurementBudgetLink)
class ProcurementBudgetLinkAdmin(admin.ModelAdmin):
    list_display = ['purchase_order', 'appropriation', 'committed_amount', 'status']
    list_filter = ['status']
    raw_id_fields = ['purchase_order', 'appropriation', 'ncoa_code']
