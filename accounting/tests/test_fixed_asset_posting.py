"""Tests for accounting/services/fixed_asset_posting.py.

All tests run without a real database — the service logic is isolated
via MagicMock and unittest.mock.patch.  No Django DB setup required.

The service uses lazy imports inside the function body (``from X import Y``
inside ``post_capitalisation``) to avoid circular imports at module load time.
Therefore we patch at the SOURCE module path rather than the service module:

  * ``accounting.models.gl.JournalHeader``  →  the GL model
  * ``accounting.models.gl.JournalLine``    →  the GL model
  * ``accounting.models.gl.Account``        →  the GL model
  * ``accounting.services.update_gl_from_journal``  →  the service init helper

We also patch ``django.db.transaction.atomic`` at its source so that the
``@transaction.atomic`` decorator on ``post_capitalisation`` is bypassed in
each test (the decorator resolves at call time because it is applied via a
classmethod descriptor that re-reads the attribute each invocation).

Coverage:
  * Happy path: post_capitalisation creates journal with correct lines
  * Happy path: payment_method='ap' resolves Accounts Payable account
  * Idempotent skip: second call with idempotent=True returns existing journal
  * Non-idempotent double-post raises FixedAssetPostingError
  * Invalid payment_method raises FixedAssetPostingError
  * Missing asset_account raises FixedAssetPostingError
  * Missing MDA raises FixedAssetPostingError
  * Already auto-capitalised from AP (created_from_journal_line_id) raises
  * Zero / missing acquisition_cost raises FixedAssetPostingError
  * Credit account not found raises FixedAssetPostingError
"""
from __future__ import annotations

import contextlib
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_asset(
    *,
    asset_number='FA-2026-00001',
    asset_account=True,
    mda=True,
    acquisition_cost=Decimal('500000.00'),
    created_from_journal_line_id=None,
    acquisition_date=None,
    fund=None,
    function=None,
    program=None,
    geo=None,
    name='Test Generator',
):
    """Build a minimal FixedAsset mock."""
    asset = MagicMock()
    asset.pk = 1
    asset.asset_number = asset_number
    asset.name = name
    asset.asset_account = MagicMock() if asset_account else None
    asset.mda = MagicMock() if mda else None
    asset.acquisition_cost = acquisition_cost
    asset.created_from_journal_line_id = created_from_journal_line_id
    asset.acquisition_date = acquisition_date
    asset.fund = fund
    asset.function = function
    asset.program = program
    asset.geo = geo
    return asset


