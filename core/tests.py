from datetime import timedelta

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from rest_framework import status

from core.authentication import ExpiringTokenAuthentication


class AuthenticationTests(TestCase):
    """Tests for centralized login, logout, and token authentication."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser', password='TestPass123!', email='test@example.com'
        )

    def test_login_success(self):
        response = self.client.post('/api/core/auth/login/', {
            'username': 'testuser',
            'password': 'TestPass123!'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('token', response.data)
        self.assertIn('user', response.data)
        self.assertIn('tenants', response.data)

    def test_login_returns_tenant_list(self):
        """Login response includes the user's available tenants."""
        response = self.client.post('/api/core/auth/login/', {
            'username': 'testuser',
            'password': 'TestPass123!'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data['tenants'], list)

    def test_login_invalid_credentials(self):
        response = self.client.post('/api/core/auth/login/', {
            'username': 'testuser',
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_missing_fields(self):
        response = self.client.post('/api/core/auth/login/', {
            'username': 'testuser'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_disabled_account(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.post('/api/core/auth/login/', {
            'username': 'testuser',
            'password': 'TestPass123!'
        })
        # PublicSchemaBackend returns None for inactive users
        self.assertIn(response.status_code, [
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN
        ])

    def test_logout_deletes_token(self):
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        response = self.client.post('/api/core/auth/logout/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_login_replaces_old_token(self):
        old_token = Token.objects.create(user=self.user)
        old_key = old_token.key
        response = self.client.post('/api/core/auth/login/', {
            'username': 'testuser',
            'password': 'TestPass123!'
        })
        new_key = response.data['token']
        self.assertNotEqual(old_key, new_key)
        self.assertEqual(Token.objects.filter(user=self.user).count(), 1)


class ExpiringTokenTests(TestCase):
    """Tests for token expiration."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='tokenuser', password='TestPass123!'
        )
        self.auth = ExpiringTokenAuthentication()

    def test_valid_token(self):
        token = Token.objects.create(user=self.user)
        user, auth_token = self.auth.authenticate_credentials(token.key)
        self.assertEqual(user, self.user)

    def test_expired_token(self):
        token = Token.objects.create(user=self.user)
        Token.objects.filter(pk=token.pk).update(
            created=timezone.now() - timedelta(hours=25)
        )
        token.refresh_from_db()
        from rest_framework.exceptions import AuthenticationFailed
        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate_credentials(token.key)

    def test_inactive_user_token(self):
        token = Token.objects.create(user=self.user)
        self.user.is_active = False
        self.user.save()
        from rest_framework.exceptions import AuthenticationFailed
        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate_credentials(token.key)


class RBACPermissionTests(TestCase):
    """Tests for RBAC permission class."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='rbacuser', password='TestPass123!'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

    def test_authenticated_user_can_access_me_endpoint(self):
        response = self.client.get('/api/core/users/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'rbacuser')

    def test_me_endpoint_returns_tenants(self):
        """The /me/ endpoint returns the user's tenant list."""
        response = self.client.get('/api/core/users/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('tenants', response.data)

    def test_unauthenticated_cannot_access_users(self):
        client = APIClient()
        response = client.get('/api/core/users/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserSerializerTests(TestCase):
    """Tests for user serializer security."""

    def setUp(self):
        self.client = APIClient()
        self.regular_user = User.objects.create_user(
            username='regular', password='TestPass123!'
        )
        self.admin_user = User.objects.create_superuser(
            username='admin', password='AdminPass123!', email='admin@test.com'
        )

    def test_regular_user_cannot_see_is_superuser(self):
        token = Token.objects.create(user=self.regular_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        response = self.client.get('/api/core/users/me/')
        self.assertNotIn('is_superuser', response.data)

    def test_admin_can_see_is_superuser(self):
        token = Token.objects.create(user=self.admin_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        response = self.client.get('/api/core/users/me/')
        self.assertIn('is_superuser', response.data)


class ChangePasswordTests(TestCase):
    """Tests for password change endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='pwuser', password='OldPass123!'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

    def test_change_password_success(self):
        response = self.client.post('/api/core/users/change_password/', {
            'old_password': 'OldPass123!',
            'new_password': 'NewPass456!'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass456!'))

    def test_change_password_wrong_old(self):
        response = self.client.post('/api/core/users/change_password/', {
            'old_password': 'WrongPass!',
            'new_password': 'NewPass456!'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TenantSelectionTests(TestCase):
    """Tests for tenant selection / switching endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='tenantuser', password='TestPass123!'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

    def test_my_tenants_returns_list(self):
        response = self.client.get('/api/core/auth/my-tenants/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('tenants', response.data)
        self.assertIsInstance(response.data['tenants'], list)

    def test_select_tenant_requires_tenant_id(self):
        response = self.client.post('/api/core/auth/select-tenant/', {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_select_nonexistent_tenant(self):
        response = self.client.post('/api/core/auth/select-tenant/', {
            'tenant_id': 99999
        })
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_cannot_select_tenant(self):
        client = APIClient()
        response = client.post('/api/core/auth/select-tenant/', {
            'tenant_id': 1
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_cannot_list_tenants(self):
        client = APIClient()
        response = client.get('/api/core/auth/my-tenants/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
