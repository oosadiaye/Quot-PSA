"""
Sequential document numbering for contracts, IPCs, MBs, variations.

Reuses accounting.TransactionSequence (existing, already atomic under
SELECT FOR UPDATE) so numbering survives across restarts and is
contention-safe.  The sequence key is namespaced under 'contracts_*'.
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from contracts.models import Contract


def _next(sequence_key: str, prefix: str) -> str:
    """Thin wrapper around accounting.TransactionSequence.get_next."""
    from accounting.models.gl import TransactionSequence
    return TransactionSequence.get_next(sequence_key, prefix=prefix)


def next_contract_number(*, contract_type: str, fiscal_year: int) -> str:
    """
    Format: DSG/<TYPE>/<YYYY>/<NNN>
    e.g. DSG/WORKS/2026/042
    """
    key = f"contracts_contract_{contract_type}_{fiscal_year}"
    raw = _next(key, prefix="")
    # Strip any accidental prefix and re-render
    seq = raw.lstrip("-").lstrip("PV-").split("-")[-1]
    try:
        seq_int = int(seq)
    except ValueError:
        seq_int = 1
    return f"DSG/{contract_type}/{fiscal_year}/{seq_int:03d}"


def next_ipc_number(contract: "Contract") -> str:
    """
    Format: <contract_number>/IPC/<NN>  (zero-padded, unique per contract)
    """
    # Count existing (any status) to avoid gaps on re-draft
    ipc_count = contract.ipcs.count() + 1
    return f"{contract.contract_number}/IPC/{ipc_count:02d}"


def next_measurement_book_number(contract: "Contract") -> str:
    mb_count = contract.measurement_books.count() + 1
    return f"{contract.contract_number}/MB/{mb_count:03d}"


def next_variation_number(contract: "Contract") -> int:
    """Variations use an integer sequence column, not a string."""
    existing = contract.variations.count()
    return existing + 1
