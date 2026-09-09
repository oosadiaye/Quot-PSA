"""OrganizationFilterMixin — the MDA isolation boundary.

Ten ViewSets across accounting, budget, contracts, procurement and hrm
inherit this mixin, and it is the only thing standing between an operator
in one MDA and another MDA's records. Before this file the behaviour had
no direct test at all: the branches were exercised only incidentally, and
a wrong turn in any of them fails open rather than loudly.

No database — the mixin's job is to decide WHICH filter to apply, so a
recording stand-in for the queryset proves the decision without paying
for a schema.
"""
from __future__ import annotations

import pytest

from core.mixins import OrganizationFilterMixin


class _FakeQuerySet:
    """Records what the mixin asked for instead of hitting a database."""

    def __init__(self):
        self.filtered_with = None
        self.was_emptied = False

    def filter(self, **kwargs):
        self.filtered_with = kwargs
        return self

    def none(self):
        self.was_emptied = True
        return self


class _FakeOrg:
    def __init__(self, *, cross_mda=False, admin_id=None, legacy_id=None):
        self.has_cross_mda_read = cross_mda
        self.administrative_segment_id = admin_id
        self.legacy_mda_id = legacy_id


class _FakeRequest:
    def __init__(self, mode, org):
        self.mda_isolation_mode = mode
        self.organization = org


def _view(mode='SEPARATED', org=None, field=None, admin_field=None):
    view = OrganizationFilterMixin()
    view.org_filter_field = field
    view.org_filter_admin_field = admin_field
    view.request = _FakeRequest(mode, org)
    return view


@pytest.mark.unit
class TestUnifiedMode:

    def test_returns_everything_untouched(self):
        qs = _FakeQuerySet()
        out = _view(mode='UNIFIED').apply_org_filter(qs, field='mda')
        assert out is qs
        assert qs.filtered_with is None
        assert not qs.was_emptied


@pytest.mark.unit
class TestSeparatedMode:

    def test_no_organization_sees_nothing(self):
        """Fail closed. An unresolved org must not mean 'see everything'."""
        qs = _FakeQuerySet()
        _view(org=None).apply_org_filter(qs, field='mda')
        assert qs.was_emptied

    def test_oversight_org_reads_across_mdas(self):
        """Budget / Finance / Audit legitimately see every MDA."""
        qs = _FakeQuerySet()
        org = _FakeOrg(cross_mda=True, admin_id=7)
        out = _view(org=org).apply_org_filter(qs, field='mda')
        assert out is qs
        assert qs.filtered_with is None

    def test_admin_segment_filter_wins_when_both_are_available(self):
        qs = _FakeQuerySet()
        org = _FakeOrg(admin_id=7, legacy_id=99)
        _view(org=org).apply_org_filter(
            qs, field='mda', admin_field='administrative')
        assert qs.filtered_with == {'administrative_id': 7}

    def test_falls_back_to_the_legacy_mda_field(self):
        qs = _FakeQuerySet()
        org = _FakeOrg(admin_id=None, legacy_id=99)
        _view(org=org).apply_org_filter(
            qs, field='mda', admin_field='administrative')
        assert qs.filtered_with == {'mda_id': 99}

    def test_reference_data_with_no_field_declared_is_unfiltered(self):
        """Currencies, tax codes and the like belong to no single MDA."""
        qs = _FakeQuerySet()
        org = _FakeOrg(admin_id=7, legacy_id=99)
        out = _view(org=org).apply_org_filter(qs)
        assert out is qs
        assert qs.filtered_with is None

    def test_traversal_paths_are_passed_through_verbatim(self):
        """PaymentViewSet filters through allocations__invoice__mda."""
        qs = _FakeQuerySet()
        org = _FakeOrg(legacy_id=99)
        _view(org=org).apply_org_filter(
            qs, field='allocations__invoice__mda')
        assert qs.filtered_with == {'allocations__invoice__mda_id': 99}


@pytest.mark.unit
class TestCustomActionsCanReuseTheDecision:
    """Why apply_org_filter was extracted from get_queryset.

    A custom action that builds its own queryset — an eligibility picker,
    a report feed — gets no filtering from ``get_queryset`` and must call
    this directly with the field path for ITS model. The payment-batch
    eligible_payments picker was returning every MDA's payments for
    exactly this reason.
    """

    def test_a_different_field_path_than_the_viewset_default(self):
        qs = _FakeQuerySet()
        org = _FakeOrg(legacy_id=99)
        view = _view(org=org, field='lines__payment__allocations__invoice__mda')

        # The action passes the Payment-shaped path, not the batch-shaped
        # one declared on the class.
        view.apply_org_filter(qs, field='allocations__invoice__mda')
        assert qs.filtered_with == {'allocations__invoice__mda_id': 99}


@pytest.mark.unit
class TestMissingRequest:

    def test_no_request_is_a_no_op(self):
        """Schema generation and shell use instantiate views without one."""
        qs = _FakeQuerySet()
        view = OrganizationFilterMixin()
        view.org_filter_field = 'mda'
        view.org_filter_admin_field = None
        out = view.apply_org_filter(qs, field='mda')
        assert out is qs
        assert not qs.was_emptied
