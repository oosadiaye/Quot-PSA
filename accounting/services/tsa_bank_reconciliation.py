"""
TSA Bank Reconciliation Services
================================

Two independent services live here:

1. ``parse_statement_file`` — read an uploaded CSV/TSV and convert it into
   ``TSABankStatementLine`` rows under a ``TSABankStatement`` header.

2. ``auto_match_statement`` — walk every unmatched statement line and try to
   link it to a ``PaymentInstruction`` (debit) or ``RevenueCollection``
   (credit) using a tiered strategy:
       a. Exact reference match (highest confidence)
       b. Amount + date (±3 days) exact match
       c. Amount + date + partial description match

Only unambiguous matches are auto-linked. Ties or fuzzy mismatches are left
for the reconciler to decide manually.

CSV format expected (flexible header matching is applied):
    date,value_date,description,reference,debit,credit,balance
Any subset of these headers is accepted; unknown columns are ignored.

Date-format note: date parsing tries ``%d/%m/%Y`` before ``%m/%d/%Y`` (Nigeria
default). Files generated with US-style formatting must either use ISO dates
(``%Y-%m-%d``) or be pre-converted.
"""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from accounting.models import (
    TSABankStatement, TSABankStatementLine,
    PaymentInstruction, RevenueCollection,
)


# =============================================================================
# Parser
# =============================================================================

# Column headers we recognise, mapped to canonical field names.
_HEADER_ALIASES = {
    'date':             'transaction_date',
    'transaction_date': 'transaction_date',
    'txn_date':         'transaction_date',
    'posting_date':     'transaction_date',
    'value_date':       'value_date',
    'val_date':         'value_date',
    'description':      'description',
    'narration':        'description',
    'details':          'description',
    'particulars':      'description',
    'reference':        'reference',
    'ref':              'reference',
    'transaction_ref':  'reference',
    'debit':            'debit',
    'withdrawal':       'debit',
    'debit_amount':     'debit',
    'credit':           'credit',
    'deposit':          'credit',
    'credit_amount':    'credit',
    'balance':          'balance_after',
    'running_balance':  'balance_after',
    'balance_after':    'balance_after',
}

# Date formats we try in order. CSVs come from all sorts of sources.
_DATE_FORMATS = [
    '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y',
    '%d-%m-%Y', '%d %b %Y', '%d-%b-%Y', '%d/%b/%Y',
    '%Y/%m/%d',
]

# Currency symbols and codes we strip from number cells (L6).
_CURRENCY_TOKENS = [
    '\u20a6',  # ₦ Naira
    '\u0024',  # $
    '\u20ac',  # €
    '\u00a3',  # £
    '\u00a5',  # ¥
    'NGN', 'USD', 'EUR', 'GBP', 'JPY',
    'KSH', 'KES', 'ZAR', 'GHS', 'XAF', 'XOF',
]


def _parse_date(value):
    if not value:
        return None
    value = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(value) -> Decimal:
    """Parse a number cell tolerantly — handles '₦1,234.00', '(500.00)',
    blank cells, and '-' / 'NIL' placeholders."""
    if value is None:
        return Decimal('0')
    v = str(value).strip()
    if not v or v.lower() in ('-', 'nil', 'n/a', 'none', '--'):
        return Decimal('0')
    # Strip all recognised currency tokens (case-insensitive on text codes).
    upper = v.upper()
    for tok in _CURRENCY_TOKENS:
        if tok.isalpha():
            upper = upper.replace(tok, '')
        else:
            v = v.replace(tok, '')
    if any(tok.isalpha() for tok in _CURRENCY_TOKENS):
        # Re-apply text-code stripping via the upper variant.
        v = upper if upper != v.upper() else v
    v = v.replace(',', '').replace(' ', '').strip()
    negative = v.startswith('(') and v.endswith(')')
    if negative:
        v = v[1:-1]
    try:
        result = Decimal(v)
    except InvalidOperation:
        return Decimal('0')
    return -result if negative else result


def _normalise_header(h):
    if not h:
        return None
    key = str(h).strip().lower().replace(' ', '_').replace('-', '_')
    return _HEADER_ALIASES.get(key)


def _compute_file_hash(raw_bytes: bytes) -> str:
    """SHA-256 digest of raw file bytes — used for upload deduplication."""
    return hashlib.sha256(raw_bytes).hexdigest()


