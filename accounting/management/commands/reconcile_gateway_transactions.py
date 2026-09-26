"""
Reconcile gateway transactions stuck in SENT — a missed webhook.

A dropped or delayed PSP callback would otherwise leave a payout or
collection forever "sent, awaiting settlement". This command finds those,
polls the gateway for the real outcome, and applies the same settlement
the webhook would have — so the ledger self-heals rather than depending on
every callback arriving.

    manage.py reconcile_gateway_transactions --older-than-minutes 30
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import schema_context

from superadmin.gateway_connectors import ConnectorError, get_connector
from superadmin.gateway_connectors.base import WebhookEvent
from superadmin.gateway_models import GatewayService, GatewayTransaction


class Command(BaseCommand):
    help = "Poll the gateway for transactions stuck in SENT and settle them."

    def add_arguments(self, parser):
        parser.add_argument("--older-than-minutes", type=int, default=30)
        parser.add_argument("--limit", type=int, default=200)

    def handle(self, *args, **opts):
        threshold = timezone.now() - timedelta(minutes=opts["older_than_minutes"])
        stuck = (
            GatewayTransaction.objects
            .select_related("provider", "tenant")
            .filter(status=GatewayTransaction.Status.SENT, created_at__lt=threshold)
            .order_by("created_at")[: opts["limit"]]
        )

        settled = failed = unreachable = 0
        for txn in stuck:
            try:
                connector = get_connector(txn.provider)
                event = connector.query_status(txn.provider, txn.gateway_reference)
            except ConnectorError as exc:
                unreachable += 1
                self.stderr.write(f"  {txn.gateway_reference}: status query failed — {exc}")
                continue

            success = event.outcome == WebhookEvent.SUCCESS
            with schema_context(txn.tenant.schema_name):
                if txn.direction == GatewayService.COLLECTION:
                    from accounting.services.gateway_collection import settle_collection
                    settle_collection(txn, success=success)
                else:
                    from accounting.services.gateway_disbursement import (
                        settle_gateway_disbursement,
                    )
                    settle_gateway_disbursement(txn, success=success)
            if success:
                settled += 1
            else:
                failed += 1

        self.stdout.write(self.style.SUCCESS(
            f"Reconciled {settled + failed}: {settled} settled, {failed} failed/reversed, "
            f"{unreachable} unreachable."
        ))
