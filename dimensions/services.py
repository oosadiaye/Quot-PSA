"""
Tagging rules and the dimension report.

Every write goes through ``set_tags`` so the rules are in one place: the dimension is switched on for the record type,
the value belongs to it and is active, a child value sits under the tagged parent, mandatory dimensions are present,
and a posted record is never re-tagged. Refusals are ``DimensionError`` with the reason, for the API to return as a 409.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Optional

from django.db import transaction
from django.db.models import Count, OuterRef, Subquery, Sum

from .models import RECORD_TYPES, DimensionTag, DimensionType, DimensionValue

UNTAGGED = '(untagged)'
POSTED = 'Posted'


class DimensionError(Exception):
    """A tag the rules refuse; the message is meant for the person using the form."""


def _is_locked(record_type: str, record_id: int) -> bool:
    """A posted ledger line is history. Other record types gain their lock here when they are wired in."""
    if record_type == 'journal_line':
        from accounting.models import JournalLine
        line = JournalLine.objects.select_related('header').filter(pk=record_id).first()
        return bool(line and line.header.status == POSTED)
    return False


def get_tags(record_type: str, record_id: int) -> dict[str, str]:
    rows = DimensionTag.objects.filter(record_type=record_type, record_id=record_id).select_related(
        'dimension_type', 'value')
    return {t.dimension_type.code: t.value.code for t in rows}


def _resolve_type(record_type: str, code: str) -> DimensionType:
    dimension = DimensionType.objects.filter(code=code).select_related('parent_type').first()
    if dimension is None:
        raise DimensionError(f"Unknown dimension '{code}'.")
    if not dimension.is_active:
        raise DimensionError(f'{dimension.name} is inactive.')
    if record_type not in (dimension.applies_to or []):
        raise DimensionError(f'{dimension.name} is not switched on for {record_type.replace("_", " ")}s.')
    return dimension


def _resolve_value(dimension: DimensionType, code: str) -> DimensionValue:
    value = DimensionValue.objects.filter(dimension_type=dimension, code=code).select_related('parent').first()
    if value is None:
        raise DimensionError(f"Unknown value '{code}' for {dimension.name}.")
    if not value.is_active:
        raise DimensionError(f"Value '{code}' of {dimension.name} is inactive.")
    return value


def _check_parentage(resolved: Mapping[str, tuple[DimensionType, DimensionValue]]) -> None:
    for dimension, value in resolved.values():
        parent_type = dimension.parent_type
        if parent_type is None or parent_type.code not in resolved or value.parent_id is None:
            continue
        tagged_parent = resolved[parent_type.code][1]
        if value.parent_id != tagged_parent.pk:
            raise DimensionError(
                f"{dimension.name} '{value.code}' is not in {parent_type.name} '{tagged_parent.code}'.")


def _check_required(record_type: str, codes) -> None:
    for dimension in DimensionType.objects.filter(is_active=True):
        if record_type in (dimension.required_on or []) and dimension.code not in codes:
            raise DimensionError(f'{dimension.name} is required on {record_type.replace("_", " ")}s.')


@transaction.atomic
def set_tags(record_type: str, record_id: int, tags: Mapping[str, str]) -> dict[str, str]:
    """Replace the record's tags with ``{dimension code: value code}``, or refuse the whole change."""
    if record_type not in RECORD_TYPES:
        raise DimensionError(f"Unknown record type '{record_type}'.")
    if _is_locked(record_type, record_id):
        raise DimensionError('This record is posted; its dimensions can no longer change.')
    resolved = {}
    for code, value_code in tags.items():
        dimension = _resolve_type(record_type, code)
        resolved[code] = (dimension, _resolve_value(dimension, value_code))
    _check_parentage(resolved)
    _check_required(record_type, resolved)
    DimensionTag.objects.filter(record_type=record_type, record_id=record_id).delete()
    DimensionTag.objects.bulk_create([
        DimensionTag(record_type=record_type, record_id=record_id, dimension_type=d, value=v)
        for d, v in resolved.values()])
    return get_tags(record_type, record_id)


def apply_default_to_journal(header_id: int, tags: Mapping[str, str]) -> None:
    """A journal-level choice fills each unposted line for the dimensions the line has no value of its own for."""
    from accounting.models import JournalLine
    for line in JournalLine.objects.filter(header_id=header_id):
        own = get_tags('journal_line', line.pk)
        merged = {**tags, **own}
        if merged != own:
            set_tags('journal_line', line.pk, merged)


def dimension_report(
    type_code: str,
    parent_value: Optional[str] = None,
    date_from=None,
    date_to=None,
    account_type: str = 'Expense',
) -> dict:
    """Posted ledger lines of one account type totalled by value of the dimension, with the untagged remainder.

    ``parent_value`` drills down: only the values under that value of the parent dimension, and no untagged row."""
    from accounting.models import JournalLine
    dimension = DimensionType.objects.select_related('parent_type').filter(code=type_code).first()
    if dimension is None:
        raise DimensionError(f"Unknown dimension '{type_code}'.")
    lines = JournalLine.objects.filter(
        header__status=POSTED, header__is_deleted=False, account__account_type=account_type)
    if date_from:
        lines = lines.filter(header__posting_date__gte=date_from)
    if date_to:
        lines = lines.filter(header__posting_date__lte=date_to)
    tagged_value = DimensionTag.objects.filter(
        record_type='journal_line', dimension_type=dimension, record_id=OuterRef('pk')).values('value_id')[:1]
    totals = {
        row['dv']: row for row in lines.annotate(dv=Subquery(tagged_value)).values('dv').annotate(
            debit=Sum('debit'), credit=Sum('credit'), lines=Count('id'))}

    values = DimensionValue.objects.filter(dimension_type=dimension)
    if parent_value is not None:
        values = values.filter(parent__code=parent_value, parent__dimension_type=dimension.parent_type)

    def row(code: str, name: str, key) -> dict:
        t = totals.get(key) or {}
        debit, credit = t.get('debit') or Decimal('0'), t.get('credit') or Decimal('0')
        return {'code': code, 'name': name, 'debit': str(debit), 'credit': str(credit),
                'net': str(debit - credit), 'lines': t.get('lines', 0)}

    rows = [row(v.code, v.name, v.pk) for v in values]
    if parent_value is None:
        rows.append(row(UNTAGGED, 'Not tagged', None))
    return {'dimension': dimension.code, 'name': dimension.name, 'account_type': account_type, 'rows': rows}
