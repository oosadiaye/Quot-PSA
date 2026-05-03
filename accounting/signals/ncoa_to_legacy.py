"""
Forward sync: every NCoA segment save auto-creates the legacy bridge.

Why this exists
---------------
The Journal Entry form, Voucher form, Asset form, and several other
pre-NCoA UIs still query the legacy dimension endpoints
(``/accounting/funds/``, ``/accounting/programs/``, ``/accounting/mdas/``,
etc.) because their parent models (``JournalHeader``, ``PaymentVoucher``,
``FixedAsset``, …) carry FKs to the legacy ``MDA``/``Fund``/``Function``/
``Program``/``Geo`` tables. The NCoA segments are the *authoritative*
catalogue, but the legacy tables remain the FK targets until those models
are refactored.

Without this signal, freshly-imported NCoA segments produce empty legacy
dropdowns, and forms that depend on them silently fail validation.

What it does
------------
For each NCoA segment type (Administrative, Fund, Functional, Programme,
Geographic), on every create / update:

1. If the segment already has its ``legacy_*`` bridge populated, do nothing.
2. Otherwise, ``get_or_create`` the matching legacy row keyed by ``code``
   (truncated to fit the legacy column's ``max_length``), then attach the
   bridge via the OneToOneField.

The legacy ``name`` columns are bounded (varchar(100/200)); we silently
truncate so a single oversized name (long ministry titles, multi-line
programme descriptions) doesn't prevent the bridge from forming. The
authoritative full name remains on the NCoA segment.

Re-entrancy
-----------
The signal only writes to legacy tables and the segment's own
``legacy_*_id`` field; it never touches another NCoA segment. The save
that updates ``legacy_*_id`` re-triggers this same signal, but the
``if seg.legacy_*_id`` short-circuit makes that a no-op (it skips the
get_or_create and returns immediately).

Opt-out
-------
Set ``segment._skip_legacy_sync = True`` before calling ``save()`` to
suppress the bridge for that one row. Useful inside the
``backfill_legacy_dims`` management command (which calls the bridge
logic directly and doesn't want recursive saves) and inside test fixtures.

Failure mode
------------
Bridge failures are logged and swallowed — they never roll back the
NCoA segment save. The legacy table is a display convenience; the
authoritative data is the NCoA segment itself.
"""
from __future__ import annotations

import logging
from typing import Type

from django.db import transaction
from django.db.models import Model
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounting.models import Fund, Function, Program, Geo, MDA
from accounting.models.ncoa import (
    AdministrativeSegment,
    FundSegment,
    FunctionalSegment,
    ProgrammeSegment,
    GeographicSegment,
)


logger = logging.getLogger(__name__)


# MDA.mda_type is required with constrained choices. NCoA's mda_type has
# overlapping but not identical values; fall back to MINISTRY at the
# sector root where no specific classification was supplied.
_VALID_MDA_TYPES = {'MINISTRY', 'DEPARTMENT', 'AGENCY', 'PARASTATAL'}


def _fit(value: str | None, max_length: int) -> str:
    """Truncate ``value`` to ``max_length`` chars, returning '' for None."""
    v = value or ''
    return v if len(v) <= max_length else v[:max_length]