@contextlib.contextmanager
def _patch_db(*, existing_journal=None, cr_account=None):
    """Context manager that patches all DB-touching callables used by
    post_capitalisation.  Returns (MockJH, MockJL, MockAcct, mock_gl_update,
    mock_journal).

    ``existing_journal``: if set, the idempotency filter returns this object.
    ``cr_account``: the Account returned for the Cash / AP lookup.

    We patch at the source module paths because post_capitalisation uses lazy
    imports inside the function body:
      * accounting.models.gl.JournalHeader
      * accounting.models.gl.JournalLine
      * accounting.models.gl.Account
      * accounting.services.update_gl_from_journal
      * accounting.services.fixed_asset_posting.transaction  (the imported name)
    """
    mock_journal = MagicMock()
    mock_journal.pk = 99

    # Make transaction.atomic a no-op context manager when called as
    # ``with transaction.atomic():``
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=None)
    cm.__exit__ = MagicMock(return_value=False)
    mock_atomic = MagicMock(return_value=cm)

    with patch('accounting.services.fixed_asset_posting.transaction') as mock_txn, \
         patch('accounting.models.gl.JournalHeader') as MockJH, \
         patch('accounting.models.gl.JournalLine') as MockJL, \
         patch('accounting.models.gl.Account') as MockAcct, \
         patch('accounting.services.update_gl_from_journal') as mock_gl:

        mock_txn.atomic = mock_atomic

        # Idempotency lookup
        MockJH.objects.filter.return_value.first.return_value = existing_journal
        MockJH.objects.create.return_value = mock_journal

        # Credit account lookup
        MockAcct.objects.filter.return_value.first.return_value = cr_account

        yield MockJH, MockJL, MockAcct, mock_gl, mock_journal


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPostCapitalisationHappyPath:
    """Happy-path tests for FixedAssetPostingService.post_capitalisation."""

    def test_creates_journal_with_correct_lines(self):
        """post_capitalisation creates a JournalHeader + 2 JournalLines and
        calls update_gl_from_journal with the correct arguments."""
        from accounting.services.fixed_asset_posting import FixedAssetPostingService

        asset = _make_asset()
        mock_cr_account = MagicMock()

        with _patch_db(existing_journal=None, cr_account=mock_cr_account) as (
            MockJH, MockJL, MockAcct, mock_gl, mock_journal
        ):
            result = FixedAssetPostingService.post_capitalisation(
                asset,
                payment_method='cash',
                user=None,
                idempotent=False,
            )

        # Journal created once with the correct reference + status
        MockJH.objects.create.assert_called_once()
        create_kwargs = MockJH.objects.create.call_args[1]
        assert create_kwargs['reference_number'] == f'ACQ-{asset.asset_number}'
        assert create_kwargs['status'] == 'Posted'

        # Two journal lines: DR asset account + CR cash
        assert MockJL.objects.create.call_count == 2
        dr_kwargs = MockJL.objects.create.call_args_list[0][1]
        cr_kwargs = MockJL.objects.create.call_args_list[1][1]
        assert dr_kwargs['debit'] == asset.acquisition_cost
        assert dr_kwargs['credit'] == Decimal('0.00')
        assert dr_kwargs['account'] is asset.asset_account
        assert cr_kwargs['debit'] == Decimal('0.00')
        assert cr_kwargs['credit'] == asset.acquisition_cost
        assert cr_kwargs['account'] is mock_cr_account

        # GL update called
        mock_gl.assert_called_once_with(
            mock_journal,
            fund=asset.fund,
            function=asset.function,
            program=asset.program,
            geo=asset.geo,
        )

        assert result is mock_journal

    def test_ap_payment_method_resolves_payable_account(self):
        """payment_method='ap' looks up an Accounts Payable account."""
        from accounting.services.fixed_asset_posting import FixedAssetPostingService

        asset = _make_asset()
        mock_ap_account = MagicMock()

        with _patch_db(existing_journal=None, cr_account=mock_ap_account) as (
            MockJH, MockJL, MockAcct, mock_gl, mock_journal
        ):
            result = FixedAssetPostingService.post_capitalisation(
                asset,
                payment_method='ap',
                user=None,
                idempotent=False,
            )

        # The second JournalLine credit account must be the AP mock
        cr_kwargs = MockJL.objects.create.call_args_list[1][1]
        assert cr_kwargs['account'] is mock_ap_account
        assert result is mock_journal


class TestPostCapitalisationIdempotency:
    """Idempotency tests for FixedAssetPostingService.post_capitalisation."""

    def test_idempotent_skip_returns_existing_journal(self):
        """When idempotent=True and a capitalisation journal already exists,
        the service returns the existing journal without creating a new one."""
        from accounting.services.fixed_asset_posting import FixedAssetPostingService

        asset = _make_asset()
        existing = MagicMock()
        existing.pk = 42

        with _patch_db(existing_journal=existing) as (
            MockJH, MockJL, MockAcct, mock_gl, _
        ):
            result = FixedAssetPostingService.post_capitalisation(
                asset,
                payment_method='cash',
                user=None,
                idempotent=True,
            )

        # No new journal or lines created
        MockJH.objects.create.assert_not_called()
        MockJL.objects.create.assert_not_called()
        mock_gl.assert_not_called()
        # Existing journal returned
        assert result is existing

    def test_non_idempotent_double_post_raises(self):
        """When idempotent=False and a capitalisation journal already exists,
        the service raises FixedAssetPostingError."""
        from accounting.services.fixed_asset_posting import (
            FixedAssetPostingService,
            FixedAssetPostingError,
        )

        asset = _make_asset()
        existing = MagicMock()
        existing.pk = 42

        with _patch_db(existing_journal=existing) as (MockJH, MockJL, _, __, ___):
            with pytest.raises(FixedAssetPostingError, match='capitalisation journal already exists'):
                FixedAssetPostingService.post_capitalisation(
                    asset,
                    payment_method='cash',
                    user=None,
                    idempotent=False,
                )

        MockJH.objects.create.assert_not_called()
        MockJL.objects.create.assert_not_called()


