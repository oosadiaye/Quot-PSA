"""
Gateway collection — IGR money-in via a collection gateway (Xpresspay).

The money-in sibling of :mod:`accounting.services.gateway_disbursement`.
Because a confirmed collection posts through the existing
``post_revenue_collection_to_gl`` (DR Cash-in-TSA / CR Revenue), the work
here is: raise a collection reference at the PSP, and — on the confirming
webhook — materialise a ``RevenueCollection`` and post it.

The RevenueCollection's required context (revenue head, NCoA code, TSA
account, payer) is captured at INITIATION, where the operator knows what
revenue is being collected, and stored on the transaction ``subject``. The
webhook then rebuilds the receipt from it rather than trying to infer it
from a callback body.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from superadmin.gateway_client import GatewayRefused
from superadmin.gateway_connectors import (
    CollectRequest,
    ConnectorError,
    get_connector,
)
from superadmin.gateway_models import GatewayService, GatewayTransaction


class GatewayCollectionError(Exception):
    """A collection could not be raised/settled for a domain reason."""


@transaction.atomic
def initiate_collection(
    *, tenant, setting, revenue_head_id, ncoa_code_id, tsa_account_id,
    amount, payer_name, payer_tin="", payer_phone="",
    collecting_mda_id=None, description="",
):
    """Raise a collection at the gateway. Returns ``(GatewayTransaction, checkout_url)``."""
    if not setting.is_usable:
        raise GatewayRefused("The selected gateway is not enabled for this tenant.")
    if not setting.provider.supports_collection:
        raise GatewayRefused("This gateway does not raise collections.")
    amount = Decimal(str(amount))
    if amount <= 0:
        raise GatewayCollectionError("Collection amount must be positive.")
    if not payer_name:
        raise GatewayCollectionError("A payer name is required.")

    from accounting.models.gl import TransactionSequence

    reference = TransactionSequence.get_next("igr_collection", prefix="IGR-")
    subject = {
        "model": "RevenueCollection",
        "revenue_head_id": revenue_head_id,
        "ncoa_code_id": ncoa_code_id,
        "tsa_account_id": tsa_account_id,
        "collecting_mda_id": collecting_mda_id,
        "payer_name": payer_name,
        "payer_tin": payer_tin,
        "payer_phone": payer_phone,
    }
    txn = GatewayTransaction.objects.create(
        tenant=tenant, provider=setting.provider,
        direction=GatewayService.COLLECTION, idempotency_key=reference,
        amount=amount, subject=subject, status=GatewayTransaction.Status.PENDING,
    )

    connector = get_connector(setting.provider)
    try:
        result = connector.initiate_collection(setting.provider, CollectRequest(
            reference=reference, amount=amount, payer_name=payer_name,
            payer_phone=payer_phone, description=description,
        ))
    except ConnectorError as exc:
        txn.status = GatewayTransaction.Status.FAILED
        txn.error_message = str(exc)[:500]
        txn.save(update_fields=["status", "error_message", "updated_at"])
        raise

    txn.gateway_reference = result.gateway_reference or reference
    txn.http_status = result.http_status
    txn.status = (
        GatewayTransaction.Status.SENT if result.accepted
        else GatewayTransaction.Status.FAILED
    )
    if not result.accepted:
        txn.error_message = result.error[:500]
    txn.save(update_fields=[
        "gateway_reference", "http_status", "status", "error_message", "updated_at",
    ])
    checkout_url = (result.raw or {}).get("checkoutUrl") or (result.raw or {}).get("checkout_url", "")
    return txn, checkout_url


@transaction.atomic
def settle_collection(txn, *, success):
    """Materialise + post the RevenueCollection on a confirmed callback.

    Idempotent on the transaction's terminal state. A failed collection
    posts nothing — no money came in.
    """
    if txn.status in (
        GatewayTransaction.Status.SUCCESS,
        GatewayTransaction.Status.REVERSED,
    ):
        return None

    if not success:
        txn.status = GatewayTransaction.Status.FAILED
        txn.settled_at = timezone.now()
        txn.save(update_fields=["status", "settled_at", "updated_at"])
        return None

    from accounting.models import RevenueCollection
    from accounting.models.gl import TransactionSequence
    from accounting.services.revenue_collection_posting import (
        post_revenue_collection_to_gl,
    )

    subj = txn.subject or {}
    collection = RevenueCollection.objects.create(
        receipt_number=TransactionSequence.get_next("revenue_receipt", prefix="OR-"),
        revenue_head_id=subj["revenue_head_id"],
        ncoa_code_id=subj["ncoa_code_id"],
        payer_name=subj.get("payer_name", ""),
        payer_tin=subj.get("payer_tin", ""),
        payer_phone=subj.get("payer_phone", ""),
        amount=txn.amount,
        payment_reference=TransactionSequence.get_next("payment_ref", prefix="PR-"),
        rrr=txn.gateway_reference,
        tsa_account_id=subj["tsa_account_id"],
        collection_date=date.today(),
        collection_channel="ONLINE",
        collecting_mda_id=subj.get("collecting_mda_id"),
        status="CONFIRMED",
    )
    post_revenue_collection_to_gl(collection)

    txn.status = GatewayTransaction.Status.SUCCESS
    txn.settled_at = timezone.now()
    txn.subject = {**subj, "revenue_collection_id": collection.pk}
    txn.save(update_fields=["status", "settled_at", "subject", "updated_at"])
    return collection
