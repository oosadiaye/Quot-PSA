"""Unit tests for ``TSABalanceService.process_transfer``.

Pure-unit / SimpleTestCase tests — exercise input validation and
guard logic without needing the DB. Integration coverage of the
actual JV posting + GLBalance roll-up is exercised by the existing
contract / treasury integration tests when run against a real
Postgres test DB.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase


def _fake_tsa(
    *,
    pk: int,
    account_number: str = '0000000000',
    is_active: bool = True,
    gl_cash_account_id: int | None = 1,
    current_balance: Decimal = Decimal('100000'),
    fund_segment_id: int | None = None,
    mda=None,
):
    """Minimal stand-in for a TreasuryAccount instance.

    Carries only the fields ``process_transfer`` reads at the
    pre-DB stage. Anything that would hit the ORM is patched out.
    """
    return SimpleNamespace(
        pk=pk,
        account_number=account_number,
        is_active=is_active,
        gl_cash_account_id=gl_cash_account_id,
        gl_cash_account=SimpleNamespace(pk=gl_cash_account_id) if gl_cash_account_id else None,
        current_balance=current_balance,
        fund_segment_id=fund_segment_id,
        fund_segment=None,
        mda=mda,
    )


class TSATransferValidationTests(SimpleTestCase):
    """Guard rails fire BEFORE the DB lock — easy to test cleanly."""

    def test_zero_amount_rejected(self):
        from accounting.services.treasury_service import TSABalanceService
        with self.assertRaisesMessage(ValueError, 'amount must be greater than zero'):
            TSABalanceService.process_transfer(
                source_tsa=_fake_tsa(pk=1),
                target_tsa=_fake_tsa(pk=2),
                amount=Decimal('0'),
                actor=SimpleNamespace(username='alice'),
            )

    def test_negative_amount_rejected(self):
        from accounting.services.treasury_service import TSABalanceService
        with self.assertRaisesMessage(ValueError, 'amount must be greater than zero'):
            TSABalanceService.process_transfer(
                source_tsa=_fake_tsa(pk=1),
                target_tsa=_fake_tsa(pk=2),
                amount=Decimal('-5'),
                actor=SimpleNamespace(username='alice'),
            )

    def test_non_numeric_amount_rejected(self):
        from accounting.services.treasury_service import TSABalanceService
        with self.assertRaisesMessage(ValueError, 'amount must be a decimal value'):
            TSABalanceService.process_transfer(
                source_tsa=_fake_tsa(pk=1),
                target_tsa=_fake_tsa(pk=2),
                amount='not-a-number',
                actor=SimpleNamespace(username='alice'),
            )

    def test_same_source_and_target_rejected(self):
        from accounting.services.treasury_service import TSABalanceService
        with self.assertRaisesMessage(ValueError, 'must differ'):
            TSABalanceService.process_transfer(
                source_tsa=_fake_tsa(pk=7),
                target_tsa=_fake_tsa(pk=7),
                amount=Decimal('100'),
                actor=SimpleNamespace(username='alice'),
            )

    def test_inactive_source_rejected(self):
        from accounting.services.treasury_service import TSABalanceService
        with self.assertRaisesMessage(ValueError, 'must be active'):
            TSABalanceService.process_transfer(
                source_tsa=_fake_tsa(pk=1, is_active=False),
                target_tsa=_fake_tsa(pk=2),
                amount=Decimal('100'),
                actor=SimpleNamespace(username='alice'),
            )

    def test_inactive_target_rejected(self):
        from accounting.services.treasury_service import TSABalanceService
        with self.assertRaisesMessage(ValueError, 'must be active'):
            TSABalanceService.process_transfer(
                source_tsa=_fake_tsa(pk=1),
                target_tsa=_fake_tsa(pk=2, is_active=False),
                amount=Decimal('100'),
                actor=SimpleNamespace(username='alice'),
            )

    def test_missing_gl_cash_account_rejected(self):
        from accounting.services.treasury_service import TSABalanceService
        with self.assertRaisesMessage(ValueError, 'gl_cash_account configured'):
            TSABalanceService.process_transfer(
                source_tsa=_fake_tsa(pk=1, gl_cash_account_id=None),
                target_tsa=_fake_tsa(pk=2),
                amount=Decimal('100'),
                actor=SimpleNamespace(username='alice'),
            )

    def test_journal_post_signature_documented(self):
        """Regression guard: the service exposes ``process_transfer`` as
        a classmethod with the keyword-only contract documented in the
        viewset. Catches accidental signature drift between view and
        service that would silently produce 500s in production.
        """
        import inspect
        from accounting.services.treasury_service import TSABalanceService
        sig = inspect.signature(TSABalanceService.process_transfer)
        # source_tsa, target_tsa, amount, actor are required keyword args;
        # transfer_date and narration are optional.
        params = sig.parameters
        for required in ('source_tsa', 'target_tsa', 'amount', 'actor'):
            self.assertIn(required, params, f'missing required kwarg: {required}')
            self.assertEqual(
                params[required].kind,
                inspect.Parameter.KEYWORD_ONLY,
                f'{required} must be keyword-only',
            )
        for optional in ('transfer_date', 'narration'):
            self.assertIn(optional, params)


class TSATransferDecimalCoercionTests(SimpleTestCase):
    """The ``amount`` parameter is coerced via ``Decimal(str(...))`` at
    the boundary (M8 lesson) so float-from-JSON inputs don't silently
    downgrade money math. These tests pin that contract.
    """

    def test_int_amount_accepted_then_blocked_at_zero_check(self):
        """Int(0) coerces to Decimal('0') and fails the >0 guard
        cleanly — not with a TypeError."""
        from accounting.services.treasury_service import TSABalanceService
        with self.assertRaisesMessage(ValueError, 'must be greater than zero'):
            TSABalanceService.process_transfer(
                source_tsa=_fake_tsa(pk=1),
                target_tsa=_fake_tsa(pk=2),
                amount=0,
                actor=SimpleNamespace(username='alice'),
            )

    def test_string_amount_accepted(self):
        """JSON inputs arrive as strings; the service must accept them.

        We expect this to pass guard validation and then fail at the
        first DB-touching call (which we patch to raise) — proving the
        Decimal coercion succeeded.
        """
        from accounting.services.treasury_service import TSABalanceService
        # Patch transaction.atomic so we can intercept right before
        # the lock. The service has already validated by that point.
        with patch(
            'accounting.services.treasury_service.transaction.atomic',
            side_effect=RuntimeError('reached atomic block'),
        ):
            with self.assertRaisesMessage(RuntimeError, 'reached atomic block'):
                TSABalanceService.process_transfer(
                    source_tsa=_fake_tsa(pk=1),
                    target_tsa=_fake_tsa(pk=2),
                    amount='150.75',  # string, like JSON
                    actor=SimpleNamespace(username='alice'),
                )
