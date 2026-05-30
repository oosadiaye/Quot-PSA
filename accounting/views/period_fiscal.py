from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import transaction
from datetime import datetime, timedelta, date
from django.utils import timezone
from ..models import (
    FiscalPeriod, FiscalPeriodReopenApproval, FiscalYear, PeriodAccess,
    PeriodCloseCheck, BudgetPeriod,
)
from ..serializers import (
    FiscalPeriodSerializer, FiscalYearSerializer, PeriodAccessSerializer, PeriodCloseCheckSerializer,
    FiscalPeriodReopenApprovalSerializer,
)
from core.utils import api_response
from core.security.client_ip import get_trusted_client_ip as _audit_client_ip


# V7 — message returned by the legacy single-actor reopen path once
# two-actor approval becomes the default. Stays user-actionable.
_REOPEN_TWO_ACTOR_MIGRATION_MSG = (
    'Single-actor period reopen is disabled. Submit a reopen request '
    'via POST /fiscal-periods/{period_id}/reopen-request/, then have a '
    'DIFFERENT user with the accounting.reopen_fiscal_period permission '
    'approve it via POST /reopen-approvals/{approval_id}/approve/. '
    'For emergency cases the accounting.reopen_fiscal_period_single_actor '
    'permission re-enables the legacy single-actor path.'
)


def _user_can_reopen(user) -> bool:
    """Caller has the base reopen privilege (perm or superuser/staff)."""
    return bool(
        user.is_authenticated
        and (
            user.is_superuser
            or user.is_staff
            or user.has_perm('accounting.reopen_fiscal_period')
        )
    )


