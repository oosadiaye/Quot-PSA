"""revenue_admin's reaction to accounting's events (accounting never imports this module)."""
from django.db import connection
from django.dispatch import receiver

from accounting.signals.events import revenue_collected
from core.permissions import _is_module_enabled

from .services import apply_collection


def _revenue_admin_enabled() -> bool:
    """Is the module switched on for this tenant? Off (or no row) means collections post exactly as they did before the
    module existed. The public schema is never touched."""
    tenant = getattr(connection, 'tenant', None)
    if tenant is None or getattr(tenant, 'schema_name', 'public') == 'public':
        return False
    return _is_module_enabled('revenue_admin', tenant)


@receiver(revenue_collected, dispatch_uid='revenue_admin.apply_collection')
def apply_posted_collection(sender, collection, journal, **kwargs):
    """Reduce the payer's arrears and open notices by what was collected (idempotent on the receipt number)."""
    if not _revenue_admin_enabled():
        return
    apply_collection(
        receipt_number=collection.receipt_number,
        payer_tin=collection.payer_tin,
        revenue_head=collection.revenue_head,
        amount=collection.amount,
    )
