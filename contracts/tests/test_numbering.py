"""
Tests for contracts.services.numbering — document number format.

These are light integration tests: numbering uses
``accounting.TransactionSequence.get_next`` which is DB-backed, so the
tests run under the pytest_schema tenant.  Covered by the shared
``accounting.tests.conftest`` tenant plumbing.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


# ── Pure format test (no DB needed) ───────────────────────────────────

def test_ipc_number_format_pattern():
    """IPC number format: <contract_number>/IPC/<NN>."""
    # We emulate the ``ipc_count`` branch without hitting the DB by
    # building a SimpleNamespace that mimics contract.ipcs.count().
    contract = SimpleNamespace(
        contract_number="DSG/WORKS/2026/042",
        ipcs=SimpleNamespace(count=lambda: 2),  # → next is 03
    )
    from contracts.services.numbering import next_ipc_number
    got = next_ipc_number(contract)
    assert got == "DSG/WORKS/2026/042/IPC/03"


def test_measurement_book_number_format():
    from contracts.services.numbering import next_measurement_book_number
    contract = SimpleNamespace(
        contract_number="DSG/WORKS/2026/001",
        measurement_books=SimpleNamespace(count=lambda: 0),
    )
    assert next_measurement_book_number(contract) == "DSG/WORKS/2026/001/MB/001"


def test_variation_number_is_sequential_int():
    from contracts.services.numbering import next_variation_number
    contract = SimpleNamespace(
        variations=SimpleNamespace(count=lambda: 3),
    )
    assert next_variation_number(contract) == 4
