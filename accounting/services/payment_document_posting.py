"""Post a Payment Document as one balanced journal (see the design spec)."""
from __future__ import annotations

from decimal import Decimal


class PaymentDocumentError(Exception):
    """A payment document could not be posted for a domain reason."""


def compute_net(lines) -> Decimal:
    """Net cash out = Σ debits − Σ credits across the document's lines."""
    total_debit = sum((ln.debit or Decimal("0.00")) for ln in lines)
    total_credit = sum((ln.credit or Decimal("0.00")) for ln in lines)
    return Decimal(total_debit) - Decimal(total_credit)