def _bridge(
    *,
    segment: Model,
    legacy_model: Type[Model],
    legacy_attr: str,
    extra_defaults: dict | None = None,
) -> None:
    """
    Generic NCoA → legacy bridge.

    Looks up or creates the legacy row keyed by ``code`` (length-clamped),
    then attaches it to ``segment`` via the OneToOneField named
    ``legacy_attr``. Idempotent — safe to call on every save.
    """
    if getattr(segment, '_skip_legacy_sync', False):
        return
    if getattr(segment, f'{legacy_attr}_id', None):
        return  # bridge already in place

    code_max = legacy_model._meta.get_field('code').max_length
    name_max = legacy_model._meta.get_field('name').max_length

    defaults = {
        'name': _fit(getattr(segment, 'name', ''), name_max),
        'is_active': getattr(segment, 'is_active', True),
    }
    # ``description`` is optional on the legacy models — only include it
    # when the field exists, so we don't break any legacy schema that
    # dropped it.
    if any(f.name == 'description' for f in legacy_model._meta.fields):
        defaults['description'] = getattr(segment, 'description', '') or ''
    if extra_defaults:
        defaults.update(extra_defaults)

    with transaction.atomic():
        legacy_row, _created = legacy_model.objects.get_or_create(
            code=_fit(getattr(segment, 'code', ''), code_max),
            defaults=defaults,
        )
        # Attach via update() rather than save() so this update never
        # re-triggers our own post_save handler (defence-in-depth even
        # though the early-return above already prevents the recursion).
        type(segment).objects.filter(pk=segment.pk).update(
            **{f'{legacy_attr}_id': legacy_row.pk},
        )


def _safe(fn):
    """Decorator: log + swallow exceptions so signal failures never roll back the NCoA save."""
    def wrapper(sender, instance, **kwargs):
        try:
            fn(sender, instance, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                'NCoA → legacy bridge failed for %s id=%s code=%r: %s',
                sender.__name__, getattr(instance, 'pk', None),
                getattr(instance, 'code', None), exc, exc_info=True,
            )
    wrapper.__name__ = fn.__name__
    return wrapper


# ── Administrative → MDA ─────────────────────────────────────────────
@receiver(post_save, sender=AdministrativeSegment,
          dispatch_uid='accounting.ncoa_to_legacy.administrative')
@_safe
def _mirror_admin(sender, instance: AdministrativeSegment, **kwargs):
    source_type = (getattr(instance, 'mda_type', '') or '').upper()
    mda_type = source_type if source_type in _VALID_MDA_TYPES else 'MINISTRY'
    _bridge(
        segment=instance,
        legacy_model=MDA,
        legacy_attr='legacy_mda',
        extra_defaults={
            'mda_type': mda_type,
            'short_name': _fit(instance.name, MDA._meta.get_field('short_name').max_length),
        },
    )


# ── Fund → Fund ──────────────────────────────────────────────────────
@receiver(post_save, sender=FundSegment,
          dispatch_uid='accounting.ncoa_to_legacy.fund')
@_safe
def _mirror_fund(sender, instance: FundSegment, **kwargs):
    _bridge(segment=instance, legacy_model=Fund, legacy_attr='legacy_fund')


# ── Functional → Function ────────────────────────────────────────────
@receiver(post_save, sender=FunctionalSegment,
          dispatch_uid='accounting.ncoa_to_legacy.functional')
@_safe
def _mirror_functional(sender, instance: FunctionalSegment, **kwargs):
    _bridge(segment=instance, legacy_model=Function, legacy_attr='legacy_function')


# ── Programme → Program ──────────────────────────────────────────────
@receiver(post_save, sender=ProgrammeSegment,
          dispatch_uid='accounting.ncoa_to_legacy.programme')
@_safe
def _mirror_programme(sender, instance: ProgrammeSegment, **kwargs):
    _bridge(segment=instance, legacy_model=Program, legacy_attr='legacy_program')


# ── Geographic → Geo ─────────────────────────────────────────────────
@receiver(post_save, sender=GeographicSegment,
          dispatch_uid='accounting.ncoa_to_legacy.geographic')
@_safe
def _mirror_geographic(sender, instance: GeographicSegment, **kwargs):
    _bridge(segment=instance, legacy_model=Geo, legacy_attr='legacy_geo')


def _connect_signals() -> None:
    """No-op — receivers above are attached at import time via @receiver.

    Kept as a stable hook for ``apps.py`` to call, mirroring the pattern
    used by ``coa_to_ncoa._connect_signals()``.
    """
    return
