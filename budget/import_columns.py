"""
Column layout for the budget CSV import templates.

The template writer and the upload parser used to state the columns
independently, a few hundred lines apart in ``views.py``. Adding a
column meant editing both and hoping; a template offering a column the
parser ignores fails silently, which is the worst way for an import to
be wrong — the operator sees "success" and the value never lands.

Keeping the layout here lets a test assert that the template a user
downloads contains the column the parser reads.
"""

#: The optional per-line reference. Free text, not a key — the NCoA
#: segment combination is what identifies a budget line structurally.
BUDGET_CODE_COLUMN = 'budget_code'

#: Mirrors ``max_length`` on the model field. Import truncates to this
#: rather than raising, because a too-long code is a typo in one cell,
#: not a reason to reject an otherwise valid 500-row upload.
BUDGET_CODE_MAX_LENGTH = 50

BUDGET_CODE_HELP = (
    "budget_code: your own reference for the budget line "
    "(e.g. 'BL-2026-0142'). Optional — leave blank if unused."
)

#: Expenditure appropriation lines.
APPROPRIATION_COLUMNS = [
    'fiscal_year', 'mda_code', 'economic_code', 'fund_code',
    'functional_code', 'programme_code', 'geographic_code',
    'appropriation_type', 'amount_approved',
    'law_reference', 'enactment_date', 'description', 'notes',
    BUDGET_CODE_COLUMN,
]

#: Revenue budget lines. The twelve month columns carry the optional
#: monthly spread; blank means "spread evenly".
REVENUE_MONTH_COLUMNS = [
    'jan', 'feb', 'mar', 'apr', 'may', 'jun',
    'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
]

REVENUE_COLUMNS = [
    'fiscal_year', 'administrative_code', 'economic_code', 'fund_code',
    'estimated_amount', *REVENUE_MONTH_COLUMNS, 'description',
    BUDGET_CODE_COLUMN,
]


def clean_budget_code(value) -> str:
    """Normalise one ``budget_code`` cell to a storable string.

    Handles the three shapes a spreadsheet cell arrives in:

    * missing entirely (an older CSV saved before the column existed),
    * pandas ``NaN`` for a blank cell — ``str(NaN)`` is the string
      ``'nan'``, which would otherwise be stored as a budget code the
      operator never typed,
    * a real value, possibly padded or over-length.
    """
    if value is None:
        return ''
    text = str(value).strip()
    # A bare 'nan'/'none' is pandas' empty cell, never a real reference:
    # every code in use carries a prefix or a digit group.
    if text.lower() in ('nan', 'none', 'nat'):
        return ''
    return text[:BUDGET_CODE_MAX_LENGTH]


def budget_code_update(columns, cell) -> dict:
    """The ``budget_code`` part of an upsert's ``defaults``.

    Empty when the upload has no ``budget_code`` column at all, so the
    stored value is left alone.

    "Column absent" and "cell blank" are different statements. Absent
    means the file has no opinion about this field — a CSV exported
    before the column existed. Blank means the operator cleared it.
    Treating both as ``''`` wipes every budget code the first time
    somebody re-uploads an older file to adjust amounts, which is the
    workflow the import template explicitly recommends, and the import
    reports success while doing it.
    """
    if BUDGET_CODE_COLUMN not in set(columns):
        return {}
    return {BUDGET_CODE_COLUMN: clean_budget_code(cell)}
