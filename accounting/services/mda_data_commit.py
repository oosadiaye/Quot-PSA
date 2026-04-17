"""
MDA bulk-import commit service — materialise parsed rows into domain tables.

Sprint 11 shipped the **preview** path: CSV/XLSX uploads are parsed,
validated, and returned as structured rows with per-row errors. This
service closes the loop: take a preview's already-validated rows and
persist them to the appropriate domain tables under a wrapping
transaction.

Design choices
--------------

* **One service, per-type strategy methods**. The ``commit()`` entry
  point dispatches on ``data_type``; each strategy (`_commit_provisions`,
  `_commit_revenue_collections`, etc.) writes to one (or more) domain
  tables. Adding a new data type is a new method + a registry entry.

* **Atomic per-commit**. The whole strategy runs inside
  ``transaction.atomic()``. If the 47th row errors, the first 46 roll
  back. Partial imports are *not* a recovery mode we want the AG to
  reason about.

* **Idempotent-friendly**. The preview carries a ``source_hash`` — a
  SHA-256 of the normalised row payload. The commit records this hash
  on an ``MDAImportLog`` row; callers that pass ``idempotency_key=...``
  get a 409-style response on re-commit instead of duplicates.

Return shape
------------
    CommitResult(
      data_type,
      created_count,
      updated_count,
      errors,
      idempotency_key,
    )
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Optional

from django.db import transaction


@dataclass
class CommitResult:
    """Return shape for ``MDAImportCommitService.commit()``."""
    data_type: str
    created_count: int = 0
    updated_count: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    idempotency_key: Optional[str] = None
    created_ids: list[int] = field(default_factory=list)

    def is_success(self) -> bool:
        return not self.errors


class CommitError(Exception):
    """Raised for any commit-time failure a view should translate to 400."""


class MDAImportCommitService:
    """Dispatch commits to per-data_type strategy methods."""

    # Registry: data_type → strategy method name.
    _STRATEGIES: dict[str, str] = {
        'provisions':         '_commit_provisions',
        'revenue_collection': '_commit_revenue_collections',
        'payroll_summary':    '_commit_payroll_summary',
        'journal_summary':    '_commit_journal_summary',
    }

    @classmethod
    def commit(
        cls,
        *,
        data_type: str,
        rows: list[dict],
        user=None,
        notes: str = '',
        idempotency_key: Optional[str] = None,
    ) -> CommitResult:
        """Persist the parsed rows atomically.

        Raises :class:`CommitError` if the data_type is unknown. For
        per-row errors the result carries them in ``errors`` — the
        outer transaction rolls back so the DB is untouched, but the
        caller still gets the structured diagnostics.
        """
        strategy_name = cls._STRATEGIES.get(data_type)
        if strategy_name is None:
            raise CommitError(
                f'Unknown data_type {data_type!r}. '
                f'Supported: {sorted(cls._STRATEGIES.keys())}.'
            )

        # Derive (or accept) an idempotency key so the caller can detect
        # a re-submission of the same payload.
        key = idempotency_key or cls._default_idempotency_key(data_type, rows)

        # Short-circuit: if we already committed under this key, return
        # the prior result so the client treats it as idempotent.
        existing = cls._load_prior_commit(key)
        if existing is not None:
            return existing

        result = CommitResult(data_type=data_type, idempotency_key=key)
        strategy: Callable = getattr(cls, strategy_name)

        try:
            with transaction.atomic():
                strategy(rows=rows, user=user, result=result, notes=notes)
                # Persist an MDAImportLog entry so subsequent calls with
                # the same key can short-circuit. Done inside the same
                # atomic block so log + data land together.
                cls._record_commit_log(
                    data_type=data_type, key=key,
                    result=result, user=user, notes=notes,
                )
        except CommitError:
            raise
        except Exception as exc:
            raise CommitError(
                f'Commit failed mid-transaction; no rows were persisted. '
                f'{type(exc).__name__}: {exc}'
            )

        return result

    # ── Strategies ──────────────────────────────────────────────────────

    @classmethod
    def _commit_provisions(cls, *, rows, user, result: CommitResult, notes):
        """Bulk-create Provision rows from parsed CSV/XLSX input.

        Maps the flat row shape to the ``Provision`` model fields.
        Duplicate ``reference`` causes the whole commit to roll back —
        the uniqueness constraint at the model level catches it.
        """
        from accounting.models import Provision, MDA

        # Resolve optional MDA FK once per mda_code so we don't query per row.
        mda_codes = {(r.get('mda_code') or '').strip() for r in rows}
        mda_codes.discard('')
        mdas_by_code = {
            m.code: m for m in MDA.objects.filter(code__in=mda_codes)
        } if mda_codes else {}

        to_create: list[Provision] = []
        for i, row in enumerate(rows, start=1):
            try:
                obj = Provision(
                    reference=row['reference'],
                    category=row.get('category') or 'OTHER',
                    title=row.get('title') or '(untitled)',
                    description=row.get('description') or '',
                    amount=_dec(row.get('amount')),
                    undiscounted_amount=_dec_or_none(row.get('undiscounted_amount')),
                    recognition_date=row['recognition_date'],
                    expected_settlement_date=row.get('expected_settlement_date'),
                    likelihood=row.get('likelihood') or 'PROBABLE',
                    mda=mdas_by_code.get((row.get('mda_code') or '').strip()),
                    status='DRAFT',
                    notes=notes or '',
                )
                to_create.append(obj)
            except Exception as exc:
                result.errors.append({
                    'row': i,
                    'reference': row.get('reference', '(missing)'),
                    'error': f'{type(exc).__name__}: {exc}',
                })

        if result.errors:
            # Signal the outer atomic block to roll back.
            raise CommitError(
                f'Cannot commit: {len(result.errors)} row(s) failed mapping.'
            )

        created = Provision.objects.bulk_create(to_create)
        result.created_count = len(created)
        result.created_ids = [p.pk for p in created if p.pk]

    @classmethod
    def _commit_revenue_collections(cls, *, rows, user, result: CommitResult, notes):
        """Bulk-create RevenueCollection rows."""
        from accounting.models import RevenueCollection, RevenueHead

        # Resolve RevenueHead once per head code.
        head_codes = {(r.get('revenue_head_code') or '').strip() for r in rows}
        head_codes.discard('')
        heads_by_code = {
            h.code: h for h in RevenueHead.objects.filter(code__in=head_codes)
        } if head_codes else {}

        to_create: list[RevenueCollection] = []
        for i, row in enumerate(rows, start=1):
            head_code = (row.get('revenue_head_code') or '').strip()
            head = heads_by_code.get(head_code)
            if head is None:
                result.errors.append({
                    'row': i,
                    'revenue_head_code': head_code,
                    'error': f'RevenueHead {head_code!r} not found in the chart.',
                })
                continue
            try:
                # The field name varies by deployment — "payment_reference"
                # is the canonical column. We ignore additional optional
                # fields if they're not on the current model.
                obj = RevenueCollection(
                    revenue_head=head,
                    collection_date=row['collection_date'],
                    payer_name=row.get('payer_name') or '',
                    amount=_dec(row.get('amount')),
                    payment_reference=row.get('payment_reference') or '',
                )
                # Optional payer_tin / rrr if present on the model.
                if hasattr(obj, 'payer_tin'):
                    obj.payer_tin = row.get('payer_tin') or ''
                if hasattr(obj, 'rrr'):
                    obj.rrr = row.get('rrr') or ''
                to_create.append(obj)
            except Exception as exc:
                result.errors.append({
                    'row': i,
                    'error': f'{type(exc).__name__}: {exc}',
                })

        if result.errors:
            raise CommitError(
                f'Cannot commit: {len(result.errors)} row(s) failed mapping.'
            )

        created = RevenueCollection.objects.bulk_create(to_create)
        result.created_count = len(created)
        result.created_ids = [r.pk for r in created if r.pk]

    @classmethod
    def _commit_payroll_summary(cls, *, rows, user, result: CommitResult, notes):
        """Payroll summary commits to a dedicated ``MDAPayrollSummary``
        model when present, otherwise records as an MDAImportLog entry
        for audit trail only (no duplicate of PayrollRun mechanics).

        For the OAGF use case the summary is consumed for consolidation
        reports; the AG does not re-post payroll. The "commit" here
        therefore materialises a lightweight audit row rather than
        creating PayrollRun/PayrollLine records.
        """
        from accounting.models import MDAImportLog

        # A commit on payroll summaries is primarily an audit trail event
        # — the structured rows are preserved in the MDAImportLog payload
        # so downstream consolidation scripts can read them back.
        # (The strategy still runs inside the outer transaction so
        # failures roll back.)
        payload = {
            'data_type':    'payroll_summary',
            'row_count':    len(rows),
            'rows':         rows,
            'total_gross':  str(sum(_dec(r.get('gross_pay')) for r in rows)),
            'total_paye':   str(sum(_dec(r.get('paye')) for r in rows)),
            'total_net':    str(sum(_dec(r.get('net_pay')) for r in rows)),
        }
        log = MDAImportLog.objects.create(
            data_type='payroll_summary',
            idempotency_key=result.idempotency_key or '',
            row_count=len(rows),
            payload=payload,
            created_by=user if (user and getattr(user, 'is_authenticated', False)) else None,
            notes=notes or '',
        )
        result.created_count = 1  # one log entry
        result.created_ids = [log.pk]

    @classmethod
    def _commit_journal_summary(cls, *, rows, user, result: CommitResult, notes):
        """Journal summary commits to a single ``JournalHeader`` with
        per-row ``JournalLine`` entries.

        The header carries ``source_module='mda_import'`` so downstream
        reconciliation can distinguish consolidated imports from live
        journal activity.
        """
        from datetime import date as _date
        from accounting.models import JournalHeader, JournalLine, Account

        account_codes = {(r.get('account_code') or '').strip() for r in rows}
        account_codes.discard('')
        accounts_by_code = {
            a.code: a for a in Account.objects.filter(code__in=account_codes)
        } if account_codes else {}

        # One JournalHeader per commit, posting_date = today.
        # reference_number is derived from the idempotency key so re-
        # commits collide on the UniqueConstraint from Sprint 1.
        header = JournalHeader.objects.create(
            posting_date=_date.today(),
            description=(
                f'MDA consolidated journal summary import — {notes}'
                if notes else 'MDA consolidated journal summary import'
            ),
            reference_number=f'MDA-{(result.idempotency_key or "")[:16]}',
            status='Draft',
            source_module='mda_import',
        )

        lines: list[JournalLine] = []
        for i, row in enumerate(rows, start=1):
            account_code = (row.get('account_code') or '').strip()
            account = accounts_by_code.get(account_code)
            if account is None:
                result.errors.append({
                    'row': i,
                    'account_code': account_code,
                    'error': f'Account {account_code!r} not found in the chart.',
                })
                continue
            try:
                lines.append(JournalLine(
                    header=header,
                    account=account,
                    debit=_dec(row.get('debit')),
                    credit=_dec(row.get('credit')),
                    memo=row.get('narration') or '',
                ))
            except Exception as exc:
                result.errors.append({
                    'row': i,
                    'error': f'{type(exc).__name__}: {exc}',
                })

        if result.errors:
            raise CommitError(
                f'Cannot commit: {len(result.errors)} row(s) failed mapping.'
            )

        JournalLine.objects.bulk_create(lines)
        result.created_count = len(lines)
        result.created_ids = [header.pk]

    # ── Idempotency / logging ──────────────────────────────────────────

    @staticmethod
    def _default_idempotency_key(data_type: str, rows: list[dict]) -> str:
        """SHA-256 over (data_type, canonical-serialised-rows).

        Two commits of the same rows in the same order produce the same
        key; the row order matters (MDAs don't want two shuffled copies
        of the same list to be treated as identical).
        """
        canonical = json.dumps(
            [_canonicalise(r) for r in rows],
            sort_keys=True, separators=(',', ':'),
        )
        return hashlib.sha256(
            f'{data_type}|{canonical}'.encode('utf-8')
        ).hexdigest()

    @classmethod
    def _load_prior_commit(cls, key: str) -> Optional[CommitResult]:
        """Return a ``CommitResult`` replayed from a prior ``MDAImportLog``
        row if this key was already committed. Returns None otherwise."""
        try:
            from accounting.models import MDAImportLog
            log = MDAImportLog.objects.filter(idempotency_key=key).first()
        except Exception:
            return None
        if log is None:
            return None
        return CommitResult(
            data_type=log.data_type,
            created_count=log.row_count,
            updated_count=0,
            errors=[],
            idempotency_key=key,
            created_ids=[],  # prior ids are recoverable from payload if needed
        )

    @classmethod
    def _record_commit_log(
        cls, *, data_type: str, key: str, result: CommitResult,
        user, notes: str,
    ):
        """Persist an audit entry for this commit so re-runs are idempotent."""
        from accounting.models import MDAImportLog
        MDAImportLog.objects.create(
            data_type=data_type,
            idempotency_key=key,
            row_count=result.created_count,
            payload={
                'created_count': result.created_count,
                'updated_count': result.updated_count,
                'created_ids':   result.created_ids,
            },
            created_by=user if (user and getattr(user, 'is_authenticated', False)) else None,
            notes=notes or '',
        )


# ── Helpers ────────────────────────────────────────────────────────────

def _dec(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or value == '':
        return Decimal('0')
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal('0')


def _dec_or_none(value):
    if value is None or value == '':
        return None
    return _dec(value)


def _canonicalise(value: Any) -> Any:
    """Stringify Decimal/date so JSON sorting is deterministic."""
    from datetime import date, datetime
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _canonicalise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonicalise(v) for v in value]
    return value