def parse_statement_file(
    tsa_account,
    uploaded_file,
    opening_balance: Decimal | None = None,
    uploaded_by=None,
) -> TSABankStatement:
    """Parse a CSV/TSV upload into a ``TSABankStatement`` with lines.

    Returns the saved import header. Raises ``ValueError`` on parse failure or
    if an identical file has already been uploaded for this TSA (M2 dedup).
    """
    filename = getattr(uploaded_file, 'name', 'statement.csv')

    # Read file bytes once, compute hash, then rewind so FileField gets full
    # content when we save (H2).
    uploaded_file.seek(0)
    raw_bytes = uploaded_file.read()
    if not isinstance(raw_bytes, (bytes, bytearray)):
        raw_bytes = str(raw_bytes).encode('utf-8')

    file_hash = _compute_file_hash(bytes(raw_bytes))

    # M2 — reject duplicate uploads against the same TSA.
    existing = TSABankStatement.objects.filter(
        tsa_account=tsa_account, file_hash=file_hash,
    ).first()
    if existing:
        raise ValueError(
            f'An identical statement was already uploaded on '
            f'{existing.created_at.date()} (file "{existing.original_filename}").'
        )

    # Decode tolerantly — banks ship cp1252/latin-1 often.
    text = None
    for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            text = bytes(raw_bytes).decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = bytes(raw_bytes).decode('utf-8', errors='replace')

    # Detect delimiter (comma or tab) from the first non-empty line.
    sample = text[:2048]
    delimiter = '\t' if sample.count('\t') > sample.count(',') else ','

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows_raw = list(reader)
    rows = [
        (original_idx + 1, r) for original_idx, r in enumerate(rows_raw)
        if any((c or '').strip() for c in r)
    ]
    if not rows:
        raise ValueError('The uploaded file is empty.')

    # Find the header row: the first row where ≥3 cells map to recognised
    # fields. Tracks the original row number (1-based, from the file) so
    # error reports use user-visible line numbers (L4).
    header_row_idx = -1
    header_map: dict[int, str] = {}
    header_file_row: int | None = None
    for i, (file_row_no, row) in enumerate(rows[:10]):
        candidate_map = {
            col_i: _normalise_header(cell) for col_i, cell in enumerate(row)
        }
        recognised = sum(1 for v in candidate_map.values() if v)
        if recognised >= 3:
            header_row_idx = i
            header_map = {k: v for k, v in candidate_map.items() if v}
            header_file_row = file_row_no
            break

    if header_row_idx == -1:
        raise ValueError(
            'Could not find a header row. Expected columns like '
            'date, description, debit, credit.'
        )

    data_rows = rows[header_row_idx + 1:]

    parsed_lines: list[dict] = []
    errors: list[dict] = []
    running_balance = opening_balance or Decimal('0')
    date_min = None
    date_max = None
    total_debits = Decimal('0')
    total_credits = Decimal('0')

    for parsed_idx, (file_row_no, row) in enumerate(data_rows, start=1):
        cells = {header_map[i]: (row[i] if i < len(row) else '') for i in header_map}

        txn_date = _parse_date(cells.get('transaction_date'))
        if not txn_date:
            errors.append({
                'file_row': file_row_no,
                'data_row': parsed_idx,
                'error': 'Missing or invalid transaction date',
            })
            continue

        debit = _parse_decimal(cells.get('debit'))
        credit = _parse_decimal(cells.get('credit'))
        if debit == 0 and credit == 0:
            errors.append({
                'file_row': file_row_no,
                'data_row': parsed_idx,
                'error': 'Row has no debit or credit amount',
            })
            continue

        balance = cells.get('balance_after')
        balance_val = _parse_decimal(balance) if balance else None
        if balance_val is None:
            running_balance = running_balance + credit - debit
            balance_val = running_balance
        else:
            running_balance = balance_val

        date_min = txn_date if date_min is None or txn_date < date_min else date_min
        date_max = txn_date if date_max is None or txn_date > date_max else date_max
        total_debits += debit
        total_credits += credit

        parsed_lines.append({
            'line_number':      parsed_idx,
            'transaction_date': txn_date,
            'value_date':       _parse_date(cells.get('value_date')),
            'description':      (cells.get('description') or '').strip()[:500],
            'reference':        (cells.get('reference') or '').strip()[:100],
            'debit':            debit,
            'credit':           credit,
            'balance_after':    balance_val,
        })

    if not parsed_lines:
        raise ValueError(
            f'No usable transaction rows found. '
            f'Header was detected on file row {header_file_row}. '
            f'First parse errors: {errors[:3]}'
        )

    # Rewind so Django's FileField reads full content (H2).
    if hasattr(uploaded_file, 'seek'):
        try:
            uploaded_file.seek(0)
        except (OSError, ValueError):
            pass

    with transaction.atomic():
        header = TSABankStatement.objects.create(
            tsa_account=tsa_account,
            statement_file=uploaded_file,
            original_filename=filename,
            statement_from=date_min,
            statement_to=date_max,
            opening_balance=opening_balance or Decimal('0'),
            closing_balance=running_balance,
            total_debits=total_debits,
            total_credits=total_credits,
            line_count=len(parsed_lines),
            parse_errors=errors,
            status='PARSED',
            uploaded_by=uploaded_by,
            file_hash=file_hash,
        )
        TSABankStatementLine.objects.bulk_create([
            TSABankStatementLine(statement=header, **row) for row in parsed_lines
        ])

    return header


