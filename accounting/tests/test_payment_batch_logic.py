"""Payment batching — fast unit tests (no DB, no I/O)."""
from __future__ import annotations

from datetime import date

import pytest


@pytest.mark.unit
class TestBatchNumberFormat:

    def test_formats_with_year_and_zero_padded_sequence(self):
        from accounting.services.payment_batch import format_batch_number
        assert format_batch_number(2026, 1) == 'PB/2026/0001'

    def test_pads_to_four_digits(self):
        from accounting.services.payment_batch import format_batch_number
        assert format_batch_number(2026, 42) == 'PB/2026/0042'

    def test_does_not_truncate_beyond_four_digits(self):
        from accounting.services.payment_batch import format_batch_number
        assert format_batch_number(2026, 12345) == 'PB/2026/12345'

    def test_rejects_non_positive_sequence(self):
        from accounting.services.payment_batch import format_batch_number
        with pytest.raises(ValueError):
            format_batch_number(2026, 0)
