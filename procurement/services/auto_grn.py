"""Automatic goods receipt for approved Purchase Orders.

A PO resolves its GRN mode from its own ``grn_mode`` and falls back to
``InventorySettings.default_grn_mode``. In AUTO mode, approving the PO books a posted
GRN for every line's outstanding quantity, exactly as a storekeeper posting it by hand.
"""
import logging
from decimal import Decimal

from django.db import transaction

logger = logging.getLogger(__name__)

AUTO = 'AUTO'
RECEIVED_BY = 'System (automatic GRN)'


def resolve_grn_mode(po) -> str:
    """'AUTO' or 'MANUAL' for this PO: its own setting, else the tenant default."""
    if po.grn_mode in ('AUTO', 'MANUAL'):
        return po.grn_mode
    from inventory.models import InventorySettings
    return InventorySettings.load().default_grn_mode


def auto_receive_po(po):
    """Create and post a GRN for the PO's outstanding quantities; None if nothing to receive.

    Idempotent: a PO that already has a live GRN is left alone, so a re-approval or a
    manual GRN is never doubled up.
    """
    from procurement.models import GoodsReceivedNote, GoodsReceivedNoteLine
    from django.utils import timezone

    if po.goodsreceivednote_set.exclude(status='Cancelled').exists():
        return None
    outstanding = [(line, line.quantity - line.quantity_received) for line in po.lines.all()]
    outstanding = [(line, qty) for line, qty in outstanding if qty > Decimal('0')]
    if not outstanding:
        return None

    with transaction.atomic():
        grn = GoodsReceivedNote.objects.create(
            purchase_order=po, received_date=timezone.localdate(), received_by=RECEIVED_BY,
            notes=f'Booked automatically when {po.po_number} was approved.',
        )
        for line, qty in outstanding:
            GoodsReceivedNoteLine.objects.create(
                grn=grn, po_line=line, quantity_received=qty, received_quantity_status='Full',
            )
        grn.status = 'Posted'
        grn.save()
    return grn


def auto_receive_if_enabled(po):
    """Approval hook. A failed auto-receipt must not undo the approval: log it and leave the PO manual."""
    try:
        if resolve_grn_mode(po) != AUTO:
            return None
        return auto_receive_po(po)
    except Exception as exc:
        logger.exception('Automatic GRN failed for PO %s; receive it manually.', po.po_number)
        po.auto_grn_error = str(getattr(exc, 'message', None) or exc)
        return None
