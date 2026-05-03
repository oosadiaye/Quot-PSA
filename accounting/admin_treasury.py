"""Admin registration for Treasury, Revenue, and IPSAS models — Quot PSE"""
from django.contrib import admin
from accounting.models.treasury import TreasuryAccount, PaymentVoucherGov, PaymentInstruction
from accounting.models.revenue import RevenueHead, RevenueCollection


@admin.register(TreasuryAccount)
class TreasuryAccountAdmin(admin.ModelAdmin):
    list_display = ['account_number', 'account_name', 'account_type', 'bank',
                    'gl_cash_account', 'current_balance', 'is_active']
    list_filter = ['account_type', 'is_active', 'bank']
    search_fields = ['account_number', 'account_name',
                     'gl_cash_account__code', 'gl_cash_account__name']
    list_select_related = ['mda', 'fund_segment', 'parent_account',
                           'gl_cash_account', 'ncoa_cash_code']
    raw_id_fields = ['parent_account', 'gl_cash_account', 'ncoa_cash_code']
    fieldsets = (
        ('Bank Account', {
            'fields': ('account_number', 'account_name', 'bank', 'sort_code',
                       'account_type', 'is_active'),
        }),
        ('Ownership & Segmentation', {
            'fields': ('mda', 'fund_segment', 'parent_account'),
        }),
        ('GL Mapping (IPSAS)', {
            'description': (
                'Link this TSA to its GL cash control account. Required for '
                'IPSAS cash flow reporting and deterministic bank reconciliation.'
            ),
            'fields': ('gl_cash_account', 'ncoa_cash_code'),
        }),
        ('State', {
            'fields': ('current_balance', 'last_reconciled', 'description'),
        }),
    )
    ordering = ['account_type', 'account_number']


@admin.register(PaymentVoucherGov)
class PaymentVoucherGovAdmin(admin.ModelAdmin):
    list_display = ['voucher_number', 'payment_type', 'payee_name',
                    'gross_amount', 'net_amount', 'status']
    list_filter = ['status', 'payment_type']
    search_fields = ['voucher_number', 'payee_name', 'narration']
    list_select_related = ['ncoa_code__economic', 'tsa_account', 'appropriation']
    raw_id_fields = ['ncoa_code', 'appropriation', 'warrant', 'tsa_account', 'journal']
    ordering = ['-created_at']
    readonly_fields = ['net_amount']


@admin.register(PaymentInstruction)
class PaymentInstructionAdmin(admin.ModelAdmin):
    list_display = ['batch_reference', 'beneficiary_name', 'amount', 'status',
                    'submitted_at', 'processed_at']
    list_filter = ['status']
    search_fields = ['beneficiary_name', 'batch_reference', 'bank_reference']
    raw_id_fields = ['payment_voucher', 'tsa_account']
    ordering = ['-created_at']


@admin.register(RevenueHead)
class RevenueHeadAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'revenue_type', 'is_active']
    list_filter = ['revenue_type', 'is_active']
    search_fields = ['code', 'name']
    list_select_related = ['economic_segment', 'collection_mda']
    ordering = ['code']


@admin.register(RevenueCollection)
class RevenueCollectionAdmin(admin.ModelAdmin):
    list_display = ['receipt_number', 'payer_name', 'amount', 'collection_date',
                    'collection_channel', 'status']
    list_filter = ['status', 'collection_channel', 'revenue_head']
    search_fields = ['receipt_number', 'payer_name', 'payer_tin', 'payment_reference']
    list_select_related = ['revenue_head', 'tsa_account', 'collecting_mda']
    raw_id_fields = ['ncoa_code', 'tsa_account', 'journal']
    ordering = ['-collection_date']
