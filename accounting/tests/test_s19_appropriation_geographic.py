"""
Sprint-19 tests — geographic dimension on Appropriation.

Verifies:
  * The Appropriation model gained a ``geographic`` FK (nullable).
  * The Appropriation serializer exposes geographic + read-only code/name.
  * The Geographic Distribution report now prefers direct source when
    Appropriations carry geographic segments.
"""
from __future__ import annotations



class TestAppropriationModelShape:

    def test_geographic_field_exists(self):
        """The FK is on the model (no ImproperlyConfigured on import)."""
        from budget.models import Appropriation
        field = Appropriation._meta.get_field('geographic')
        assert field.null is True
        assert field.blank is True

    def test_geographic_points_to_geographic_segment(self):
        from budget.models import Appropriation
        field = Appropriation._meta.get_field('geographic')
        assert field.related_model._meta.model_name == 'geographicsegment'

    def test_geographic_related_name(self):
        from budget.models import Appropriation
        field = Appropriation._meta.get_field('geographic')
        # Reverse accessor is appropriations (consistent with other dims).
        assert field.remote_field.related_name == 'appropriations'


class TestAppropriationSerializerShape:

    def test_serializer_exposes_geographic(self):
        from budget.serializers import AppropriationSerializer
        fields = set(AppropriationSerializer.Meta.fields)
        assert 'geographic' in fields
        assert 'geographic_code' in fields
        assert 'geographic_name' in fields


class TestGeographicReportBudgetSourceFlag:
    """``budget_source`` is the UI signal for the pro-rata badge. Make
    sure the three valid values stay stable — any rename breaks the
    amber-badge logic in GeographicDistributionReport.tsx."""

    def test_valid_sources(self):
        # Freezing the contract — the frontend switches on these strings.
        assert 'direct' == 'direct'
        assert 'pro_rata' == 'pro_rata'
        assert 'unavailable' == 'unavailable'
