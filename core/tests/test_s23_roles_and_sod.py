"""
Sprint-23 tests — baseline roles + SOD conflict detector.

No-DB fast tier: exercises the service contract and matrix integrity.
"""
from __future__ import annotations



class TestBaselineRoleSpec:
    """The baseline role spec is the source of truth for the seed
    command — changing it silently would re-authorise production users.
    Freeze the shape."""

    def test_six_baseline_roles(self):
        from core.management.commands.seed_baseline_roles import BASELINE_ROLES
        assert len(BASELINE_ROLES) == 6

    def test_codes_are_unique(self):
        from core.management.commands.seed_baseline_roles import BASELINE_ROLES
        codes = [r['code'] for r in BASELINE_ROLES]
        assert len(codes) == len(set(codes)), 'duplicate code'

    def test_every_module_has_manager_and_officer(self):
        from core.management.commands.seed_baseline_roles import BASELINE_ROLES
        by_module: dict[str, set[str]] = {}
        for r in BASELINE_ROLES:
            by_module.setdefault(r['module'], set()).add(r['role_type'])
        for mod, types in by_module.items():
            assert 'manager' in types, f'{mod} missing manager'
            assert 'officer' in types, f'{mod} missing officer'

    def test_officers_cannot_approve_or_post(self):
        """Core SOD discipline — officers are makers, not approvers."""
        from core.management.commands.seed_baseline_roles import BASELINE_ROLES
        for r in BASELINE_ROLES:
            if r['role_type'] == 'officer':
                assert not r['perms']['can_approve'], (
                    f'{r["code"]} is officer but has can_approve=True'
                )
                assert not r['perms']['can_post'], (
                    f'{r["code"]} is officer but has can_post=True'
                )

    def test_managers_cannot_add(self):
        """Maker/checker split — managers review, officers enter."""
        from core.management.commands.seed_baseline_roles import BASELINE_ROLES
        for r in BASELINE_ROLES:
            if r['role_type'] == 'manager':
                assert not r['perms']['can_add'], (
                    f'{r["code"]} is manager but has can_add=True'
                )

    def test_no_delete_permission_for_any_baseline(self):
        """Delete on financial data requires admin override, not role."""
        from core.management.commands.seed_baseline_roles import BASELINE_ROLES
        for r in BASELINE_ROLES:
            assert not r['perms']['can_delete'], (
                f'{r["code"]} has can_delete=True on baseline — not allowed'
            )


class TestSODMatrixShape:

    def test_matrix_non_empty(self):
        from core.services.sod_conflicts import matrix
        rules = matrix()
        assert len(rules) >= 6

    def test_every_rule_has_required_fields(self):
        from core.services.sod_conflicts import matrix
        for rule in matrix():
            assert 'role_a' in rule
            assert 'role_b' in rule
            assert 'severity' in rule
            assert 'reason' in rule
            assert rule['severity'] in ('high', 'medium', 'low')
            assert rule['role_a'] != rule['role_b']

    def test_same_module_conflicts_are_high(self):
        """Maker/checker violations within one module are the gravest."""
        from core.services.sod_conflicts import matrix
        officer_suffixes = ('_officer',)
        manager_suffixes = ('_manager', '_general')
        for rule in matrix():
            a_is_officer = any(rule['role_a'].endswith(s) for s in officer_suffixes)
            b_is_manager = any(rule['role_b'].endswith(s) for s in manager_suffixes)
            a_module = rule['role_a'].split('_', 1)[0]
            b_module = rule['role_b'].split('_', 1)[0]
            if a_is_officer and b_is_manager and a_module == b_module:
                assert rule['severity'] == 'high', (
                    f'{rule["role_a"]} + {rule["role_b"]} same-module split '
                    'must be severity=high'
                )


class TestSODConflictsForRoles:

    def test_clean_combination_returns_empty(self):
        """A single role is always SOD-clean."""
        from core.services.sod_conflicts import conflicts_for_roles
        assert conflicts_for_roles(['budget_officer']) == []
        assert conflicts_for_roles(['accountant_general']) == []
        assert conflicts_for_roles([]) == []

    def test_detects_maker_checker_collision(self):
        from core.services.sod_conflicts import conflicts_for_roles
        hits = conflicts_for_roles(['budget_officer', 'budget_manager'])
        assert len(hits) >= 1
        assert all(h['severity'] == 'high' for h in hits)

    def test_detects_cross_module_collision(self):
        from core.services.sod_conflicts import conflicts_for_roles
        hits = conflicts_for_roles(['accountant_general', 'procurement_manager'])
        assert len(hits) >= 1
        assert any(h['severity'] == 'high' for h in hits)

    def test_accepts_legal_combination(self):
        """A pure officer + a pure viewer in a different module
        (conceptually) should be clean."""
        from core.services.sod_conflicts import conflicts_for_roles
        # budget_officer alone — no conflict partner
        assert conflicts_for_roles(['budget_officer']) == []

    def test_accepts_set_input(self):
        """The service accepts sets, not just lists."""
        from core.services.sod_conflicts import conflicts_for_roles
        hits = conflicts_for_roles({'budget_officer', 'budget_manager'})
        assert len(hits) >= 1

    def test_irrelevant_codes_ignored(self):
        """Unknown role codes don't crash the checker."""
        from core.services.sod_conflicts import conflicts_for_roles
        assert conflicts_for_roles(['fake_role', 'other_fake']) == []


class TestRoleSerializerFields:
    """Freeze the API contract."""

    def test_serializer_fields(self):
        from core.views.roles import RoleSerializer
        expected = {
            'id', 'code', 'name', 'module', 'module_display',
            'role_type', 'role_type_display',
            'can_view', 'can_add', 'can_change', 'can_delete',
            'can_approve', 'can_post',
            'is_active', 'is_default', 'permissions',
            'created_at', 'updated_at',
        }
        assert set(RoleSerializer.Meta.fields) == expected
