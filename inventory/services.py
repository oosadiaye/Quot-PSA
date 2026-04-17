"""Inventory service helpers — shared logic used across procurement / GRN flows.

The main export is :func:`get_default_warehouse_for_mda`, which returns the
auto-provisioned ``Warehouse`` row that represents an MDA's physical stores.
In Quot PSE the user never picks a warehouse in the GRN screen — they pick
an MDA, and the backend transparently resolves that MDA to its dedicated
warehouse for downstream inventory tracking (``ItemBatch``, ``StockMovement``,
``ItemStock``).

This preserves the public-sector "MDA is the accountable custodian" mental
model without disrupting the existing inventory schema.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from accounting.models import MDA  # noqa: F401
    from inventory.models import Warehouse  # noqa: F401


@transaction.atomic
def get_default_warehouse_for_mda(mda) -> "Warehouse":
    """Return (creating if necessary) the default Warehouse for this MDA.

    Idempotent and race-safe: uses ``get_or_create`` on a deterministic key
    (the warehouse ``name`` derived from the MDA code) so concurrent first-
    use does not create duplicates. Wrapped in ``@transaction.atomic`` so
    the INSERT is rolled back if it races with a committed peer.

    Args:
        mda: legacy ``accounting.MDA`` instance.

    Returns:
        A persisted ``inventory.Warehouse`` — either fetched or created.

    Raises:
        ValueError: if ``mda`` is None or has no ``code``.
    """
    from inventory.models import Warehouse

    if mda is None:
        raise ValueError("MDA is required to resolve a default warehouse.")
    if not getattr(mda, "code", None):
        raise ValueError(f"MDA {mda!r} has no code — cannot build warehouse key.")

    # Deterministic name = "<MDA CODE> - Stores" so the same MDA always
    # resolves to the same Warehouse row regardless of capitalisation
    # drift on mda.name.
    canonical_name = f"{mda.code} - Stores"
    warehouse, _created = Warehouse.objects.get_or_create(
        name=canonical_name,
        defaults={
            "location": mda.name or canonical_name,
            "is_active": True,
            "is_central": False,
        },
    )
    return warehouse