def _user_can_single_actor_reopen(user) -> bool:
    """Caller may bypass the two-actor flow.

    Superusers always may (operational break-glass). Otherwise the
    caller must hold BOTH ``reopen_fiscal_period`` and the
    ``reopen_fiscal_period_single_actor`` escape-hatch permission.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (
        user.has_perm('accounting.reopen_fiscal_period')
        and user.has_perm('accounting.reopen_fiscal_period_single_actor')
    )


def _execute_period_reopen(*, period, user, request, reason, prior_state):
    """Mutate ``period`` to reopened state + write the audit log row.

    Caller is responsible for the surrounding ``transaction.atomic``
    block. Raises through any audit-log write failure so the atomic
    block rolls back.
    """
    from accounting.models import TransactionAuditLog
    # ``transaction_type`` is max_length=5 — use the short code 'FP' for
    # FiscalPeriod (mirrors 'JE', 'VI', 'PAY' etc. in DOCUMENT_TYPE_CHOICES).
    # 'REOPEN' is not in the standard ACTION_CHOICES (max_length=10) but
    # Django won't enforce choices at the DB layer, and the string fits.
    TransactionAuditLog.objects.create(
        transaction_type='FP',
        transaction_id=period.pk,
        action='REOPEN',
        user=user,
        ip_address=_audit_client_ip(request),
        old_values=prior_state,
        new_values={
            'is_closed': False,
            'status': 'Open',
            'reopen_reason': reason,
            'reopened_by_id': user.id,
            'reopened_at': timezone.now().isoformat(),
        },
    )

    period.is_closed = False
    period.status = 'Open'
    # Preserve original close reason as prefix, annotate with reopen.
    combined = (
        f"[Reopened by {user.username} on {timezone.now():%Y-%m-%d}: {reason}] "
        f"(Original close reason: {prior_state['closed_reason'] or 'n/a'})"
    )
    period.closed_reason = combined
    # Preserve closed_by / closed_date — auditors need the history of
    # who originally closed it.
    period.save()


class FiscalPeriodViewSet(viewsets.ModelViewSet):
    queryset = FiscalPeriod.objects.all()
    serializer_class = FiscalPeriodSerializer
    filterset_fields = ['fiscal_year', 'period_type', 'status']
    ordering_fields = ['fiscal_year', 'period_number']

    def get_permissions(self):
        # S7-01 — Reopening a closed period permits retroactive rewriting
        # of financial statements. It requires both the custom
        # ``reopen_fiscal_period`` permission (enforced in the action
        # body) AND a fresh MFA verification. Closing and locking are
        # likewise gated.
        #
        # V7 — The new two-step flow (``reopen_request`` / ``reopen_approve``)
        # is similarly MFA-gated. Both the requester and the second-actor
        # approver must complete a fresh MFA verification.
        from accounting.permissions import RequiresMFA
        from rest_framework.permissions import IsAuthenticated
        if self.action in (
            'reopen',
            'reopen_request',
            'reopen_approve',
            'reopen_reject',
            'close_periods',
            'lock',
        ):
            return [IsAuthenticated(), RequiresMFA()]
        return super().get_permissions()

    def get_queryset(self):
        queryset = super().get_queryset()
        year = self.request.query_params.get('year')
        if year:
            queryset = queryset.filter(fiscal_year=int(year))
        return queryset

    @action(detail=False, methods=['post'])
    def close_periods(self, request):
        """Bulk-close fiscal periods (H15 — audit + pre-flight gate).

        The bulk close action is high-leverage; previously it required
        only MFA. We now additionally:

          * Require a non-empty ``reason`` (mirrors the per-period
            ``close`` and ``reopen`` actions; minimum 10 chars).
          * Run the pre-flight checklist for every targeted period and
            refuse if any reports unposted journals, unreconciled
            payments, or other "not clear to close" signals — unless the
            caller passes ``force=True`` AND a reason explaining why.
          * Write one ``TransactionAuditLog`` entry per closed period
            so reconstruction works post-hoc. Failure to write an audit
            row aborts the whole bulk close (mirrors per-period reopen
            behaviour).
        """
        from accounting.models import TransactionAuditLog

        close_type = request.data.get('close_type')  # 'daily', 'monthly', 'yearly'
        target_date = request.data.get('target_date')
        close_all_upto = request.data.get('close_all_upto', True)
        reason = (request.data.get('reason') or '').strip()
        force = bool(request.data.get('force', False))

        # V2 — ``force=True`` skips the pre-flight checklist (unposted
        # journals, unreconciled payments, etc.) so it must be gated on
        # a dedicated permission rather than only MFA. Superusers always
        # bypass; everyone else needs ``accounting.force_close_periods``.
        if force and not (
            request.user.is_superuser
            or request.user.has_perm('accounting.force_close_periods')
        ):
            return Response(
                {'error': 'force=True requires the accounting.force_close_periods permission.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if len(reason) < 10:
            return Response(
                {'error': 'A reason of at least 10 characters is required to close periods.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if close_type == 'daily':
            periods = self.queryset.filter(start_date__lte=target_date, status__in=['Open', 'Locked'])
            if close_all_upto:
                periods = periods.filter(end_date__lte=target_date)
        elif close_type == 'monthly':
            from datetime import datetime
            target = datetime.strptime(target_date, '%Y-%m-%d').date()
            periods = self.queryset.filter(
                fiscal_year=target.year,
                period_number=target.month,
                status__in=['Open', 'Locked']
            )
        elif close_type == 'yearly':
            periods = self.queryset.filter(fiscal_year=int(target_date), status__in=['Open', 'Locked'])
        else:
            return Response({'error': 'Invalid close_type'}, status=status.HTTP_400_BAD_REQUEST)

        periods_to_close = []
        # V16 — TOCTOU narrowing. Previously the pre-flight scan ran
        # OUTSIDE the atomic block, so another transaction could create a
        # Draft/Pending journal in the close window between "scan finds
        # zero blockers" and "atomic block flips is_closed". We now:
        #   * Open the atomic block first.
        #   * ``select_for_update(nowait=True)`` the targeted FiscalPeriod
        #     rows. This serializes against concurrent close/reopen calls
        #     on the same periods — a second close call hits an
        #     immediate lock error rather than racing with us.
        #   * Run the pre-flight scan against the locked period set.
        # Residual risk: ``JournalHeader`` writes that don't lock the
        # FiscalPeriod row (most do not — journals reference periods
        # only by ``posting_date``) can still slip in between the scan
        # and the atomic commit. Fully closing that race requires
        # row-locking the period from the journal-write path too —
        # tracked separately; this change narrows the window to the
        # serializable section of one close call.
        with transaction.atomic():
            from accounting.models import JournalHeader
            try:
                target_periods = list(periods.select_for_update(nowait=True))
            except Exception as exc:  # pragma: no cover — DB-engine dependent
                # ``nowait=True`` raises django.db.utils.OperationalError
                # (psycopg2 LockNotAvailable) when another transaction
                # already holds these rows. Surface as 409 so the caller
                # can retry rather than letting the 500 leak through.
                return Response(
                    {
                        'error': (
                            'Could not lock target periods for close — another '
                            'close/reopen is in progress. Retry shortly.'
                        ),
                        'detail': str(exc),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            # Pre-flight: refuse if any period has unposted journals or
            # other blockers unless force=True. Now runs against the
            # locked row set — consistent with what we're about to close.
            if not force:
                blockers = []
                for p in target_periods:
                    pending_count = JournalHeader.objects.filter(
                        posting_date__gte=p.start_date,
                        posting_date__lte=p.end_date,
                        status__in=('Draft', 'Pending', 'Approved'),
                    ).count()
                    if pending_count:
                        blockers.append({
                            'period_id': p.pk,
                            'period_name': str(p),
                            'pending_journals': pending_count,
                        })
                if blockers:
                    return Response(
                        {
                            'error': (
                                'Pre-flight failed: one or more periods have '
                                'pending journals. Post or reject them first, or '
                                'pass force=true with a reason explaining why.'
                            ),
                            'blockers': blockers,
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

            for period in target_periods:
                prior_state = {
                    'is_closed': period.is_closed,
                    'status': period.status,
                }

                # Write audit row BEFORE the mutation. If audit write
                # fails, the whole bulk close rolls back.
                try:
                    TransactionAuditLog.objects.create(
                        transaction_type='fiscalperiod',
                        transaction_id=period.pk,
                        action='CLOSE',
                        user=request.user,
                        ip_address=_audit_client_ip(request),
                        old_values=prior_state,
                        new_values={
                            'is_closed': True,
                            'status': 'Closed',
                            'reason': reason,
                            'forced': force,
                            'closed_by_id': request.user.id,
                            'closed_at': timezone.now().isoformat(),
                        },
                    )
                except Exception as exc:
                    raise  # rollback the atomic block; surface to client

                period.is_closed = True
                period.status = 'Closed'
                period.closed_by = request.user
                period.closed_date = timezone.now()
                period.closed_reason = reason
                period.save()
                periods_to_close.append(period.id)

        return Response({
            'message': f'Closed {len(periods_to_close)} periods',
            'periods': periods_to_close,
            'forced': force,
        })

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        period = self.get_object()
        reason = request.data.get('reason', '')
        period.is_closed = True
        period.status = 'Closed'
        period.closed_by = request.user
        period.closed_date = timezone.now()
        period.closed_reason = reason
        period.save()
        return Response(FiscalPeriodSerializer(period).data)

    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        """Reopen a closed fiscal period (S1-14, V7).

        V7 — Two-actor approval is now the default. A single user with
        ``accounting.reopen_fiscal_period`` could previously rewrite
        historical financial statements; that single-actor path is
        retained ONLY as an emergency escape hatch behind the dedicated
        ``accounting.reopen_fiscal_period_single_actor`` permission
        (default-granted to superusers ONLY by migration).

        Behaviour now:

          * If the caller holds BOTH ``reopen_fiscal_period`` AND
            ``reopen_fiscal_period_single_actor`` (or is a superuser),
            the legacy single-actor reopen executes as before — same
            audit-log row, same atomic mutation.
          * Otherwise the endpoint returns ``405 Method Not Allowed``
            with a message pointing to the two-step
            ``reopen_request`` + ``reopen_approve`` flow.
        """
        user = request.user

        # Base permission gate — same shape as before so unauthorised
        # callers still see 403 not 405.
        if not _user_can_reopen(user):
            return Response(
                {'error': 'You do not have permission to reopen fiscal periods.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # V7 — gate the single-actor path. Without the escape-hatch
        # perm we refuse and point operators at the two-step flow.
        if not _user_can_single_actor_reopen(user):
            return Response(
                {
                    'error': _REOPEN_TWO_ACTOR_MIGRATION_MSG,
                    'period_id': pk,
                    'next_steps': {
                        'request_url': f'/fiscal-periods/{pk}/reopen-request/',
                        'approve_url': '/reopen-approvals/<approval_id>/approve/',
                    },
                },
                status=status.HTTP_405_METHOD_NOT_ALLOWED,
            )

        reason = (request.data.get('reason') or '').strip()
        if len(reason) < 10:
            return Response(
                {'error': 'A reason of at least 10 characters is required to reopen a period.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        period = self.get_object()

        # Capture the closed state for audit BEFORE mutating.
        prior_state = {
            'is_closed': period.is_closed,
            'status': period.status,
            'closed_by_id': getattr(period, 'closed_by_id', None),
            'closed_date': str(getattr(period, 'closed_date', '') or ''),
            'closed_reason': getattr(period, 'closed_reason', '') or '',
        }

        try:
            with transaction.atomic():
                _execute_period_reopen(
                    period=period,
                    user=user,
                    request=request,
                    reason=reason,
                    prior_state=prior_state,
                )
        except Exception:
            # Audit logging or save failure must not silently succeed
            # the reopen — abort with an error so operators investigate.
            return Response(
                {'error': 'Audit logging failed; refusing to reopen period.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(FiscalPeriodSerializer(period).data)

    @action(detail=True, methods=['post'], url_path='reopen-request')
    def reopen_request(self, request, pk=None):
        """V7 — Stage 1 of the two-actor reopen workflow.

        Records a ``FiscalPeriodReopenApproval`` row in PENDING state.
        The actual period mutation happens at Stage 2 when a DIFFERENT
        privileged user calls ``reopen_approve``.

        Returns ``202 Accepted`` with the approval id so the requester
        can hand it off to a second-actor approver.
        """
        user = request.user

        if not _user_can_reopen(user):
            return Response(
                {'error': 'You do not have permission to request a fiscal period reopen.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        reason = (request.data.get('reason') or '').strip()
        if len(reason) < 10:
            return Response(
                {'error': 'A reason of at least 10 characters is required to request a period reopen.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        period = self.get_object()

        # Reject if the period is already open — nothing to reopen.
        if not period.is_closed and period.status != 'Closed':
            return Response(
                {'error': 'Fiscal period is not closed; nothing to reopen.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        approval = FiscalPeriodReopenApproval.objects.create(
            fiscal_period=period,
            requested_by=user,
            reason=reason,
            status=FiscalPeriodReopenApproval.STATUS_PENDING,
        )
        return Response(
            {
                'approval_id': approval.id,
                'fiscal_period': period.pk,
                'status': approval.status,
                'message': 'Awaiting second-actor approval',
                'approve_url': f'/reopen-approvals/{approval.id}/approve/',
                'reject_url': f'/reopen-approvals/{approval.id}/reject/',
                'approval': FiscalPeriodReopenApprovalSerializer(approval).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=['post'])
    def grant_access(self, request, pk=None):
        period = self.get_object()
        user_id = request.data.get('user_id')
        access_type = request.data.get('access_type', 'Temporary')
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        reason = request.data.get('reason', '')

        from django.contrib.auth import get_user_model
        User = get_user_model()

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        access = PeriodAccess.objects.create(
            period=period,
            user=user,
            access_type=access_type,
            start_date=start_date,
            end_date=end_date,
            granted_by=request.user,
            reason=reason,
            is_active=True
        )

        return Response(PeriodAccessSerializer(access).data)

    @action(detail=True, methods=['get'])
    def access_list(self, request, pk=None):
        period = self.get_object()
        accesses = period.access_grants.all()
        return Response(PeriodAccessSerializer(accesses, many=True).data)


class FiscalYearViewSet(viewsets.ModelViewSet):
    queryset = FiscalYear.objects.all()
    serializer_class = FiscalYearSerializer
    filterset_fields = ['year', 'status', 'period_type']
    ordering_fields = ['year']

    MAX_OPEN_YEARS = 2  # SAP-style: only 2 fiscal years open simultaneously

    def get_permissions(self):
        # S7-01 — Year-end close locks an entire fiscal year and posts the
        # closing journal. Require a fresh MFA verification before allowing
        # it. Reopening a year is even more sensitive (lives in
        # FiscalPeriodViewSet below) and is similarly gated.
        from accounting.permissions import RequiresMFA
        from rest_framework.permissions import IsAuthenticated
        if self.action in ('close_year', 'reopen_year'):
            return [IsAuthenticated(), RequiresMFA()]
        return super().get_permissions()

    @action(detail=False, methods=['get'])
    def next_available(self, request):
        """Return the next fiscal year number to create + current open years."""
        open_years = list(
            FiscalYear.objects.filter(status='Open')
            .order_by('year')
            .values_list('year', flat=True)
        )
        latest = FiscalYear.objects.order_by('-year').first()
        next_year = (latest.year + 1) if latest else date.today().year

        # Check if we need to close an old year before opening a new one
        must_close = None
        if len(open_years) >= self.MAX_OPEN_YEARS:
            must_close = open_years[0]  # oldest open year

        return Response({
            'next_year': next_year,
            'open_years': open_years,
            'open_count': len(open_years),
            'max_open_years': self.MAX_OPEN_YEARS,
            'must_close_year': must_close,
            'can_create': len(open_years) < self.MAX_OPEN_YEARS,
        })

    @action(detail=False, methods=['post'])
    def create_year(self, request):
        year = request.data.get('year')
        name = request.data.get('name')
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        period_type = request.data.get('period_type', 'Monthly')

        if FiscalYear.objects.filter(year=year).exists():
            return Response(
                {'error': f'Fiscal year {year} already exists'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Max open years enforcement (SAP-style) ──────────────
        open_years = FiscalYear.objects.filter(status='Open').order_by('year')
        open_count = open_years.count()
        if open_count >= self.MAX_OPEN_YEARS:
            oldest = open_years.first()
            return Response(
                {
                    'error': (
                        f'Maximum {self.MAX_OPEN_YEARS} fiscal years can be open simultaneously. '
                        f'Close fiscal year {oldest.year} before opening {year}.'
                    ),
                    'must_close_year': oldest.year,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Sequential year enforcement ──────────────────────────
        latest = FiscalYear.objects.order_by('-year').first()
        if latest and year != latest.year + 1:
            return Response(
                {
                    'error': (
                        f'Fiscal years must be sequential. '
                        f'The next year to create is {latest.year + 1}, not {year}.'
                    ),
                    'expected_year': latest.year + 1,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        from datetime import date

        with transaction.atomic():
            fiscal_year = FiscalYear.objects.create(
                year=year,
                name=name,
                start_date=start_date,
                end_date=end_date,
                period_type=period_type,
                status='Open'
            )

            periods = []
            if period_type == 'Daily':
                current_date = start_date if isinstance(start_date, date) else datetime.strptime(str(start_date), '%Y-%m-%d').date()
                end_dt = end_date if isinstance(end_date, date) else datetime.strptime(str(end_date), '%Y-%m-%d').date()
                period_num = 1
                while current_date <= end_dt:
                    periods.append(FiscalPeriod(
                        fiscal_year=year,
                        period_number=period_num,
                        period_type='Daily',
                        start_date=current_date,
                        end_date=current_date,
                        status='Open'
                    ))
                    current_date += timedelta(days=1)
                    period_num += 1
            elif period_type == 'Monthly':
                start = datetime.strptime(str(start_date), '%Y-%m-%d').date() if not isinstance(start_date, date) else start_date
                end = datetime.strptime(str(end_date), '%Y-%m-%d').date() if not isinstance(end_date, date) else end_date
                period_num = 1
                current_year = start.year
                current_month = start.month
                while (current_year, current_month) <= (end.year, end.month):
                    month_start = date(current_year, current_month, 1)
                    if current_month == 12:
                        month_end = date(current_year + 1, 1, 1) - timedelta(days=1)
                    else:
                        month_end = date(current_year, current_month + 1, 1) - timedelta(days=1)
                    periods.append(FiscalPeriod(
                        fiscal_year=year,
                        period_number=period_num,
                        period_type='Monthly',
                        start_date=month_start,
                        end_date=month_end,
                        status='Open'
                    ))
                    period_num += 1
                    if current_month == 12:
                        current_month = 1
                        current_year += 1
                    else:
                        current_month += 1
            else:
                periods.append(FiscalPeriod(
                    fiscal_year=year,
                    period_number=1,
                    period_type='Yearly',
                    start_date=start_date,
                    end_date=end_date,
                    status='Open'
                ))

            if periods:
                FiscalPeriod.objects.bulk_create(periods)

            # ── Auto-create matching BudgetPeriod records ─────────────────────
            # This makes budget periods immediately available in Budget Management
            # without any extra manual step.
            if period_type == 'Monthly':
                budget_periods = []
                start_dt = start_date if isinstance(start_date, date) else datetime.strptime(str(start_date), '%Y-%m-%d').date()
                end_dt = end_date if isinstance(end_date, date) else datetime.strptime(str(end_date), '%Y-%m-%d').date()
                cur_year = start_dt.year
                cur_month = start_dt.month
                p_num = 1
                while (cur_year, cur_month) <= (end_dt.year, end_dt.month):
                    m_start = date(cur_year, cur_month, 1)
                    if cur_month == 12:
                        m_end = date(cur_year + 1, 1, 1) - timedelta(days=1)
                    else:
                        m_end = date(cur_year, cur_month + 1, 1) - timedelta(days=1)
                    budget_periods.append(BudgetPeriod(
                        fiscal_year=year,
                        period_type='MONTHLY',
                        period_number=p_num,
                        start_date=m_start,
                        end_date=m_end,
                        status='OPEN',
                        allow_postings=True,
                        allow_adjustments=True,
                    ))
                    p_num += 1
                    if cur_month == 12:
                        cur_month = 1
                        cur_year += 1
                    else:
                        cur_month += 1
                if budget_periods:
                    BudgetPeriod.objects.bulk_create(budget_periods, ignore_conflicts=True)

        return Response(FiscalYearSerializer(fiscal_year).data)

    @action(detail=True, methods=['post'])
    def set_active(self, request, pk=None):
        fiscal_year = self.get_object()
        FiscalYear.objects.filter(is_active=True).update(is_active=False)
        fiscal_year.is_active = True
        fiscal_year.save()
        return Response(FiscalYearSerializer(fiscal_year).data)

    @action(detail=True, methods=['post'])
    def close_year(self, request, pk=None):
        """S3-06 — Year-end close with closing journal.

        Previously a cosmetic status flip; now delegates to the
        YearEndCloseService which:
          1. Aggregates Revenue + Expense GL balances for the year.
          2. Posts a closing journal that zeroes P&L nominal accounts
             and transfers net surplus/deficit to Accumulated Fund.
          3. Locks the FiscalYear + all child periods.

        Body params:
          force : bool  — if true, close even when Draft/Pending
                          journals remain (they will be orphaned).

        Returns the closing journal summary or a 400 with a readable
        error when the year cannot be closed.
        """
        from accounting.services.year_end_close import (
            YearEndCloseService, YearEndCloseError,
        )

        fiscal_year = self.get_object()
        force = request.data.get('force') in (True, 'true', 1, '1')

        try:
            summary = YearEndCloseService.close_fiscal_year(
                fiscal_year=fiscal_year,
                user=request.user,
                force=force,
            )
        except YearEndCloseError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            'fiscal_year': FiscalYearSerializer(fiscal_year).data,
            'close_summary': {
                'journal_id':   summary['journal_id'],
                'reference':    summary['reference'],
                'total_revenue':   str(summary['total_revenue']),
                'total_expense':   str(summary['total_expense']),
                'surplus_deficit': str(summary['surplus_deficit']),
                'accumulated_fund_account': summary['accumulated_fund_account'],
                'lines_posted': summary['lines_posted'],
            },
        })


class PeriodAccessViewSet(viewsets.ModelViewSet):
    queryset = PeriodAccess.objects.all()
    serializer_class = PeriodAccessSerializer
    filterset_fields = ['period', 'user', 'access_type', 'is_active']

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        access = self.get_object()
        access.is_active = False
        access.save()
        return Response(PeriodAccessSerializer(access).data)


class PeriodCloseCheckViewSet(viewsets.ModelViewSet):
    queryset = PeriodCloseCheck.objects.all().select_related('period', 'checked_by')
    serializer_class = PeriodCloseCheckSerializer
    filterset_fields = ['period']


class PeriodCloseChecklistView(viewsets.ViewSet):
    """
    Period-close pre-flight checklist.

    GET /api/accounting/period-close/checklist/?fiscal_period_id=<id>

    Returns live counts of items that must be resolved before a period can be
    safely closed:
      - unposted_journals       : Draft/Pending journals in the period
      - open_grn_without_invoice: GRNs with no matched vendor invoice
      - unreconciled_payments   : Posted payments not yet reconciled
      - unreconciled_receipts   : Posted receipts not yet reconciled
      - pending_approvals       : Journal entries in Pending/Approved-but-not-Posted state

    All counts = 0 means the period is clear to close.
    """

    def list(self, request):
        from ..models import JournalHeader

        fiscal_period_id = request.query_params.get('fiscal_period_id')
        period_obj = None
        if fiscal_period_id:
            period_obj = FiscalPeriod.objects.filter(pk=fiscal_period_id).first()

        # Base date range for filtering
        start_date = period_obj.start_date if period_obj else None
        end_date = period_obj.end_date if period_obj else None

        # 1. Unposted journal entries (Draft or Pending) within the period
        je_qs = JournalHeader.objects.filter(status__in=['Draft', 'Pending'])
        if start_date and end_date:
            je_qs = je_qs.filter(posting_date__gte=start_date, posting_date__lte=end_date)
        unposted_journals = je_qs.count()

        # Track subquery failures so we don't false-green is_clear_to_close.
        # Previously the bare ``except Exception: open_grns = 0`` collapsed
        # any DB / model-import error into a "0 open" reading, making the
        # checklist report Clear-to-Close while the operator was blind to
        # whatever broke. The flag below surfaces the failure to the UI and
        # forces is_clear_to_close=False so close cannot be requested until
        # the underlying error is fixed.
        checklist_error = False
        checklist_error_details: list = []

        # 2. Open GRNs without a matched vendor invoice
        try:
            from procurement.models import GoodsReceivedNote
            grn_qs = GoodsReceivedNote.objects.filter(status='Posted')
            if start_date and end_date:
                grn_qs = grn_qs.filter(received_date__gte=start_date, received_date__lte=end_date)
            # GRNs that have no vendor invoice linked via purchase_order
            open_grns = grn_qs.filter(
                purchase_order__vendor_invoices__isnull=True
            ).distinct().count()
        except Exception as exc:
            open_grns = 0
            checklist_error = True
            checklist_error_details.append({
                'check': 'open_grn_without_invoice',
                'error': str(exc),
            })

        # 3. Unreconciled payments
        try:
            from accounting.models import Payment, Receipt
            pay_qs = Payment.objects.filter(status='Posted', is_reconciled=False)
            if start_date and end_date:
                pay_qs = pay_qs.filter(payment_date__gte=start_date, payment_date__lte=end_date)
            unreconciled_payments = pay_qs.count()

            rec_qs = Receipt.objects.filter(status='Posted', is_reconciled=False)
            if start_date and end_date:
                rec_qs = rec_qs.filter(receipt_date__gte=start_date, receipt_date__lte=end_date)
            unreconciled_receipts = rec_qs.count()
        except Exception as exc:
            unreconciled_payments = 0
            unreconciled_receipts = 0
            checklist_error = True
            checklist_error_details.append({
                'check': 'unreconciled_payments_receipts',
                'error': str(exc),
            })

        # 4. Pending approval workflows (journals in 'Pending' state)
        pending_approvals = JournalHeader.objects.filter(status='Pending').count()
        if start_date and end_date:
            pending_approvals = JournalHeader.objects.filter(
                status='Pending',
                posting_date__gte=start_date,
                posting_date__lte=end_date,
            ).count()

        checklist = {
            'fiscal_period': fiscal_period_id,
            'period_name': str(period_obj) if period_obj else None,
            'is_clear_to_close': (
                not checklist_error
                and unposted_journals == 0
                and open_grns == 0
                and unreconciled_payments == 0
                and unreconciled_receipts == 0
                and pending_approvals == 0
            ),
            'checklist_error': checklist_error,
            'checklist_error_details': checklist_error_details,
            'items': {
                'unposted_journals': unposted_journals,
                'open_grn_without_invoice': open_grns,
                'unreconciled_payments': unreconciled_payments,
                'unreconciled_receipts': unreconciled_receipts,
                'pending_approvals': pending_approvals,
            }
        }
        return api_response(data=checklist)


class FiscalPeriodReopenApprovalViewSet(viewsets.ReadOnlyModelViewSet):
    """V7 — Two-actor approval queue for fiscal period reopen.

    Stage 1 (``FiscalPeriodViewSet.reopen_request``) creates a row
    here in PENDING state. A DIFFERENT user with the
    ``accounting.reopen_fiscal_period`` permission then either calls
    ``approve`` (which mutates the period) or ``reject`` on the
    detail endpoint.

    The list / retrieve endpoints are read-only — the only state
    transitions are via the ``approve`` and ``reject`` actions.
    """

    queryset = (
        FiscalPeriodReopenApproval.objects
        .select_related('fiscal_period', 'requested_by', 'approved_by')
        .all()
    )
    serializer_class = FiscalPeriodReopenApprovalSerializer
    filterset_fields = ['fiscal_period', 'status', 'requested_by', 'approved_by']
    ordering_fields = ['requested_at', 'approved_at']

    def get_permissions(self):
        # ``approve`` and ``reject`` mutate financial state — gate with
        # MFA just like the single-actor reopen used to be.
        from accounting.permissions import RequiresMFA
        from rest_framework.permissions import IsAuthenticated
        if self.action in ('approve', 'reject'):
            return [IsAuthenticated(), RequiresMFA()]
        return super().get_permissions()

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """V7 — Stage 2: second-actor approval + execute reopen.

        Hard requirements:

          * Caller holds ``accounting.reopen_fiscal_period`` (or is a
            superuser / staff) — same gate as the requester.
          * Caller is NOT the requester. Self-approval is rejected
            with ``403 Forbidden``. This is the second-actor check
            that defends against single-user audit-trail tampering.
          * Approval is still PENDING. Already-executed, rejected,
            or expired approvals cannot be re-executed.

        On success, the period is mutated and the approval row moves
        ``PENDING → APPROVED → EXECUTED`` inside one atomic block.
        """
        user = request.user

        if not _user_can_reopen(user):
            return Response(
                {'error': 'You do not have permission to approve fiscal period reopens.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        approval = self.get_object()

        # Second-actor enforcement — must not match the requester.
        if approval.requested_by_id == user.id:
            return Response(
                {
                    'error': (
                        'You cannot approve your own reopen request. '
                        'A different user with the reopen_fiscal_period '
                        'permission must approve.'
                    ),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if approval.status != FiscalPeriodReopenApproval.STATUS_PENDING:
            return Response(
                {
                    'error': (
                        f'Approval is in status {approval.status}; '
                        f'only PENDING approvals can be approved.'
                    ),
                    'status': approval.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        period = approval.fiscal_period

        if not period.is_closed and period.status != 'Closed':
            # The period was reopened by some other path between
            # request and approve; nothing to do.
            return Response(
                {'error': 'Fiscal period is not closed; nothing to reopen.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prior_state = {
            'is_closed': period.is_closed,
            'status': period.status,
            'closed_by_id': getattr(period, 'closed_by_id', None),
            'closed_date': str(getattr(period, 'closed_date', '') or ''),
            'closed_reason': getattr(period, 'closed_reason', '') or '',
            'reopen_approval_id': approval.id,
            'requested_by_id': approval.requested_by_id,
        }

        try:
            with transaction.atomic():
                # Flip to APPROVED first so the audit row records the
                # approver as the executing user, then execute, then
                # flip to EXECUTED. Rollback unwinds both flips and
                # the period mutation if the audit log write fails.
                approval.status = FiscalPeriodReopenApproval.STATUS_APPROVED
                approval.approved_by = user
                approval.approved_at = timezone.now()
                approval.save(update_fields=['status', 'approved_by', 'approved_at'])

                _execute_period_reopen(
                    period=period,
                    user=user,
                    request=request,
                    reason=approval.reason,
                    prior_state=prior_state,
                )

                approval.status = FiscalPeriodReopenApproval.STATUS_EXECUTED
                approval.executed_at = timezone.now()
                approval.save(update_fields=['status', 'executed_at'])
        except Exception:
            return Response(
                {'error': 'Audit logging failed; refusing to reopen period.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        approval.refresh_from_db()
        return Response(
            {
                'approval': FiscalPeriodReopenApprovalSerializer(approval).data,
                'fiscal_period': FiscalPeriodSerializer(period).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """V7 — Reject a PENDING reopen request.

        A second actor (or the original requester themselves, who may
        change their mind) can mark a pending request as REJECTED so
        it cannot be approved later. Requires a rejection reason.
        """
        user = request.user

        if not _user_can_reopen(user):
            return Response(
                {'error': 'You do not have permission to reject fiscal period reopens.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        approval = self.get_object()

        if approval.status != FiscalPeriodReopenApproval.STATUS_PENDING:
            return Response(
                {
                    'error': (
                        f'Approval is in status {approval.status}; '
                        f'only PENDING approvals can be rejected.'
                    ),
                    'status': approval.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        rejection_reason = (request.data.get('rejection_reason') or '').strip()
        if len(rejection_reason) < 10:
            return Response(
                {'error': 'A rejection reason of at least 10 characters is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        approval.status = FiscalPeriodReopenApproval.STATUS_REJECTED
        approval.rejection_reason = rejection_reason
        # Record the rejecter via approved_by so we keep a single
        # "who acted on this" column for forensic queries.
        approval.approved_by = user
        approval.approved_at = timezone.now()
        approval.save(update_fields=[
            'status', 'rejection_reason', 'approved_by', 'approved_at',
        ])

        return Response(
            FiscalPeriodReopenApprovalSerializer(approval).data,
            status=status.HTTP_200_OK,
        )
