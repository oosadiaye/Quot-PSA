"""Assigning users to MDAs (core.Organization) when a user is created or edited.

``UserOrganization`` already existed but nothing in the app could create one:
the Create User form had no MDA field and ``POST /core/tenant-users/`` never
wrote a membership. These tests pin the service that does, the serializer
input that feeds it, and the permission on the org-users endpoint.
"""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework import serializers as drf

from core.models import Organization, UserOrganization


@pytest.fixture
def user(db):
    return User.objects.create_user(username='mda_user', password='x-Strong-1234')


@pytest.fixture
def mda_a(db):
    return Organization.objects.create(code='MDA-A', name='Ministry A')


@pytest.fixture
def mda_b(db):
    return Organization.objects.create(code='MDA-B', name='Ministry B')


@pytest.fixture
def mda_inactive(db):
    return Organization.objects.create(code='MDA-X', name='Closed Ministry', is_active=False)


def _rows(user):
    return {
        uo.organization.code: uo
        for uo in UserOrganization.objects.filter(user=user).select_related('organization')
    }


@pytest.mark.django_db
class TestReplaceUserOrganizations:
    def test_creates_memberships_and_flags_the_default(self, user, mda_a, mda_b):
        from core.services.organization_assignment import replace_user_organizations

        replace_user_organizations(
            user,
            [{'organization': mda_a, 'per_org_role': 'manager'},
             {'organization': mda_b, 'per_org_role': 'officer'}],
            default_organization_id=mda_b.pk,
        )
        rows = _rows(user)
        assert set(rows) == {'MDA-A', 'MDA-B'}
        assert rows['MDA-A'].per_org_role == 'manager'
        assert rows['MDA-B'].is_default is True
        assert rows['MDA-A'].is_default is False

    def test_a_single_mda_becomes_the_default_automatically(self, user, mda_a):
        from core.services.organization_assignment import replace_user_organizations

        replace_user_organizations(user, [{'organization': mda_a}], default_organization_id=None)
        assert _rows(user)['MDA-A'].is_default is True

    def test_without_an_explicit_default_the_first_listed_is_used(self, user, mda_a, mda_b):
        from core.services.organization_assignment import replace_user_organizations

        replace_user_organizations(
            user, [{'organization': mda_b}, {'organization': mda_a}], default_organization_id=None,
        )
        rows = _rows(user)
        assert rows['MDA-B'].is_default is True
        assert rows['MDA-A'].is_default is False

    def test_replace_removes_unlisted_and_keeps_exactly_one_default(self, user, mda_a, mda_b):
        from core.services.organization_assignment import replace_user_organizations

        replace_user_organizations(
            user, [{'organization': mda_a}, {'organization': mda_b}], default_organization_id=mda_a.pk,
        )
        replace_user_organizations(user, [{'organization': mda_b}], default_organization_id=mda_b.pk)

        rows = _rows(user)
        assert set(rows) == {'MDA-B'}
        assert UserOrganization.objects.filter(user=user, is_default=True).count() == 1

    def test_empty_list_clears_every_assignment(self, user, mda_a):
        from core.services.organization_assignment import replace_user_organizations

        replace_user_organizations(user, [{'organization': mda_a}], default_organization_id=None)
        replace_user_organizations(user, [], default_organization_id=None)
        assert UserOrganization.objects.filter(user=user).count() == 0

    def test_is_idempotent_and_updates_the_role_in_place(self, user, mda_a):
        from core.services.organization_assignment import replace_user_organizations

        replace_user_organizations(user, [{'organization': mda_a, 'per_org_role': 'viewer'}], None)
        replace_user_organizations(user, [{'organization': mda_a, 'per_org_role': 'admin'}], None)
        assert UserOrganization.objects.filter(user=user).count() == 1
        assert _rows(user)['MDA-A'].per_org_role == 'admin'