class TestPostCapitalisationValidation:
    """Validation / error-path tests for FixedAssetPostingService."""

    def test_invalid_payment_method_raises(self):
        """payment_method not in ('cash', 'ap') raises FixedAssetPostingError
        immediately — before any DB access."""
        from accounting.services.fixed_asset_posting import (
            FixedAssetPostingService,
            FixedAssetPostingError,
        )

        asset = _make_asset()

        with _patch_db() as (MockJH, MockJL, MockAcct, mock_gl, _):
            with pytest.raises(FixedAssetPostingError, match="Invalid payment_method 'wire'"):
                FixedAssetPostingService.post_capitalisation(
                    asset,
                    payment_method='wire',
                    user=None,
                )

        MockJH.objects.create.assert_not_called()

    def test_missing_asset_account_raises(self):
        """Asset with no asset_account raises FixedAssetPostingError."""
        from accounting.services.fixed_asset_posting import (
            FixedAssetPostingService,
            FixedAssetPostingError,
        )

        asset = _make_asset(asset_account=False)

        with _patch_db() as (MockJH, _, __, ___, ____):
            with pytest.raises(FixedAssetPostingError, match='Asset account not configured'):
                FixedAssetPostingService.post_capitalisation(
                    asset,
                    payment_method='cash',
                    user=None,
                )

        MockJH.objects.create.assert_not_called()

    def test_missing_mda_raises(self):
        """Asset with no MDA raises FixedAssetPostingError."""
        from accounting.services.fixed_asset_posting import (
            FixedAssetPostingService,
            FixedAssetPostingError,
        )

        asset = _make_asset(mda=False)

        with _patch_db() as (MockJH, _, __, ___, ____):
            with pytest.raises(FixedAssetPostingError, match='MDA is required'):
                FixedAssetPostingService.post_capitalisation(
                    asset,
                    payment_method='cash',
                    user=None,
                )

        MockJH.objects.create.assert_not_called()

    def test_ap_path_asset_raises(self):
        """Asset already capitalised from AP invoice (created_from_journal_line_id
        set) raises FixedAssetPostingError to prevent double-booking."""
        from accounting.services.fixed_asset_posting import (
            FixedAssetPostingService,
            FixedAssetPostingError,
        )

        asset = _make_asset(created_from_journal_line_id=77)

        with _patch_db() as (MockJH, _, __, ___, ____):
            with pytest.raises(FixedAssetPostingError, match='already capitalised from a vendor invoice'):
                FixedAssetPostingService.post_capitalisation(
                    asset,
                    payment_method='cash',
                    user=None,
                )

        MockJH.objects.create.assert_not_called()

    def test_zero_acquisition_cost_raises(self):
        """Asset with acquisition_cost <= 0 raises FixedAssetPostingError."""
        from accounting.services.fixed_asset_posting import (
            FixedAssetPostingService,
            FixedAssetPostingError,
        )

        asset = _make_asset(acquisition_cost=Decimal('0.00'))

        with _patch_db(existing_journal=None) as (MockJH, _, __, ___, ____):
            with pytest.raises(FixedAssetPostingError, match='no acquisition cost'):
                FixedAssetPostingService.post_capitalisation(
                    asset,
                    payment_method='cash',
                    user=None,
                )

        MockJH.objects.create.assert_not_called()

    def test_credit_account_not_found_raises(self):
        """When the cash / AP GL account lookup returns None, raises
        FixedAssetPostingError."""
        from accounting.services.fixed_asset_posting import (
            FixedAssetPostingService,
            FixedAssetPostingError,
        )

        asset = _make_asset()

        # cr_account=None means all Account.objects.filter().first() → None
        with _patch_db(existing_journal=None, cr_account=None) as (
            MockJH, _, __, ___, ____
        ):
            with pytest.raises(FixedAssetPostingError, match='Credit account.*not found'):
                FixedAssetPostingService.post_capitalisation(
                    asset,
                    payment_method='cash',
                    user=None,
                )

        MockJH.objects.create.assert_not_called()
