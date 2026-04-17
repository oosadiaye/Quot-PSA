"""
Sprint-1 regression tests: fiscal period enforcement.

Covers S1-06 — ``PeriodControlService.can_post_to_period`` delegation from
``BasePostingService._validate_fiscal_period`` and the "no periods →
silent allow" bypass removal.

Posting into a closed period must raise. Posting into a period that
simply doesn't exist must also raise (removed bypass).
"""
from datetime import date

import pytest


@pytest.mark.django_db(transaction=True)
class TestPeriodControlEnforcement:
    """_validate_fiscal_period is the last gate on every posting path."""

    def test_closed_period_rejects_posting(self, closed_fiscal_period):
        """Posting to a date inside a closed period raises."""
        from accounting.services.base_posting import (
            BasePostingService, TransactionPostingError,
        )
        with pytest.raises(TransactionPostingError):
            BasePostingService._validate_fiscal_period(
                date(2020, 1, 15),  # inside closed_fiscal_period
            )

    def test_open_period_allows_posting(self, open_fiscal_period):
        """Posting to a date inside an open period returns without raising."""
        from accounting.services.base_posting import BasePostingService
        # Should NOT raise.
        BasePostingService._validate_fiscal_period(
            open_fiscal_period.start_date,
        )

    def test_no_period_for_date_rejects_posting(self, open_fiscal_period):
        """Posting to a date with NO covering period must raise — the
        "no periods → silent allow" bypass is gone (S1-06)."""
        from accounting.services.base_posting import (
            BasePostingService, TransactionPostingError,
        )
        with pytest.raises(TransactionPostingError):
            # Year far outside any seeded period.
            BasePostingService._validate_fiscal_period(date(1990, 6, 15))


@pytest.mark.django_db(transaction=True)
class TestFiscalPeriodReopenGate:
    """S1-14 — reopen requires permission + reason + writes audit log."""

    def test_reopen_requires_reason(self, closed_fiscal_period, superuser, rf):
        """reopen without a reason (or with a short one) returns 400."""
        from accounting.views.period_fiscal import FiscalPeriodViewSet
        viewset = FiscalPeriodViewSet()
        viewset.kwargs = {'pk': closed_fiscal_period.pk}
        viewset.request = rf.post(
            f'/periods/{closed_fiscal_period.pk}/reopen/',
            {'reason': 'oops'},  # too short (< 10 chars)
            content_type='application/json',
        )
        viewset.request.user = superuser
        viewset.format_kwarg = None

        response = viewset.reopen(viewset.request, pk=closed_fiscal_period.pk)
        assert response.status_code == 400

    def test_reopen_refused_without_permission(self, closed_fiscal_period,
                                               maker_user, rf):
        """Regular users (no is_staff, no reopen_fiscal_period perm) are 403."""
        from accounting.views.period_fiscal import FiscalPeriodViewSet
        viewset = FiscalPeriodViewSet()
        viewset.kwargs = {'pk': closed_fiscal_period.pk}
        viewset.request = rf.post(
            f'/periods/{closed_fiscal_period.pk}/reopen/',
            {'reason': 'Need to amend prior year for audit'},
            content_type='application/json',
        )
        viewset.request.user = maker_user
        viewset.format_kwarg = None

        response = viewset.reopen(viewset.request, pk=closed_fiscal_period.pk)
        assert response.status_code == 403
