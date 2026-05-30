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
        # FiscalPeriodViewSet.reopen reads ``request.data`` (DRF), so
        # the test request must be built via DRF's APIRequestFactory —
        # Django's plain RequestFactory yields a WSGIRequest that only
        # exposes ``request.POST``.
        from rest_framework.test import APIRequestFactory
        from rest_framework.request import Request
        from accounting.views.period_fiscal import FiscalPeriodViewSet
        _drf = APIRequestFactory()
        viewset = FiscalPeriodViewSet()
        viewset.kwargs = {'pk': closed_fiscal_period.pk}
        from rest_framework.parsers import JSONParser
        viewset.request = Request(
            _drf.post(
                f'/periods/{closed_fiscal_period.pk}/reopen/',
                {'reason': 'oops'},  # too short (< 10 chars)
                format='json',
            ),
            parsers=[JSONParser()],
        )
        viewset.request.user = superuser
        viewset.format_kwarg = None

        response = viewset.reopen(viewset.request, pk=closed_fiscal_period.pk)
        assert response.status_code == 400

    def test_reopen_refused_without_permission(self, closed_fiscal_period,
                                               maker_user, rf):
        """Regular users (no is_staff, no reopen_fiscal_period perm) are 403."""
        from rest_framework.test import APIRequestFactory
        from rest_framework.request import Request
        from accounting.views.period_fiscal import FiscalPeriodViewSet
        _drf = APIRequestFactory()
        viewset = FiscalPeriodViewSet()
        viewset.kwargs = {'pk': closed_fiscal_period.pk}
        from rest_framework.parsers import JSONParser
        viewset.request = Request(
            _drf.post(
                f'/periods/{closed_fiscal_period.pk}/reopen/',
                {'reason': 'Need to amend prior year for audit'},
                format='json',
            ),
            parsers=[JSONParser()],
        )
        viewset.request.user = maker_user
        viewset.format_kwarg = None

        response = viewset.reopen(viewset.request, pk=closed_fiscal_period.pk)
        assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
