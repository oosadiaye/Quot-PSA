"""Inventory signals for maintaining data integrity.

- StockMovement post_save: auto-update ItemStock quantities and Item totals
- StockMovement post_save: auto-decrement ItemBatch.remaining_quantity on OUT
- Reservation post_save/post_delete: sync ItemStock.reserved_quantity
"""

from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, F
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver(post_save, sender='inventory.StockMovement')
def update_stock_on_movement(sender, instance, created, **kwargs):
    """Auto-update ItemStock and Item totals when a StockMovement is created."""
    if not created:
        return
    # Callers (e.g. reconciliation adjust) may set _skip_stock_update = True on the
    # instance to indicate that stock was already updated explicitly and the signal
    # should not apply the qty delta again (prevents double-counting).
    if getattr(instance, '_skip_stock_update', False):
        # Still recalculate item-level aggregates so totals stay consistent.
        instance.item.recalculate_stock_values()
        return

    from inventory.models import ItemStock

    movement = instance

    with transaction.atomic():
        # Update source warehouse stock
        stock, _ = ItemStock.objects.get_or_create(
            item=movement.item,
            warehouse=movement.warehouse,
            defaults={'quantity': Decimal('0'), 'reserved_quantity': Decimal('0')},
        )

        if movement.movement_type == 'IN':
            stock.quantity = F('quantity') + movement.quantity
        elif movement.movement_type == 'OUT':
            stock.quantity = F('quantity') - movement.quantity
        elif movement.movement_type == 'ADJ':
            stock.quantity = F('quantity') + movement.quantity  # ADJ can be positive or negative via sign
        elif movement.movement_type == 'TRF':
            stock.quantity = F('quantity') - movement.quantity
        stock.save(update_fields=['quantity'])
        stock.refresh_from_db()

        # For transfers, credit the destination warehouse
        if movement.movement_type == 'TRF' and movement.to_warehouse:
            dest_stock, _ = ItemStock.objects.get_or_create(
                item=movement.item,
                warehouse=movement.to_warehouse,
                defaults={'quantity': Decimal('0'), 'reserved_quantity': Decimal('0')},
            )
            dest_stock.quantity = F('quantity') + movement.quantity
            dest_stock.save(update_fields=['quantity'])
            dest_stock.refresh_from_db()

        # Recalculate Item-level totals
        movement.item.recalculate_stock_values()


@receiver(post_save, sender='inventory.StockMovement')
def decrement_batch_on_out(sender, instance, created, **kwargs):
    """Auto-decrement ItemBatch.remaining_quantity on OUT movements."""
    if not created:
        return
    movement = instance
    if movement.movement_type == 'OUT' and movement.batch:
        with transaction.atomic():
            batch = movement.batch
            # Use F() expression to avoid race condition, then clamp at DB level
            batch.remaining_quantity = F('remaining_quantity') - movement.quantity
            batch.save(update_fields=['remaining_quantity'])
            batch.refresh_from_db()
            # Clamp to zero if it went negative
            if batch.remaining_quantity < Decimal('0'):
                batch.remaining_quantity = Decimal('0')
                batch.save(update_fields=['remaining_quantity'])


@receiver(post_save, sender='inventory.Reservation')
@receiver(post_delete, sender='inventory.Reservation')
def sync_reserved_quantity(sender, instance, **kwargs):
    """Sync ItemStock.reserved_quantity from Reservation aggregates."""
    from inventory.models import ItemStock

    reservation = instance
    with transaction.atomic():
        stock = ItemStock.objects.filter(
            item=reservation.item,
            warehouse=reservation.warehouse,
        ).first()
        if stock:
            total_reserved = reservation.item.reservations.filter(
                warehouse=reservation.warehouse,
                status__in=['Pending', 'Partially_Fulfilled'],
            ).aggregate(
                total=Sum('quantity')
            )['total'] or Decimal('0')
            stock.reserved_quantity = total_reserved
            stock.save(update_fields=['reserved_quantity'])