@pytest.mark.django_db
class TestOrganizationsInput:
    """The serializer fragment shared by create and update."""

    def _validate(self, payload):
        from core.serializers import OrganizationAssignmentsMixin

        class _S(OrganizationAssignmentsMixin, drf.Serializer):
            pass

        s = _S(data=payload)
        s.is_valid(raise_exception=True)
        return s.validated_data

    def test_accepts_a_valid_assignment(self, mda_a, mda_b):
        data = self._validate({
            'organizations': [{'organization': mda_a.pk, 'per_org_role': 'manager'},
                              {'organization': mda_b.pk}],
            'default_organization': mda_b.pk,
        })
        assert [o['organization'] for o in data['organizations']] == [mda_a, mda_b]
        assert data['organizations'][1]['per_org_role'] == 'officer'  # default
        assert data['default_organization'] == mda_b.pk

    def test_rejects_an_unknown_organization(self):
        with pytest.raises(drf.ValidationError):
            self._validate({'organizations': [{'organization': 999999}]})

    def test_rejects_an_inactive_organization(self, mda_inactive):
        with pytest.raises(drf.ValidationError):
            self._validate({'organizations': [{'organization': mda_inactive.pk}]})

    def test_rejects_the_same_mda_listed_twice(self, mda_a):
        with pytest.raises(drf.ValidationError):
            self._validate({'organizations': [{'organization': mda_a.pk}, {'organization': mda_a.pk}]})

    def test_rejects_a_default_that_is_not_in_the_list(self, mda_a, mda_b):
        with pytest.raises(drf.ValidationError):
            self._validate({'organizations': [{'organization': mda_a.pk}],
                            'default_organization': mda_b.pk})

    def test_rejects_an_invalid_per_org_role(self, mda_a):
        with pytest.raises(drf.ValidationError):
            self._validate({'organizations': [{'organization': mda_a.pk, 'per_org_role': 'god'}]})

    def test_omitting_organizations_is_allowed_and_leaves_the_key_absent(self):
        # Absent means "do not touch" on update, so the key must not appear.
        assert 'organizations' not in self._validate({})


@pytest.mark.django_db
class TestTenantUserLookupUsesTheUserId:
    """The list API publishes ``id = user.id`` and the UI sends that id back on
    edit / deactivate / reset-password. The viewset used to look the record up
    by the *role* row's id instead, so on any tenant where the two differ
    (every real one) those actions 404'd — or could hit another person."""

    def _viewset(self, tenant):
        from core.views.tenant_user import TenantUserViewSet

        vs = TenantUserViewSet()
        vs._get_tenant = lambda: tenant  # connection.tenant is a stub in tests
        return vs

    def test_resolves_by_user_id_even_when_it_differs_from_the_role_id(self, user):
        from tenants.models import Client, UserTenantRole

        tenant = Client.objects.get(schema_name='pytest_schema')
        # Force the two ids apart so this cannot pass by coincidence.
        role = UserTenantRole.objects.create(
            id=user.pk + 1000, user=user, tenant=tenant, role='user', is_active=True,
        )
        assert role.pk != user.pk

        assert self._viewset(tenant)._get_utr(user.pk).pk == role.pk

    def test_the_role_row_id_is_not_a_valid_handle(self, user):
        from tenants.models import Client, UserTenantRole

        tenant = Client.objects.get(schema_name='pytest_schema')
        role = UserTenantRole.objects.create(
            id=user.pk + 1000, user=user, tenant=tenant, role='user', is_active=True,
        )
        with pytest.raises(UserTenantRole.DoesNotExist):
            self._viewset(tenant)._get_utr(role.pk)

    def test_a_user_of_another_tenant_is_not_found(self, user):
        from tenants.models import Client, UserTenantRole

        tenant = Client.objects.get(schema_name='pytest_schema')
        with pytest.raises(UserTenantRole.DoesNotExist):
            self._viewset(tenant)._get_utr(user.pk)  # user has no role here


class TestOrganizationUsersEndpointIsAdminOnly:
    """It used to accept any authenticated user, so anyone could add themselves
    to an oversight MDA and inherit its cross-MDA read access."""

    def test_requires_a_tenant_admin(self):
        from core.permissions import IsTenantAdmin
        from core.views.organization import OrganizationUsers

        # Exactly this class: IsTenantAdmin already rejects anonymous users, and
        # a bare IsAuthenticated alongside it would be the regression.
        assert list(OrganizationUsers.permission_classes) == [IsTenantAdmin]


@pytest.mark.django_db
class TestCreateSerializerAcceptsWhatTheAddFormSends:
    """The Add User form does not mark first/last name as required and always
    sends them (blank when untouched); create rejected that, so adding a user
    without typing both names failed."""

    def test_blank_first_and_last_name_are_allowed(self):
        from core.serializers import TenantUserCreateSerializer

        serializer = TenantUserCreateSerializer(data={
            'username': 'blank_names_user', 'email': 'blank_names@example.com',
            'first_name': '', 'last_name': '',
            'password': 'Zx9!kQ-Pilot-Test-2026', 'role': 'user',
        })
        assert serializer.is_valid(), serializer.errors


