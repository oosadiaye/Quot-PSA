"""
Seed NCoA Segments as Legacy Dimension Records
================================================
Creates legacy Fund/Function/Program/Geo/MDA records from NCoA segments
and links them via the bridge FKs (legacy_fund, legacy_function, etc.).

This ensures:
1. Legacy JournalHeader FKs (fund, function, program, geo, mda) stay populated
2. Legacy GLBalance queries continue working
3. Legacy Dimensions UI shows NCoA-aligned data
4. Budget queries using legacy dimensions still function

Run: python manage.py seed_ncoa_as_dimensions
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from accounting.models.gl import Fund, Function, Program, Geo, MDA
from accounting.models.ncoa import (
    FundSegment, FunctionalSegment, ProgrammeSegment,
    GeographicSegment, AdministrativeSegment,
)


class Command(BaseCommand):
    help = 'Sync NCoA segments to legacy dimension records (Fund/Function/Program/Geo/MDA)'

    @transaction.atomic
    def handle(self, *args, **options):
        totals = {}

        # Fund Segment -> Fund
        totals['fund'] = self._sync_segment(
            FundSegment, Fund, 'legacy_fund',
            lambda seg: {'code': seg.code, 'name': seg.name, 'description': seg.description, 'is_active': seg.is_active},
        )

        # Functional Segment -> Function
        totals['function'] = self._sync_segment(
            FunctionalSegment, Function, 'legacy_function',
            lambda seg: {'code': seg.code, 'name': seg.name, 'description': getattr(seg, 'description', ''), 'is_active': seg.is_active},
        )

        # Programme Segment -> Program
        totals['program'] = self._sync_segment(
            ProgrammeSegment, Program, 'legacy_program',
            lambda seg: {'code': seg.code, 'name': seg.name, 'description': getattr(seg, 'description', ''), 'is_active': seg.is_active},
        )

        # Geographic Segment -> Geo
        totals['geo'] = self._sync_segment(
            GeographicSegment, Geo, 'legacy_geo',
            lambda seg: {'code': seg.code, 'name': seg.name, 'description': getattr(seg, 'description', ''), 'is_active': seg.is_active},
        )

        # Administrative Segment -> MDA
        totals['mda'] = self._sync_admin_to_mda()

        self.stdout.write(self.style.SUCCESS(
            '\nNCoA -> Dimensions bridge complete:\n'
            + '\n'.join(f'  {k}: {v} synced' for k, v in totals.items())
        ))

    def _sync_segment(self, ncoa_model, legacy_model, bridge_field, defaults_fn):
        """Generic sync: for each NCoA segment, create/link a legacy dimension record."""
        count = 0
        for seg in ncoa_model.objects.all():
            # Already linked?
            if getattr(seg, bridge_field) is not None:
                # Update existing
                legacy = getattr(seg, bridge_field)
                defaults = defaults_fn(seg)
                for k, v in defaults.items():
                    setattr(legacy, k, v)
                legacy.save()
                count += 1
                continue

            # Check if legacy record with same code exists
            defaults = defaults_fn(seg)
            existing = legacy_model.objects.filter(code=seg.code).first()
            if existing:
                setattr(seg, bridge_field, existing)
                seg.save(update_fields=[bridge_field])
                # Update legacy record to match NCoA
                for k, v in defaults.items():
                    setattr(existing, k, v)
                existing.save()
                count += 1
                continue

            # Create new legacy record
            legacy_obj = legacy_model.objects.create(**defaults)
            setattr(seg, bridge_field, legacy_obj)
            seg.save(update_fields=[bridge_field])
            count += 1

        return count

    def _sync_admin_to_mda(self):
        """Sync AdministrativeSegment -> MDA with type mapping."""
        count = 0
        MDA_TYPE_MAP = {
            'MINISTRY': 'MINISTRY',
            'DEPARTMENT': 'DEPARTMENT',
            'AGENCY': 'AGENCY',
            'UNIT': 'UNIT',
        }

        for seg in AdministrativeSegment.objects.all():
            if seg.legacy_mda is not None:
                # Update existing
                mda = seg.legacy_mda
                mda.name = seg.name
                mda.short_name = seg.short_name or ''
                mda.is_active = seg.is_active
                mda.mda_type = MDA_TYPE_MAP.get(seg.mda_type, '') if seg.mda_type else ''
                mda.save()
                count += 1
                continue

            existing = MDA.objects.filter(code=seg.code).first()
            if existing:
                seg.legacy_mda = existing
                seg.save(update_fields=['legacy_mda'])
                existing.name = seg.name
                existing.short_name = seg.short_name or ''
                existing.is_active = seg.is_active
                existing.save()
                count += 1
                continue

            mda = MDA.objects.create(
                code=seg.code,
                name=seg.name,
                short_name=seg.short_name or '',
                mda_type=MDA_TYPE_MAP.get(seg.mda_type, '') if seg.mda_type else '',
                is_active=seg.is_active,
            )
            seg.legacy_mda = mda
            seg.save(update_fields=['legacy_mda'])
            count += 1

        return count
