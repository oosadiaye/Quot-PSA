"""
Sprint-5 regression tests: CanViewFinancialStatements permission logic.

Covers S5-03 — every grant pathway is exercised via mocked users so
the tests stay in the fast (no-DB) tier. DB-backed integration tests
live in a separate file and run in the DB tier.

The six grant pathways:
  1. Unauthenticated  → denied
  2. Superuser        → allowed
  3. Staff user       → allowed
  4. Has ``accounting.view_financial_statements``   → allowed
  5. Has ``accounting.view_journalheader`` (legacy) → allowed
  6. Linked to an Organization whose ``org_role`` grants cross-MDA read
     (BUDGET_AUTHORITY / FINANCE_AUTHORITY / AUDIT_AUTHORITY) → allowed
"""
from unittest.mock import MagicMock, patch


from accounting.permissions import CanViewFinancialStatements


def _request(user):
    """Build a minimal DRF-compatible request object carrying a user."""
    return MagicMock(user=user)


class TestCanViewFinancialStatements:
    """Grant-pathway matrix for the IPSAS permission gate."""

    def setup_method(self):
        self.perm = CanViewFinancialStatements()

    # ── Deny path ────────────────────────────────────────────────────────

    def test_unauthenticated_denied(self):
        user = MagicMock(is_authenticated=False)
        assert self.perm.has_permission(_request(user), view=None) is False

    def test_authenticated_without_any_grant_denied(self):
        """Authenticated but has no perm, no oversight org → denied."""
        user = MagicMock(
            is_authenticated=True, is_superuser=False, is_staff=False,
        )
        user.has_perm.return_value = False
        with patch(
            'accounting.permissions._user_has_oversight_org', return_value=False,
        ):
            assert self.perm.has_permission(_request(user), view=None) is False

    # ── Allow paths ──────────────────────────────────────────────────────

    def test_superuser_allowed(self):
        user = MagicMock(
            is_authenticated=True, is_superuser=True, is_staff=False,
        )
        assert self.perm.has_permission(_request(user), view=None) is True

    def test_staff_allowed(self):
        user = MagicMock(
            is_authenticated=True, is_superuser=False, is_staff=True,
        )
        assert self.perm.has_permission(_request(user), view=None) is True

    def test_view_financial_statements_perm_allowed(self):
        """The granular permission grants access on its own."""
        user = MagicMock(
            is_authenticated=True, is_superuser=False, is_staff=False,
        )
        user.has_perm.side_effect = lambda p: p == 'accounting.view_financial_statements'
        with patch(
            'accounting.permissions._user_has_oversight_org', return_value=False,
        ):
            assert self.perm.has_permission(_request(user), view=None) is True

    def test_legacy_view_journalheader_perm_allowed(self):
        """Backward compat: anyone with ledger read access sees IPSAS reports."""
        user = MagicMock(
            is_authenticated=True, is_superuser=False, is_staff=False,
        )
        user.has_perm.side_effect = lambda p: p == 'accounting.view_journalheader'
        with patch(
            'accounting.permissions._user_has_oversight_org', return_value=False,
        ):
            assert self.perm.has_permission(_request(user), view=None) is True

    def test_oversight_org_allowed(self):
        """PFM oversight role via UserOrganization grants access."""
        user = MagicMock(
            is_authenticated=True, is_superuser=False, is_staff=False,
        )
        user.has_perm.return_value = False
        with patch(
            'accounting.permissions._user_has_oversight_org', return_value=True,
        ):
            assert self.perm.has_permission(_request(user), view=None) is True

    # ── Defence-in-depth ─────────────────────────────────────────────────

    def test_oversight_lookup_failure_falls_through_to_deny(self):
        """If UserOrganization lookup raises (older tenant), treat as no access."""
        user = MagicMock(
            is_authenticated=True, is_superuser=False, is_staff=False,
        )
        user.has_perm.return_value = False
        # Real helper is tried — forces the except-branch by patching the
        # underlying model import to raise.
        with patch('core.models.UserOrganization') as UserOrg:
            UserOrg.objects.filter.side_effect = RuntimeError('table missing')
            # Should NOT raise; should return False.
            assert self.perm.has_permission(_request(user), view=None) is False

    def test_none_user_denied(self):
        """`user=None` must be denied — guards against misconfiguration."""
        request = MagicMock(user=None)
        assert self.perm.has_permission(request, view=None) is False
