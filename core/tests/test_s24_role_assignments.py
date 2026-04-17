"""
Sprint-24 tests — role assignment model + API contract.
"""
from __future__ import annotations



class TestRoleAssignmentModel:

    def test_model_importable(self):
        from core.models import RoleAssignment
        assert RoleAssignment is not None

    def test_unique_together(self):
        from core.models import RoleAssignment
        assert RoleAssignment._meta.unique_together == (('user', 'role'),)

    def test_indexes_cover_user_and_role_active(self):
        from core.models import RoleAssignment
        field_tuples = [tuple(i.fields) for i in RoleAssignment._meta.indexes]
        assert ('user', 'is_active') in field_tuples
        assert ('role', 'is_active') in field_tuples


class TestRoleAssignmentSerializer:

    def test_fields(self):
        from core.views.role_assignments import RoleAssignmentSerializer
        expected = {
            'id', 'user', 'user_username', 'user_full_name',
            'role', 'role_code', 'role_name', 'role_module', 'role_type',
            'is_active', 'assigned_at', 'assigned_by', 'assigned_by_username',
            'notes',
        }
        assert set(RoleAssignmentSerializer.Meta.fields) == expected


class TestTruthyParser:

    def test_truthy_accepts_variants(self):
        from core.views.role_assignments import _truthy
        assert _truthy(True) is True
        assert _truthy('true') is True
        assert _truthy('TRUE') is True
        assert _truthy('1') is True
        assert _truthy('yes') is True
        assert _truthy('on') is True

    def test_falsy(self):
        from core.views.role_assignments import _truthy
        assert _truthy(None) is False
        assert _truthy(False) is False
        assert _truthy('') is False
        assert _truthy('0') is False
        assert _truthy('nope') is False


class TestRoleAssignmentViewSetPermissions:
    """Writes must require admin — reads can be any authenticated user."""

    def test_read_actions_permissioned_as_authenticated(self):
        from core.views.role_assignments import RoleAssignmentViewSet
        from rest_framework.permissions import IsAuthenticated, IsAdminUser

        vs = RoleAssignmentViewSet()
        for action in ('list', 'retrieve', 'by_user', 'preview_sod'):
            vs.action = action
            perms = vs.get_permissions()
            assert len(perms) == 1
            assert isinstance(perms[0], IsAuthenticated)
            assert not isinstance(perms[0], IsAdminUser)

    def test_write_actions_permissioned_as_admin(self):
        from core.views.role_assignments import RoleAssignmentViewSet
        from rest_framework.permissions import IsAdminUser

        vs = RoleAssignmentViewSet()
        for action in ('create', 'update', 'partial_update', 'destroy'):
            vs.action = action
            perms = vs.get_permissions()
            assert len(perms) == 1
            assert isinstance(perms[0], IsAdminUser)


class TestSODIntegrationPoint:
    """The create() method must call conflicts_for_roles() on the
    projected set (current roles + new). Source-level check."""

    def test_create_invokes_sod_check(self):
        import inspect
        from core.views.role_assignments import RoleAssignmentViewSet
        src = inspect.getsource(RoleAssignmentViewSet.create)
        assert 'conflicts_for_roles' in src
        # Must project user's existing roles alongside the new one.
        assert 'values_list' in src
        assert "role__code" in src or 'role.code' in src
