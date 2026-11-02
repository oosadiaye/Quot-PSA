"""Supplier/vendor name de-duplication — VendorSerializer.validate_name and the
shared helpers. A supplier must be unique by name within a tenant, compared
case- and whitespace-insensitively, on both create and rename.
"""
from __future__ import annotations

import pytest
from rest_framework import serializers as drf

from procurement.models import Vendor
from procurement.serializers import (
    VendorSerializer,
    normalize_vendor_name,
    find_duplicate_vendor,
)


def _make(name: str, code: str) -> Vendor:
    v, _ = Vendor.objects.get_or_create(code=code, defaults={'name': name, 'is_active': True})
    return v


class TestNormalize:
    def test_trims_and_collapses_internal_whitespace(self):
        assert normalize_vendor_name('  ABC   Ltd  ') == 'ABC Ltd'
        assert normalize_vendor_name('ABC Ltd') == 'ABC Ltd'

    def test_blank_inputs_become_empty(self):
        assert normalize_vendor_name('') == ''
        assert normalize_vendor_name('   ') == ''
        assert normalize_vendor_name(None) == ''  # type: ignore[arg-type]


@pytest.mark.django_db
class TestValidateName:
    def test_exact_duplicate_is_rejected(self):
        _make('ABC Ltd', 'V1')
        with pytest.raises(drf.ValidationError):
            VendorSerializer().validate_name('ABC Ltd')

    def test_duplicate_is_case_and_whitespace_insensitive(self):
        _make('ABC Ltd', 'V1')
        for variant in ['abc ltd', 'AbC lTd', 'ABC  Ltd', '  ABC Ltd  ']:
            with pytest.raises(drf.ValidationError):
                VendorSerializer().validate_name(variant)

    def test_distinct_name_passes_and_is_returned_normalised(self):
        _make('ABC Ltd', 'V1')
        assert VendorSerializer().validate_name('  XYZ   Corp ') == 'XYZ Corp'

    def test_blank_name_is_rejected(self):
        with pytest.raises(drf.ValidationError):
            VendorSerializer().validate_name('   ')

    def test_error_message_names_the_existing_supplier(self):
        _make('ABC Ltd', 'ACME-01')
        with pytest.raises(drf.ValidationError) as exc:
            VendorSerializer().validate_name('abc ltd')
        text = str(exc.value)
        assert 'ABC Ltd' in text and 'ACME-01' in text

    def test_rename_keeping_own_name_does_not_collide_with_self(self):
        v = _make('ABC Ltd', 'V1')
        assert VendorSerializer(instance=v).validate_name('ABC Ltd') == 'ABC Ltd'

    def test_rename_onto_another_supplier_is_rejected(self):
        _make('ABC Ltd', 'V1')
        other = _make('XYZ Corp', 'V2')
        with pytest.raises(drf.ValidationError):
            VendorSerializer(instance=other).validate_name('abc ltd')


@pytest.mark.django_db
class TestFindDuplicateHelper:
    def test_matches_case_insensitively(self):
        v = _make('ABC Ltd', 'V1')
        assert find_duplicate_vendor('abc ltd') == v

    def test_exclude_pk_skips_that_vendor(self):
        v = _make('ABC Ltd', 'V1')
        assert find_duplicate_vendor('abc ltd', exclude_pk=v.pk) is None

    def test_no_match_returns_none(self):
        _make('ABC Ltd', 'V1')
        assert find_duplicate_vendor('nobody here') is None
        assert find_duplicate_vendor('') is None
