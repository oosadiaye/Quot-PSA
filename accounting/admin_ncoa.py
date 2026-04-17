"""NCoA Admin Registration — Quot PSE"""
from django.contrib import admin
from accounting.models.ncoa import (
    AdministrativeSegment, EconomicSegment, FunctionalSegment,
    ProgrammeSegment, FundSegment, GeographicSegment, NCoACode,
)


@admin.register(AdministrativeSegment)
class AdministrativeSegmentAdmin(admin.ModelAdmin):
    list_display  = ['code', 'name', 'level', 'sector_code', 'is_active', 'is_mda']
    list_filter   = ['level', 'sector_code', 'is_active', 'mda_type']
    search_fields = ['code', 'name']
    ordering      = ['code']


@admin.register(EconomicSegment)
class EconomicSegmentAdmin(admin.ModelAdmin):
    list_display  = ['code', 'name', 'account_type_code', 'is_posting_level',
                     'is_control_account', 'normal_balance', 'is_active']
    list_filter   = ['account_type_code', 'is_posting_level', 'is_active']
    search_fields = ['code', 'name']
    ordering      = ['code']


@admin.register(FunctionalSegment)
class FunctionalSegmentAdmin(admin.ModelAdmin):
    list_display  = ['code', 'name', 'division_code', 'is_active']
    list_filter   = ['division_code', 'is_active']
    search_fields = ['code', 'name']


@admin.register(ProgrammeSegment)
class ProgrammeSegmentAdmin(admin.ModelAdmin):
    list_display  = ['code', 'name', 'is_capital', 'is_active']
    list_filter   = ['is_capital', 'is_active']
    search_fields = ['code', 'name']


@admin.register(FundSegment)
class FundSegmentAdmin(admin.ModelAdmin):
    list_display  = ['code', 'name', 'main_fund_code', 'is_restricted', 'is_active']
    list_filter   = ['main_fund_code', 'is_restricted', 'is_active']
    search_fields = ['code', 'name']


@admin.register(GeographicSegment)
class GeographicSegmentAdmin(admin.ModelAdmin):
    list_display  = ['code', 'name', 'zone_code', 'state_code', 'is_active']
    list_filter   = ['zone_code', 'state_code', 'is_active']
    search_fields = ['code', 'name']


@admin.register(NCoACode)
class NCoACodeAdmin(admin.ModelAdmin):
    list_display        = ['full_code', 'account_name', 'mda_name', 'is_active']
    list_select_related = [
        'administrative', 'economic', 'functional',
        'programme', 'fund', 'geographic',
    ]
    list_filter   = ['is_active', 'fund', 'economic__account_type_code']
    search_fields = ['economic__code', 'economic__name', 'administrative__name']
    raw_id_fields = [
        'administrative', 'economic', 'functional',
        'programme', 'fund', 'geographic',
    ]