class TestUpdateSerializerAcceptsWhatTheEditFormSends:
    """Editing a user failed for every account that has no first/last name
    (``allow_blank`` was missing, though create allows blank names)."""

    def _valid(self, payload):
        from core.serializers import TenantUserUpdateSerializer

        return TenantUserUpdateSerializer(data=payload).is_valid()

    def test_blank_first_and_last_name_are_allowed(self):
        assert self._valid({'first_name': '', 'last_name': '', 'email': 'a@b.co'}) is True

    def test_admin_still_cannot_be_granted_through_an_edit(self):
        # An edit must not be a route to promote someone to tenant admin, so the
        # modal has to leave `role` out when it has not changed.
        assert self._valid({'role': 'admin'}) is False

    def test_the_four_assignable_roles_are_accepted(self):
        for role in ('senior_manager', 'manager', 'user', 'viewer'):
            assert self._valid({'role': role}) is True


class TestOrganizationCrudIsAdminWrite:
    """Creating, renaming or deleting an MDA — including changing its
    ``org_role`` to an oversight role — used to be open to any signed-in user,
    despite the docstring saying "admin only"."""

    def _request(self, method, authenticated=True):
        from types import SimpleNamespace
        return SimpleNamespace(
            method=method, user=SimpleNamespace(is_authenticated=authenticated),
        )

    def test_both_views_use_the_read_or_admin_permission(self):
        from core.permissions import IsTenantAdminOrReadOnly
        from core.views.organization import OrganizationDetail, OrganizationListCreate

        assert list(OrganizationListCreate.permission_classes) == [IsTenantAdminOrReadOnly]
        assert list(OrganizationDetail.permission_classes) == [IsTenantAdminOrReadOnly]

    @pytest.mark.parametrize('method', ['GET', 'HEAD', 'OPTIONS'])
    def test_any_signed_in_user_may_read(self, method):
        from core.permissions import IsTenantAdminOrReadOnly

        assert IsTenantAdminOrReadOnly().has_permission(self._request(method), view=None) is True

    @pytest.mark.parametrize('method', ['POST', 'PUT', 'PATCH', 'DELETE'])
    def test_writes_require_a_tenant_admin(self, method, monkeypatch):
        from core.permissions import IsTenantAdmin, IsTenantAdminOrReadOnly

        monkeypatch.setattr(IsTenantAdmin, 'has_permission', lambda self, request, view: False)
        assert IsTenantAdminOrReadOnly().has_permission(self._request(method), view=None) is False

        monkeypatch.setattr(IsTenantAdmin, 'has_permission', lambda self, request, view: True)
        assert IsTenantAdminOrReadOnly().has_permission(self._request(method), view=None) is True

    @pytest.mark.parametrize('method', ['GET', 'POST'])
    def test_anonymous_users_get_nothing(self, method):
        from core.permissions import IsTenantAdminOrReadOnly

        assert IsTenantAdminOrReadOnly().has_permission(
            self._request(method, authenticated=False), view=None) is False


@pytest.mark.django_db
class TestUserBelongsToTenant:
    def test_a_user_with_no_role_in_the_tenant_is_not_a_member(self, user):
        from core.services.organization_assignment import user_in_tenant
        from tenants.models import Client

        assert user_in_tenant(user.pk, Client.objects.get(schema_name='pytest_schema')) is False

    def test_a_user_with_an_active_role_is_a_member(self, user):
        from core.services.organization_assignment import user_in_tenant
        from tenants.models import Client, UserTenantRole

        tenant = Client.objects.get(schema_name='pytest_schema')
        UserTenantRole.objects.create(user=user, tenant=tenant, role='user', is_active=True)
        assert user_in_tenant(user.pk, tenant) is True

    def test_a_deactivated_role_does_not_count(self, user):
        from core.services.organization_assignment import user_in_tenant
        from tenants.models import Client, UserTenantRole

        tenant = Client.objects.get(schema_name='pytest_schema')
        UserTenantRole.objects.create(user=user, tenant=tenant, role='user', is_active=False)
        assert user_in_tenant(user.pk, tenant) is False
