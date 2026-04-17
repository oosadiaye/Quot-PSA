"""
NCoA Service — utilities for looking up, validating, and resolving NCoA codes.
Used by all transactional modules (budget, treasury, payroll, procurement).
"""
from django.db import models
from accounting.models.ncoa import (
    AdministrativeSegment, EconomicSegment, FunctionalSegment,
    ProgrammeSegment, FundSegment, GeographicSegment, NCoACode,
)


class NCoAResolutionError(Exception):
    """Raised when NCoA segment codes cannot be resolved to valid segment objects."""
    pass


class NCoAService:

    @staticmethod
    def resolve_code(
        admin_code: str,
        economic_code: str,
        functional_code: str,
        programme_code: str,
        fund_code: str,
        geo_code: str,
    ) -> NCoACode:
        """
        Resolve string codes to segment objects and return (or create) NCoACode.
        Raises NCoAResolutionError with descriptive message on any lookup failure.
        """
        errors: list[str] = []

        def get_segment(model, code, segment_name):
            try:
                return model.objects.get(code=code, is_active=True)
            except model.DoesNotExist:
                errors.append(f"{segment_name} code '{code}' not found or inactive.")
                return None

        admin    = get_segment(AdministrativeSegment, admin_code,     "Administrative")
        economic = get_segment(EconomicSegment,       economic_code,  "Economic")
        func     = get_segment(FunctionalSegment,     functional_code, "Functional")
        prog     = get_segment(ProgrammeSegment,      programme_code, "Programme")
        fund     = get_segment(FundSegment,           fund_code,      "Fund")
        geo      = get_segment(GeographicSegment,     geo_code,       "Geographic")

        if errors:
            raise NCoAResolutionError(
                "NCoA resolution failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        # Validate economic segment is posting-level
        if not economic.is_posting_level:
            raise NCoAResolutionError(
                f"Economic segment {economic_code} ({economic.name}) is a header account "
                f"and cannot be posted to. Use a posting-level child account."
            )

        # Validate economic segment is not a control account
        if economic.is_control_account:
            raise NCoAResolutionError(
                f"Economic segment {economic_code} ({economic.name}) is a control account. "
                f"Direct posting is not permitted."
            )

        return NCoACode.get_or_create_code(
            admin_id=admin.pk,
            economic_id=economic.pk,
            functional_id=func.pk,
            programme_id=prog.pk,
            fund_id=fund.pk,
            geo_id=geo.pk,
        )

    @staticmethod
    def validate_expenditure_account(economic_code: str) -> bool:
        """Returns True if economic code is a valid, active expenditure account (2xxxxxxx)."""
        try:
            seg = EconomicSegment.objects.get(code=economic_code, is_active=True)
            return seg.account_type_code == '2' and seg.is_posting_level
        except EconomicSegment.DoesNotExist:
            return False

    @staticmethod
    def validate_revenue_account(economic_code: str) -> bool:
        """Returns True if economic code is a valid, active revenue account (1xxxxxxx)."""
        try:
            seg = EconomicSegment.objects.get(code=economic_code, is_active=True)
            return seg.account_type_code == '1' and seg.is_posting_level
        except EconomicSegment.DoesNotExist:
            return False

    @staticmethod
    def get_posting_accounts_by_type(account_type_code: str):
        """Returns QuerySet of posting-level accounts for a given type code."""
        return EconomicSegment.objects.filter(
            account_type_code=account_type_code,
            is_posting_level=True,
            is_active=True,
        ).order_by('code')

    @staticmethod
    def search_accounts(query: str, account_type: str = None):
        """Full-text search across economic segment codes and names."""
        qs = EconomicSegment.objects.filter(
            is_posting_level=True, is_active=True,
        ).filter(
            models.Q(code__icontains=query) | models.Q(name__icontains=query)
        )
        if account_type:
            qs = qs.filter(account_type_code=account_type)
        return qs.order_by('code')[:50]
