"""Tests for HRM PII at-rest encryption.

Covers the crypto primitives, the Employee accessors, the dual-state
flag, and the hash-based lookup path.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from core.security.pii_crypto import decrypt_pii, encrypt_pii, pii_hash
from hrm.models import Department, Employee, Position


pytestmark = pytest.mark.django_db


# ── Pure-crypto tests ─────────────────────────────────────────────────


def test_encrypt_then_decrypt_roundtrip():
    plaintext = 'A12345678901'
    token = encrypt_pii(plaintext)
    assert token != plaintext
    assert token.startswith('v2:')  # HKDF v2 envelope prefix
    assert decrypt_pii(token) == plaintext


def test_encrypt_empty_returns_empty():
    assert encrypt_pii('') == ''
    assert encrypt_pii(None) == ''  # type: ignore[arg-type]
    assert decrypt_pii('') == ''


def test_pii_hash_normalisation():
    assert pii_hash('AB-123') == pii_hash('ab123')
    assert pii_hash('  ab 123  ') == pii_hash('AB123')


def test_pii_hash_empty():
    assert pii_hash('') == ''
    assert pii_hash(None) == ''  # type: ignore[arg-type]


def test_pii_hash_distinguishes_distinct_inputs():
    assert pii_hash('A12345678901') != pii_hash('A12345678902')


# ── Accessor + DB tests ───────────────────────────────────────────────


@pytest.fixture
def employee(db):
    user = User.objects.create_user(username='pii_user', password='x')
    dept = Department.objects.create(name='Test Dept', code='TD-PII')
    pos = Position.objects.create(title='Tester', code='TST', department=dept, grade='Mid')
    return Employee.objects.create(
        user=user,
        employee_number='EMP-PII-001',
        department=dept,
        position=pos,
        hire_date='2025-01-01',
    )


@pytest.fixture
def pii_search_actor(db):
    """A superuser actor used to invoke the gated PII hash search."""
    return User.objects.create_superuser(username='pii_searcher', password='x', email='ps@example.com')


def test_set_then_get_roundtrip(employee):
    employee.set_national_id_number('A12345678901')
    employee.save()
    employee.refresh_from_db()
    assert employee.get_national_id_number() == 'A12345678901'
    assert employee.national_id_number_encrypted is True


def test_find_by_pii_hash(employee, pii_search_actor):
    employee.set_national_id_number('A12345678901')
    employee.save()
    qs = Employee.find_by_pii_hash(
        'national_id_number', 'A12345678901', actor=pii_search_actor,
    )
    assert qs.count() == 1
    assert qs.first().pk == employee.pk


def test_find_by_pii_hash_normalised(employee, pii_search_actor):
    """Hash lookup should respect the same lower/strip/alphanum normalisation."""
    employee.set_national_id_number('A12345678901')
    employee.save()
    qs = Employee.find_by_pii_hash(
        'national_id_number', 'a-1234-5678-901', actor=pii_search_actor,
    )
    assert qs.count() == 1


def test_find_by_pii_hash_rejects_non_searchable(employee, pii_search_actor):
    with pytest.raises(ValueError):
        Employee.find_by_pii_hash(
            'social_security_number', '123', actor=pii_search_actor,
        )


def test_ciphertext_at_rest(employee):
    employee.set_national_id_number('A12345678901')
    employee.save()
    employee.refresh_from_db()
    raw = employee.national_id_number
    assert raw.startswith('v2:'), f'expected v2 envelope, got {raw!r}'
    assert 'A12345678901' not in raw


def test_set_empty_clears_flag_and_hash(employee):
    employee.set_national_id_number('A12345678901')
    employee.save()
    employee.refresh_from_db()
    assert employee.national_id_number_encrypted is True
    assert employee.national_id_number_hash != ''

    employee.set_national_id_number('')
    employee.save()
    employee.refresh_from_db()
    assert employee.national_id_number == ''
    assert employee.national_id_number_encrypted is False
    assert employee.national_id_number_hash == ''


def test_get_returns_plaintext_when_flag_false(employee):
    """Dual-state read: pre-backfill rows are still plaintext."""
    # Simulate a pre-backfill row by writing the column directly.
    employee.national_id_number = 'PLAIN-VALUE'
    employee.national_id_number_encrypted = False
    employee.save()
    employee.refresh_from_db()
    assert employee.get_national_id_number() == 'PLAIN-VALUE'


def test_all_five_fields_roundtrip(employee):
    samples = {
        'national_id_number': 'NIN-001',
        'tax_identification_number': 'TIN-002',
        'social_security_number': 'SSN-003',
        'bank_account': '0123456789',
        'bank_routing': '044150149',
    }
    for field, value in samples.items():
        getattr(employee, f'set_{field}')(value)
    employee.save()
    employee.refresh_from_db()
    for field, value in samples.items():
        assert getattr(employee, f'get_{field}')() == value
        assert getattr(employee, f'{field}_encrypted') is True
        # Raw column is v2-envelope ciphertext, not plaintext.
        assert getattr(employee, field).startswith('v2:')