# =============================================================================
# Auto-matcher
# =============================================================================

# Tolerance when comparing amounts (guards against FX/rounding).
_AMOUNT_EPSILON = Decimal('0.01')
# How many days we allow between a statement date and a book date before we
# refuse to consider them the same transaction.
_DATE_WINDOW_DAYS = 3

# Common words ignored when scoring description overlap (L3).
_DESC_STOPWORDS = {
    'the', 'and', 'for', 'from', 'with', 'via',
    'payment', 'transfer', 'deposit', 'withdrawal',
    'trf', 'pmt', 'txn', 'inv', 'ref', 'bank',
    'charge', 'charges', 'fee', 'fees',
    'nibss', 'neft', 'rtgs', 'instant',
    'per', 'ltd', 'limited', 'ent', 'enterprises',
    'nigeria', 'ngn',
}


def _amount_close(a: Decimal, b: Decimal) -> bool:
    return abs((a or Decimal('0')) - (b or Decimal('0'))) <= _AMOUNT_EPSILON


def _date_within(a, b, days: int = _DATE_WINDOW_DAYS) -> bool:
    if a is None or b is None:
        return False
    return abs((a - b).days) <= days


def _description_overlap(text_a: str, text_b: str) -> float:
    """Token-overlap score between two strings, 0.0 - 1.0, with stopwords
    filtered so common banking words don't inflate scores."""
    if not text_a or not text_b:
        return 0.0
    toks_a = {
        t for t in text_a.lower().split()
        if len(t) > 2 and t not in _DESC_STOPWORDS
    }
    toks_b = {
        t for t in text_b.lower().split()
        if len(t) > 2 and t not in _DESC_STOPWORDS
    }
    if not toks_a or not toks_b:
        return 0.0
    return len(toks_a & toks_b) / max(len(toks_a), len(toks_b))


def auto_match_statement(statement: TSABankStatement, actor=None) -> dict:
    """Attempt to match every unmatched line on the statement.

    ``actor`` is the user running the match (stamped on ``matched_by``).

    Serialises under a row-lock on the statement (H3) so concurrent clicks
    can't both claim the same candidate and produce a silent double-match.

    Returns::

        {
          'matched': 42, 'skipped': 3, 'ambiguous': 1,
          'by_strategy': {'reference': 20, 'amount_date': 18, 'amount_fuzzy': 4},
          'total_lines': 60,
        }
    """
    with transaction.atomic():
        # Row-level lock — H3. Another auto-match call on the same statement
        # waits until we finish.
        statement = (
            TSABankStatement.objects
            .select_for_update()
            .get(pk=statement.pk)
        )
        result = _do_auto_match(statement, actor)

        # Conditional status flip (M3): only move to MATCHED if something
        # actually matched. Otherwise stay on PARSED.
        if result['matched'] > 0 and statement.status == 'PARSED':
            statement.status = 'MATCHED'
            statement.save(update_fields=['status'])

    return result


