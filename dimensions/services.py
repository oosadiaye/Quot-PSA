"""
Tagging rules and the dimension report.

Every write goes through ``set_tags`` so the rules are in one place: the dimension is switched on for the record type,
the value belongs to it and is active, a child value sits under the tagged parent, mandatory dimensions are present,
and a posted record is never re-tagged. Refusals are ``DimensionError`` with the reason, for the API to return as a 409.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Optional

from django.db import IntegrityError, transaction
from django.db.models import Count, OuterRef, Subquery, Sum

from .models import RECORD_TYPES, DimensionTag, DimensionType, DimensionValue

UNTAGGED = '(untagged)'
POSTED = 'Posted'


class DimensionError(Exception):
    """A tag the rules refuse; the message is meant for the person using the form."""


# Where each record type lives and when its tags freeze: (app, model, reads the status from an instance). A record that
# is posted, approved into a binding document or enacted is history; its dimensions change only by reversing it.
def _journal_line_status(line) -> str:
    return line.header.status


_RECORDS = {
    'journal_line': ('accounting', 'JournalLine', _journal_line_status, {'Pending', 'Approved', 'Posted'}),
    'purchase_request': ('procurement', 'PurchaseRequest', lambda o: o.status, {'Approved'}),
    'purchase_order': ('procurement', 'PurchaseOrder', lambda o: o.status, {'Posted', 'Closed'}),
    'appropriation': ('budget', 'Appropriation', lambda o: o.status, {'ENACTED', 'ACTIVE', 'CLOSED'}),
}


def _assert_editable(record_type: str, record_id: int) -> None:
    """The record must exist and not be locked, or the change is refused with the reason."""
    from django.apps import apps
    app_label, model_name, read_status, locked = _RECORDS[record_type]
    model = apps.get_model(app_label, model_name)
    qs = model.objects.select_related('header') if record_type == 'journal_line' else model.objects
    record = qs.filter(pk=record_id).first()
    if record is None:
        raise DimensionError(f'That {record_type.replace("_", " ")} does not exist.')
    status = read_status(record)
    if status in locked:
        raise DimensionError(f'This record is {str(status).lower()}; its dimensions can no longer change.')


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


def _fill_parents(record_type: str, resolved: dict) -> None:
    """A ward alone implies its zone: tag the parent too (when it is switched on here), so a zone report and a ward
    report agree about the line."""
    for code, (dimension, value) in list(resolved.items()):
        parent_type = dimension.parent_type
        if (parent_type is None or value.parent_id is None or parent_type.code in resolved
                or not parent_type.is_active or record_type not in (parent_type.applies_to or [])):
            continue
        resolved[parent_type.code] = (parent_type, value.parent)


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
    resolved = {}
    for code, value_code in tags.items():
        dimension = _resolve_type(record_type, code)
        resolved[code] = (dimension, _resolve_value(dimension, value_code))
    _fill_parents(record_type, resolved)
    _check_parentage(resolved)
    _check_required(record_type, resolved)
    _assert_editable(record_type, record_id)
    try:
        DimensionTag.objects.filter(record_type=record_type, record_id=record_id).delete()
        DimensionTag.objects.bulk_create([
            DimensionTag(record_type=record_type, record_id=record_id, dimension_type=d, value=v)
            for d, v in resolved.values()])
    except IntegrityError as exc:       # two saves of the same record at once: the second loses, with a reason
        raise DimensionError('This record was changed by someone else at the same time. Try again.') from exc
    return get_tags(record_type, record_id)


def copy_tags(from_type: str, from_id: int, to_type: str, to_id: int) -> None:
    """Carry a record's dimensions onto the record made from it (a purchase order from its request), keeping only the
    dimensions that are switched on for the new record type. For code that has just created the target: no lock check."""
    wanted = {t.dimension_type_id: t for t in DimensionTag.objects.select_related('dimension_type').filter(
        record_type=from_type, record_id=from_id, dimension_type__is_active=True, value__is_active=True)
        if to_type in (t.dimension_type.applies_to or [])}
    DimensionTag.objects.filter(record_type=to_type, record_id=to_id).delete()
    DimensionTag.objects.bulk_create([
        DimensionTag(record_type=to_type, record_id=to_id, dimension_type_id=t.dimension_type_id, value_id=t.value_id)
        for t in wanted.values()])


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
    # A reversed journal and the journal that reverses it cancel each other; counting only one (the reversal's lines carry no
    # tags) would show spend that no longer exists. Leave both out.
    from accounting.models import JournalReversal
    reversing = JournalReversal.objects.exclude(reversal_journal__isnull=True).values('reversal_journal_id')
    lines = JournalLine.objects.filter(
        header__status=POSTED, header__is_deleted=False, header__is_reversed=False,
        account__account_type=account_type).exclude(header_id__in=reversing)
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
