"""
Sprint-25 tests — approval rule seed spec + API contract.
"""
from __future__ import annotations

from decimal import Decimal



class TestApprovalRuleSpec:
    """Freeze the baseline seed spec — any change that silently weakens
    the workflow rewires production approval authority. Hard stop."""

    def test_has_every_document_type(self):
        """Every document type recognised by ApprovalRule.DOCUMENT_TYPES
        must have at least one rule in the seed."""
        from accounting.management.commands.seed_approval_rules import RULES
        from accounting.models.audit import ApprovalRule
        expected = {d[0] for d in ApprovalRule.DOCUMENT_TYPES}
        seeded = {r['document_type'] for r in RULES}
        missing = expected - seeded
        assert not missing, f'Missing approval rules for: {missing}'

    def test_rules_are_well_formed(self):
        from accounting.management.commands.seed_approval_rules import RULES
        for r in RULES:
            assert 'document_type' in r
            assert 'min_amount' in r
            assert 'max_amount' in r
            assert 'levels' in r
            assert len(r['levels']) >= 1
            for lvl in r['levels']:
                assert 'level' in lvl
                assert 'role_code' in lvl
                assert 'min_approvers' in lvl
                assert lvl['min_approvers'] >= 1

    def test_amount_bands_are_non_overlapping_per_document(self):
        """Two rules for the same document_type must not cover the
        same amount — the engine would pick one arbitrarily."""
        from accounting.management.commands.seed_approval_rules import RULES
        by_type: dict[str, list] = {}
        for r in RULES:
            by_type.setdefault(r['document_type'], []).append(r)
        for doc, rules in by_type.items():
            # Sort by min_amount
            ordered = sorted(rules, key=lambda x: x['min_amount'])
            for i in range(1, len(ordered)):
                prev = ordered[i - 1]
                curr = ordered[i]
                prev_max = prev['max_amount'] if prev['max_amount'] is not None else Decimal('999999999999')
                assert curr['min_amount'] > prev_max, (
                    f'Overlap in {doc}: {prev} + {curr}'
                )

    def test_levels_escalate_authority(self):
        """Multi-level rules must escalate — each higher level has >=
        authority than the level below. We don't encode authority
        ordinally, so we only check the non-decreasing level number."""
        from accounting.management.commands.seed_approval_rules import RULES
        for r in RULES:
            levels = [lvl['level'] for lvl in r['levels']]
            assert levels == sorted(levels), (
                f'Levels must be ordered: {r["document_type"]} {levels}'
            )

    def test_every_role_referenced_is_a_baseline_role(self):
        """All role codes in approval levels must appear in the
        baseline role seed — otherwise the approval engine routes
        requests to a non-existent role."""
        from accounting.management.commands.seed_approval_rules import RULES
        from core.management.commands.seed_baseline_roles import BASELINE_ROLES
        baseline_codes = {r['code'] for r in BASELINE_ROLES}
        for rule in RULES:
            for lvl in rule['levels']:
                assert lvl['role_code'] in baseline_codes, (
                    f'Role {lvl["role_code"]} in approval rule '
                    f'{rule["document_type"]} not in baseline spec'
                )


class TestApprovalRuleSerializer:

    def test_fields(self):
        from accounting.views.approval_rules import ApprovalRuleSerializer
        expected = {
            'id', 'document_type', 'document_type_display',
            'min_amount', 'max_amount',
            'approval_levels', 'auto_approve_roles',
            'skip_approval_if_same_user', 'require_comment_on_reject',
            'is_active', 'levels', 'level_count',
            'created_at', 'updated_at',
        }
        assert set(ApprovalRuleSerializer.Meta.fields) == expected

    def test_level_serializer_fields(self):
        from accounting.views.approval_rules import ApprovalLevelSerializer
        expected = {
            'id', 'level', 'approver_type', 'approver_type_display',
            'approver_value', 'role_name', 'min_approvers',
        }
        assert set(ApprovalLevelSerializer.Meta.fields) == expected


class TestApprovalRuleViewSetPermissions:

    def test_read_actions_any_authenticated(self):
        from accounting.views.approval_rules import ApprovalRuleViewSet
        from rest_framework.permissions import IsAuthenticated, IsAdminUser
        vs = ApprovalRuleViewSet()
        for action in ('list', 'retrieve', 'summary'):
            vs.action = action
            perms = vs.get_permissions()
            assert len(perms) == 1
            assert isinstance(perms[0], IsAuthenticated)
            assert not isinstance(perms[0], IsAdminUser)

    def test_write_actions_admin_only(self):
        from accounting.views.approval_rules import ApprovalRuleViewSet
        from rest_framework.permissions import IsAdminUser
        vs = ApprovalRuleViewSet()
        for action in ('create', 'update', 'partial_update', 'destroy'):
            vs.action = action
            perms = vs.get_permissions()
            assert len(perms) == 1
            assert isinstance(perms[0], IsAdminUser)


class TestRoleCoverage:
    """Every baseline manager role must appear as an approver somewhere
    — otherwise the role has authority flags with no workflow to use them."""

    def test_every_manager_is_referenced(self):
        from accounting.management.commands.seed_approval_rules import RULES
        from core.management.commands.seed_baseline_roles import BASELINE_ROLES
        manager_codes = {
            r['code'] for r in BASELINE_ROLES if r['role_type'] == 'manager'
        }
        referenced = set()
        for rule in RULES:
            for lvl in rule['levels']:
                referenced.add(lvl['role_code'])
        for code in manager_codes:
            assert code in referenced, (
                f'Manager role {code} never approves anything in seeded rules — '
                'dead role, weaken seed'
            )
