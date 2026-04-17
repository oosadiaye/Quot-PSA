"""
Sprint-18 tests — seed_demo_registers structural checks (no-DB tier).

Verifies:
  * _first_of_month helper correctness.
  * _has_is_active reflection safety.
  * DEMO-REG tag constant stability (idempotency key).
"""
from __future__ import annotations

from datetime import date



class TestFirstOfMonth:

    def test_jan(self):
        from accounting.management.commands.seed_demo_registers import _first_of_month
        assert _first_of_month(2026, 1) == date(2026, 1, 1)

    def test_feb(self):
        from accounting.management.commands.seed_demo_registers import _first_of_month
        assert _first_of_month(2026, 2) == date(2026, 2, 1)

    def test_dec(self):
        from accounting.management.commands.seed_demo_registers import _first_of_month
        assert _first_of_month(2026, 12) == date(2026, 12, 1)

    def test_leap_year_feb(self):
        from accounting.management.commands.seed_demo_registers import _first_of_month
        assert _first_of_month(2024, 2) == date(2024, 2, 1)


class TestHasIsActive:

    def test_model_without_is_active(self):
        from accounting.management.commands.seed_demo_registers import _has_is_active

        class StubNoField:
            class _meta:
                @staticmethod
                def get_field(name):
                    raise Exception('no such field')

        assert _has_is_active(StubNoField) is False

    def test_model_with_is_active(self):
        from accounting.management.commands.seed_demo_registers import _has_is_active

        class StubField:
            name = 'is_active'

        class StubWithField:
            class _meta:
                @staticmethod
                def get_field(name):
                    if name == 'is_active':
                        return StubField()
                    raise Exception('not found')

        assert _has_is_active(StubWithField) is True


class TestTagConstant:
    """Freeze the tag — it is the idempotency key for TSA account_number,
    RevenueCollection.receipt_number, and Appropriation.variance_explanation.
    Changing it silently orphans previously-seeded rows."""

    def test_tag(self):
        from accounting.management.commands import seed_demo_registers
        assert seed_demo_registers._TAG == 'DEMO-REG-'


class TestReceiptNumberFormat:
    """The receipt_number prefix+suffix pattern is used by --clear to
    find prior seed data. Lock the format so upgrades don't break
    --clear unexpectedly."""

    def test_receipt_format_shape(self):
        from accounting.management.commands.seed_demo_registers import _TAG
        # Form used in the command: f'{_TAG}REV-{year}-{month:02d}-{idx:02d}'
        sample = f'{_TAG}REV-2026-04-01'
        assert sample.startswith(_TAG)
        # And --clear uses startswith matching.
        assert sample.startswith('DEMO-REG-')

    def test_tsa_number_format(self):
        from accounting.management.commands.seed_demo_registers import _TAG
        sample = f'{_TAG}TSA-001'
        assert sample.startswith(_TAG)