class TestFiscalPeriodReopenTwoActor:
    """V7 — two-actor reopen approval workflow.

    Legacy single-actor reopen is blocked by default (405). Reopens go
    through ``reopen_request`` → second-actor ``reopen_approve``. The
    approver must NOT be the requester (the second-actor check).
    """

    @staticmethod
    def _build_view(view_cls, user, method, url, data, pk, action=None,
                    target_obj=None):
        """Construct a viewset wired up enough to invoke an action body.

        Bypasses DRF dispatch — the action method is called directly. If
        ``target_obj`` is supplied, ``view.get_object`` is monkey-patched
        to return it without re-running ``check_object_permissions``
        (which would re-evaluate MFA / RBAC perms that the action body
        intentionally enforces in code).
        """
        from rest_framework.test import APIRequestFactory
        from rest_framework.request import Request
        from rest_framework.parsers import JSONParser

        _drf = APIRequestFactory()
        view = view_cls()
        view.kwargs = {'pk': pk}
        view.action = action
        view.request = Request(
            getattr(_drf, method)(url, data, format='json'),
            parsers=[JSONParser()],
        )
        view.request.user = user
        view.format_kwarg = None
        if target_obj is not None:
            view.get_object = lambda: target_obj
        return view

    def _grant_reopen_perm(self, user):
        """Make ``user.has_perm('accounting.reopen_fiscal_period')`` True.

        Persisting the perm via ``user.user_permissions.add()`` doesn't
        survive the auth backend's perm-cache invalidation across
        tenant schema switches in tests, so we monkey-patch ``has_perm``
        on the user instance directly. The action-body permission check
        is what we're testing — not the auth backend's lookup mechanics.
        """
        granted = {
            'accounting.reopen_fiscal_period',
        }
        original_has_perm = user.has_perm

        def _patched_has_perm(perm, obj=None):
            if perm in granted:
                return True
            return original_has_perm(perm, obj)

        user.has_perm = _patched_has_perm
        return user

    def test_legacy_reopen_returns_405_for_non_superuser(
        self, closed_fiscal_period, maker_user,
    ):
        """V7 — Non-superuser holding only the base perm hits 405 now."""
        from accounting.views.period_fiscal import FiscalPeriodViewSet

        # Grant the base reopen perm — without the new single-actor
        # escape-hatch perm the legacy endpoint must refuse.
        user = self._grant_reopen_perm(maker_user)

        view = self._build_view(
            FiscalPeriodViewSet,
            user,
            'post',
            f'/periods/{closed_fiscal_period.pk}/reopen/',
            {'reason': 'Need to amend prior year for audit'},
            closed_fiscal_period.pk,
            action='reopen',
        )
        response = view.reopen(view.request, pk=closed_fiscal_period.pk)
        assert response.status_code == 405
        # Migration message should point to the new endpoints.
        assert 'reopen-request' in response.data['error']

    def test_reopen_request_creates_pending_approval(
        self, closed_fiscal_period, maker_user,
    ):
        """Stage 1 — ``reopen_request`` returns 202 + creates PENDING row."""
        from accounting.models import FiscalPeriodReopenApproval
        from accounting.views.period_fiscal import FiscalPeriodViewSet

        user = self._grant_reopen_perm(maker_user)

        view = self._build_view(
            FiscalPeriodViewSet,
            user,
            'post',
            f'/periods/{closed_fiscal_period.pk}/reopen-request/',
            {'reason': 'Audit adjustment needed for FY2020'},
            closed_fiscal_period.pk,
            action='reopen_request',
            target_obj=closed_fiscal_period,
        )
        response = view.reopen_request(view.request, pk=closed_fiscal_period.pk)
        assert response.status_code == 202
        assert response.data['status'] == 'PENDING'

        approval = FiscalPeriodReopenApproval.objects.get(
            id=response.data['approval_id'],
        )
        assert approval.fiscal_period_id == closed_fiscal_period.pk
        assert approval.requested_by_id == user.id
        assert approval.approved_by_id is None
        # Period must still be closed at Stage 1 — only Stage 2 mutates.
        closed_fiscal_period.refresh_from_db()
        assert closed_fiscal_period.is_closed is True

    def test_reopen_request_rejects_short_reason(
        self, closed_fiscal_period, maker_user,
    ):
        from accounting.views.period_fiscal import FiscalPeriodViewSet

        user = self._grant_reopen_perm(maker_user)

        view = self._build_view(
            FiscalPeriodViewSet,
            user,
            'post',
            f'/periods/{closed_fiscal_period.pk}/reopen-request/',
            {'reason': 'short'},
            closed_fiscal_period.pk,
            action='reopen_request',
        )
        response = view.reopen_request(view.request, pk=closed_fiscal_period.pk)
        assert response.status_code == 400

    def test_self_approval_rejected_with_403(
        self, closed_fiscal_period, maker_user,
    ):
        """V7 second-actor check — requester cannot approve own request."""
        from accounting.models import FiscalPeriodReopenApproval
        from accounting.views.period_fiscal import (
            FiscalPeriodReopenApprovalViewSet,
        )

        user = self._grant_reopen_perm(maker_user)

        approval = FiscalPeriodReopenApproval.objects.create(
            fiscal_period=closed_fiscal_period,
            requested_by=user,
            reason='Audit adjustment needed for FY2020',
        )

        view = self._build_view(
            FiscalPeriodReopenApprovalViewSet,
            user,
            'post',
            f'/reopen-approvals/{approval.pk}/approve/',
            {},
            approval.pk,
            action='approve',
            target_obj=approval,
        )
        response = view.approve(view.request, pk=approval.pk)
        assert response.status_code == 403
        assert 'cannot approve your own' in response.data['error']

        # Period must remain closed.
        closed_fiscal_period.refresh_from_db()
        assert closed_fiscal_period.is_closed is True

        # Approval must remain PENDING.
        approval.refresh_from_db()
        assert approval.status == 'PENDING'

    def test_second_actor_approval_executes_reopen(
        self, closed_fiscal_period, maker_user, checker_user,
    ):
        """V7 end-to-end — distinct second actor approves and executes."""
        from accounting.models import FiscalPeriodReopenApproval
        from accounting.views.period_fiscal import (
            FiscalPeriodReopenApprovalViewSet,
        )

        maker = self._grant_reopen_perm(maker_user)
        checker = self._grant_reopen_perm(checker_user)

        approval = FiscalPeriodReopenApproval.objects.create(
            fiscal_period=closed_fiscal_period,
            requested_by=maker,
            reason='Audit adjustment needed for FY2020',
        )

        view = self._build_view(
            FiscalPeriodReopenApprovalViewSet,
            checker,  # different from requester
            'post',
            f'/reopen-approvals/{approval.pk}/approve/',
            {},
            approval.pk,
            action='approve',
            target_obj=approval,
        )
        response = view.approve(view.request, pk=approval.pk)
        assert response.status_code == 200

        approval.refresh_from_db()
        assert approval.status == 'EXECUTED'
        assert approval.approved_by_id == checker.id
        assert approval.executed_at is not None

        closed_fiscal_period.refresh_from_db()
        assert closed_fiscal_period.is_closed is False
        assert closed_fiscal_period.status == 'Open'

    def test_approve_non_pending_returns_409(
        self, closed_fiscal_period, maker_user, checker_user,
    ):
        """Already-executed approvals cannot be re-approved."""
        from accounting.models import FiscalPeriodReopenApproval
        from accounting.views.period_fiscal import (
            FiscalPeriodReopenApprovalViewSet,
        )

        checker = self._grant_reopen_perm(checker_user)

        approval = FiscalPeriodReopenApproval.objects.create(
            fiscal_period=closed_fiscal_period,
            requested_by=maker_user,
            reason='Audit adjustment',
            status=FiscalPeriodReopenApproval.STATUS_EXECUTED,
        )

        view = self._build_view(
            FiscalPeriodReopenApprovalViewSet,
            checker,
            'post',
            f'/reopen-approvals/{approval.pk}/approve/',
            {},
            approval.pk,
            action='approve',
            target_obj=approval,
        )
        response = view.approve(view.request, pk=approval.pk)
        assert response.status_code == 409

    def test_reject_pending_request(
        self, closed_fiscal_period, maker_user, checker_user,
    ):
        """Second actor can REJECT a PENDING request."""
        from accounting.models import FiscalPeriodReopenApproval
        from accounting.views.period_fiscal import (
            FiscalPeriodReopenApprovalViewSet,
        )

        checker = self._grant_reopen_perm(checker_user)

        approval = FiscalPeriodReopenApproval.objects.create(
            fiscal_period=closed_fiscal_period,
            requested_by=maker_user,
            reason='Audit adjustment needed for FY2020',
        )

        view = self._build_view(
            FiscalPeriodReopenApprovalViewSet,
            checker,
            'post',
            f'/reopen-approvals/{approval.pk}/reject/',
            {'rejection_reason': 'Insufficient justification provided'},
            approval.pk,
            action='reject',
            target_obj=approval,
        )
        response = view.reject(view.request, pk=approval.pk)
        assert response.status_code == 200

        approval.refresh_from_db()
        assert approval.status == 'REJECTED'
        assert approval.rejection_reason == 'Insufficient justification provided'

        # Period stays closed.
        closed_fiscal_period.refresh_from_db()
        assert closed_fiscal_period.is_closed is True

    def test_superuser_legacy_reopen_still_works(
        self, closed_fiscal_period, superuser,
    ):
        """V7 escape hatch — superusers retain legacy single-actor reopen."""
        from accounting.views.period_fiscal import FiscalPeriodViewSet

        view = self._build_view(
            FiscalPeriodViewSet,
            superuser,
            'post',
            f'/periods/{closed_fiscal_period.pk}/reopen/',
            {'reason': 'Emergency superuser reopen for audit FY2020'},
            closed_fiscal_period.pk,
            action='reopen',
            target_obj=closed_fiscal_period,
        )
        response = view.reopen(view.request, pk=closed_fiscal_period.pk)
        assert response.status_code == 200

        closed_fiscal_period.refresh_from_db()
        assert closed_fiscal_period.is_closed is False
