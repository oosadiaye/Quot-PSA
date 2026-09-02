"""Shared field validators for procurement master data."""
from __future__ import annotations

from django.core.exceptions import ValidationError

NUBAN_LENGTH = 10


def validate_nuban(value: str) -> None:
    """Nigerian NUBAN account numbers are exactly 10 digits.

    Blank is allowed: bank details remain optional on Vendor so existing
    records stay editable. Completeness is enforced at the payment-batch
    boundary, which is where a missing value would otherwise freeze into
    an immutable printed line.
    """
    if not value:
        return
    if not (value.isdigit() and len(value) == NUBAN_LENGTH):
        raise ValidationError(
            f'Account number must be exactly {NUBAN_LENGTH} digits (NUBAN). '
            f'Got {value!r}.'
        )