def _do_auto_match(statement: TSABankStatement, actor) -> dict:
    tsa = statement.tsa_account
    window_start = statement.statement_from - timedelta(days=_DATE_WINDOW_DAYS)
    window_end = statement.statement_to + timedelta(days=_DATE_WINDOW_DAYS)

    already_matched_payment_ids = set(
        TSABankStatementLine.objects
        .filter(matched_payment__isnull=False)
        .exclude(statement=statement)
        .values_list('matched_payment_id', flat=True)
    )
    already_matched_revenue_ids = set(
        TSABankStatementLine.objects
        .filter(matched_revenue__isnull=False)
        .exclude(statement=statement)
        .values_list('matched_revenue_id', flat=True)
    )

    payments = list(
        PaymentInstruction.objects
        .filter(
            tsa_account=tsa,
            status='PROCESSED',
            processed_at__date__gte=window_start,
            processed_at__date__lte=window_end,
        )
        .exclude(id__in=already_matched_payment_ids)
        .select_related('payment_voucher')
    )
    revenues = list(
        RevenueCollection.objects
        .filter(
            tsa_account=tsa,
            status__in=['POSTED', 'RECONCILED'],
            collection_date__gte=window_start,
            collection_date__lte=window_end,
        )
        .exclude(id__in=already_matched_revenue_ids)
    )

    by_strategy = {'reference': 0, 'amount_date': 0, 'amount_fuzzy': 0}
    matched = 0
    ambiguous = 0
    skipped = 0

    lines = statement.lines.filter(match_status='UNMATCHED').order_by('line_number')
    to_update: list[TSABankStatementLine] = []
    now = timezone.now()

    for line in lines:
        candidate = None
        strategy = None
        confidence = Decimal('0')

        if line.debit > 0 and line.credit == 0:
            pool = payments
            amt = line.debit
            pool_type = 'payment'
        elif line.credit > 0 and line.debit == 0:
            pool = revenues
            amt = line.credit
            pool_type = 'revenue'
        else:
            skipped += 1
            continue

        def get_ref(p, _pool_type=pool_type):
            if _pool_type == 'payment':
                return (
                    p.bank_reference
                    or (p.payment_voucher.voucher_number if p.payment_voucher_id else '')
                    or p.batch_reference
                )
            return p.payment_reference or p.rrr or ''

        def get_date(p, _pool_type=pool_type):
            if _pool_type == 'payment':
                return p.processed_at.date() if p.processed_at else None
            return p.value_date or p.collection_date

        def get_narr(p, _pool_type=pool_type):
            if _pool_type == 'payment':
                return p.narration or p.beneficiary_name or ''
            return p.payer_name or ''

        # ── Strategy 1: reference equality ────────────────────────────────
        if line.reference:
            ref_lower = line.reference.strip().lower()
            exact = [
                p for p in pool
                if get_ref(p) and get_ref(p).strip().lower() == ref_lower
            ]
            amt_ok = [p for p in exact if _amount_close(amt, p.amount or Decimal('0'))]
            if len(amt_ok) == 1:
                candidate = amt_ok[0]
                strategy = 'reference'
                confidence = Decimal('99')
            elif len(amt_ok) > 1:
                # H7: multiple records share ref+amount — note as ambiguous.
                ambiguous += 1
                # Don't fall through to weaker strategies when the strong
                # signal is itself ambiguous.
                skipped += 1
                continue

        # ── Strategy 2: amount + close date ───────────────────────────────
        if candidate is None:
            same_amount = [
                p for p in pool if _amount_close(amt, p.amount or Decimal('0'))
            ]
            date_ok = [
                p for p in same_amount
                if _date_within(line.transaction_date, get_date(p))
            ]
            if len(date_ok) == 1:
                candidate = date_ok[0]
                strategy = 'amount_date'
                confidence = Decimal('85')
            elif len(date_ok) > 1:
                scored = [
                    (p, _description_overlap(line.description, get_narr(p)))
                    for p in date_ok
                ]
                scored.sort(key=lambda x: x[1], reverse=True)
                if scored and scored[0][1] >= 0.5 and (
                    len(scored) == 1 or scored[0][1] - scored[1][1] >= 0.2
                ):
                    candidate = scored[0][0]
                    strategy = 'amount_fuzzy'
                    confidence = Decimal('70')
                else:
                    ambiguous += 1

        if candidate is None:
            skipped += 1
            continue

        if pool_type == 'payment':
            line.matched_payment = candidate
            payments.remove(candidate)
        else:
            line.matched_revenue = candidate
            revenues.remove(candidate)

        line.match_status = 'AUTO'
        line.match_confidence = confidence
        line.matched_by = actor if (actor and getattr(actor, 'is_authenticated', False)) else None
        line.matched_at = now
        to_update.append(line)
        by_strategy[strategy] = by_strategy.get(strategy, 0) + 1
        matched += 1

    if to_update:
        TSABankStatementLine.objects.bulk_update(
            to_update,
            [
                'matched_payment', 'matched_revenue',
                'match_status', 'match_confidence',
                'matched_by', 'matched_at',
            ],
            batch_size=500,
        )

    return {
        'matched': matched,
        'skipped': skipped,
        'ambiguous': ambiguous,
        'by_strategy': by_strategy,
        'total_lines': statement.line_count,
    }
