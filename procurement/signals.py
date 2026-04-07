"""
INT-12: Cross-module signal handlers for procurement events.
Fires after GRN posting to liquidate related PO budget encumbrances.
"""
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='procurement.GoodsReceivedNote')
def on_grn_posted(sender, instance, **kwargs):
    """When a GRN is posted, liquidate the related PO's budget encumbrances."""
    if instance.status == 'Posted':
        from accounting.models import BudgetEncumbrance
        if instance.purchase_order:
            BudgetEncumbrance.objects.filter(
                reference_number=instance.purchase_order.po_number,
                status='ACTIVE'
            ).update(status='FULLY_LIQUIDATED', liquidated_amount=models.F('amount'))
