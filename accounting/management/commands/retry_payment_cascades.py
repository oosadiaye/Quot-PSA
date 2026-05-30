"""
Background retry for transient payment-cascade failures (H2 — WS6).

Most ``PaymentCascadeFailure`` rows come from PERMANENT errors —
Segregation-of-Duties rejection (payer is a prior actor on the IPC),
schema drift, or an upstream contract-state mismatch. These do NOT
benefit from automatic retry; they require an operator to fix the
upstream condition and then manually re-trigger the cascade.

A small minority come from TRANSIENT errors — a network blip while
the IPC service was warming up, a temporary DB connection issue, a
brief lock contention. For those, a periodic retry is genuinely
useful.

This command is the retry surface. It:

1. Selects unresolved ``PaymentCascadeFailure`` rows whose
   ``error_class`` matches a small whitelist of known-transient
   exception types.
2. Retries ``IPCService.mark_paid`` on the linked IPC.
3. If the retry succeeds, marks the failure resolved with an
   auto-generated note crediting the retry.
4. If the retry fails again, leaves the row pending and increments
   an attempt counter in ``error_context['retry_count']``.

## Why a management command and not a Celery task

The project keeps Celery commented out in ``requirements.txt`` and
relies on the host OS scheduler (Windows Task Scheduler / cron) for
periodic work. This is a deliberate operational choice — see
``contracts/tasks.py`` for the long-form rationale. A management
command runs identically under any scheduler, so this surface is
portable across deployments.

## Scheduling

``accounting`` is a TENANT_APP, so this command must be run inside a
tenant schema context (the model does not exist in the public
schema). Invoke via django-tenants' ``tenant_command`` wrapper:

    # All tenants (hourly cron):
    python manage.py all_tenants_command retry_payment_cascades --max-attempts 5

    # Specific tenant (testing or targeted retry):
    python manage.py tenant_command retry_payment_cascades --schema=acme

Each row is retried up to ``--max-attempts`` times before it is left
for manual operator resolution.

## When to switch this to a Celery task

If transient failure volume grows to the point that hourly retries
are insufficient (i.e., money sits in limbo for >1 hour with material
business impact), add Celery and convert this command body into a
``@shared_task`` with ``acks_late=True`` and a 60-second retry
interval. The conversion is mechanical because the retry logic itself
is already idempotent and side-effect-safe.
"""
from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


logger = logging.getLogger(__name__)


# Exception class names that have historically been transient.
# Operators / SREs can extend this list via settings if their
# environment surfaces additional transient classes; defaulting to a
# tight list is the safer behaviour (failing to retry a permanent
# error costs less than retrying one repeatedly).
TRANSIENT_ERROR_CLASSES = frozenset({
    'OperationalError',          # django.db.utils.OperationalError
    'InterfaceError',            # psycopg2.InterfaceError
    'ConnectionError',
    'TimeoutError',
    'DatabaseError',             # only sometimes transient — bounded by attempts
})


class Command(BaseCommand):
    help = 'Retry transient PaymentCascadeFailure rows by re-running IPCService.mark_paid'

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            '--max-attempts',
            type=int,
            default=5,
            help='Maximum retry attempts per row before giving up '
                 '(default: 5).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be retried without actually retrying.',
        )

    def handle(self, *args, max_attempts: int, dry_run: bool, **options) -> None:
        from accounting.models import PaymentCascadeFailure
        try:
            from contracts.services.ipc_service import IPCService
        except ImportError:
            self.stderr.write(self.style.ERROR(
                'IPCService import failed; cannot retry. Verify the '
                'contracts app is installed.'
            ))
            return

        # Select transient-class rows that haven't exceeded the
        # retry budget.
        candidates = PaymentCascadeFailure.objects.filter(
            resolved=False,
            error_class__in=TRANSIENT_ERROR_CLASSES,
            ipc__isnull=False,
        ).select_related('payment', 'ipc')

        self.stdout.write(
            f'Selected {candidates.count()} candidate row(s) for retry. '
            f'Max attempts per row: {max_attempts}.'
        )

        retried_ok = 0
        retried_still_failing = 0
        skipped_over_budget = 0

        for failure in candidates:
            attempt = (
                failure.error_context.get('retry_count', 0)
                if isinstance(failure.error_context, dict)
                else 0
            )
            if attempt >= max_attempts:
                skipped_over_budget += 1
                continue

            if dry_run:
                self.stdout.write(
                    f'  DRY: would retry failure={failure.pk} '
                    f'(payment={failure.payment_id}, '
                    f'ipc={failure.ipc_id}, attempt={attempt + 1})'
                )
                continue

            # Each retry runs in its own atomic block so a fresh
            # failure of one row does not roll back the resolution of
            # another row processed earlier in the same command.
            try:
                with transaction.atomic():
                    IPCService.mark_paid(
                        ipc=failure.ipc,
                        payment_voucher=failure.payment.payment_voucher,
                        user=failure.resolved_by or failure.payment.created_by,
                    )

                # Retry succeeded — close the row.
                failure.mark_resolved(
                    user=None,  # system retry, not a human actor
                    note=(
                        f'Auto-resolved via retry_payment_cascades on '
                        f'{timezone.now():%Y-%m-%d %H:%M}Z '
                        f'(attempt {attempt + 1}).'
                    ),
                )
                retried_ok += 1
                self.stdout.write(self.style.SUCCESS(
                    f'  OK : failure={failure.pk} retried successfully '
                    f'(attempt {attempt + 1})'
                ))

            except Exception as exc:  # noqa: BLE001
                # Retry failed again. Increment counter; leave row pending.
                ctx = dict(failure.error_context) if isinstance(
                    failure.error_context, dict
                ) else {}
                ctx['retry_count'] = attempt + 1
                ctx['last_retry_at'] = timezone.now().isoformat()
                ctx['last_retry_error'] = str(exc)
                failure.error_context = ctx
                failure.save(update_fields=['error_context'])
                retried_still_failing += 1
                logger.warning(
                    'Retry %d/%d failed for cascade failure %s: %s',
                    attempt + 1, max_attempts, failure.pk, exc,
                )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Done. resolved={retried_ok} '
            f'still_failing={retried_still_failing} '
            f'over_budget_skipped={skipped_over_budget}'
        ))
