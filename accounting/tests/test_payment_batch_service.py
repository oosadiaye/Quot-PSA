"""Payment batching — DB integration tests."""
from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.mark.integration
class TestBankLetterSettingsSingleton:

    def test_get_singleton_creates_row_with_defaults(self, db):
        from accounting.models import BankLetterSettings
        s = BankLetterSettings.get_singleton()
        assert s.pk == 1
        assert s.ministry_name == 'Ministry of Finance'
        assert s.office_name == 'Office of the Accountant General'

    def test_get_singleton_is_idempotent(self, db):
        from accounting.models import BankLetterSettings
        a = BankLetterSettings.get_singleton()
        a.office_address = 'Asaba'
        a.save()
        b = BankLetterSettings.get_singleton()
        assert b.pk == a.pk
        assert b.office_address == 'Asaba'
        assert BankLetterSettings.objects.count() == 1
