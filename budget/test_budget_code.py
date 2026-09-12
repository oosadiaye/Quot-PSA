"""
Optional budget code on budget line items.

No database. CI's backend job runs a no-DB fast tier, so a test that
needs a tenant schema would not run there at all — and the logic worth
guarding here is parsing and layout, neither of which needs a row.

What can actually go wrong with an optional free-text column:

  * an older CSV, saved before the column existed, stops importing;
  * a blank cell is stored as the string ``'nan'`` — pandas' empty cell
    reaches the model as a budget code nobody typed;
  * the template offers a column the parser does not read, so the
    upload reports success and silently drops the value;
  * the column's ``max_length`` and the importer's truncation drift
    apart, turning a long code into a database error mid-import.
"""
from django.test import SimpleTestCase

from budget.import_columns import (
    APPROPRIATION_COLUMNS,
    BUDGET_CODE_COLUMN,
    BUDGET_CODE_MAX_LENGTH,
    REVENUE_COLUMNS,
    REVENUE_MONTH_COLUMNS,
    budget_code_update,
    clean_budget_code,
)


class CleanBudgetCodeTests(SimpleTestCase):
    """The cell-to-string normaliser."""

    def test_keeps_a_real_code(self):
        self.assertEqual(clean_budget_code('BL-2026-0142'), 'BL-2026-0142')

    def test_trims_surrounding_whitespace(self):
        # Spreadsheets pad cells more often than anyone admits.
        self.assertEqual(clean_budget_code('  BL-2026-0142 '), 'BL-2026-0142')

    def test_missing_column_is_empty(self):
        # row.get('budget_code') on a CSV saved before the column existed.
        self.assertEqual(clean_budget_code(None), '')

    def test_blank_cell_is_empty(self):
        self.assertEqual(clean_budget_code(''), '')
        self.assertEqual(clean_budget_code('   '), '')

    def test_pandas_nan_does_not_become_the_string_nan(self):
        # The revenue importer reads with pandas' default NA handling, so
        # a blank cell arrives as NaN and str(NaN) == 'nan'. Storing that
        # would invent a budget code that matches nothing and groups
        # every blank row together.
        float_nan = float('nan')
        self.assertEqual(clean_budget_code(float_nan), '')
        self.assertEqual(clean_budget_code('nan'), '')
        self.assertEqual(clean_budget_code('NaN'), '')
        self.assertEqual(clean_budget_code('None'), '')

    def test_truncates_to_the_column_width(self):
        # One over-long cell is a typo, not a reason to fail a 500-row
        # upload — but it must not reach the database over-length either.
        long_code = 'X' * (BUDGET_CODE_MAX_LENGTH + 20)
        cleaned = clean_budget_code(long_code)
        self.assertEqual(len(cleaned), BUDGET_CODE_MAX_LENGTH)

    def test_coerces_a_numeric_cell(self):
        # Excel turns a code like 20260142 into a number; str() of it must
        # still be usable rather than crashing on .strip().
        self.assertEqual(clean_budget_code(20260142), '20260142')


class TemplateLayoutTests(SimpleTestCase):
    """The template a user downloads must offer what the parser reads."""

    def test_appropriation_template_offers_the_column(self):
        self.assertIn(BUDGET_CODE_COLUMN, APPROPRIATION_COLUMNS)

    def test_revenue_template_offers_the_column(self):
        self.assertIn(BUDGET_CODE_COLUMN, REVENUE_COLUMNS)

    def test_budget_code_is_last_so_existing_files_keep_their_order(self):
        # Appending rather than inserting means a saved CSV opened in
        # Excel lines up column-for-column with the new template.
        self.assertEqual(APPROPRIATION_COLUMNS[-1], BUDGET_CODE_COLUMN)
        self.assertEqual(REVENUE_COLUMNS[-1], BUDGET_CODE_COLUMN)

    def test_required_columns_are_still_present(self):
        # The importers reject an upload missing any of these; adding a
        # column must not have disturbed them.
        for col in ('fiscal_year', 'mda_code', 'economic_code', 'fund_code',
                    'functional_code', 'programme_code', 'amount_approved'):
            self.assertIn(col, APPROPRIATION_COLUMNS)
        for col in ('fiscal_year', 'administrative_code', 'economic_code',
                    'fund_code', 'estimated_amount'):
            self.assertIn(col, REVENUE_COLUMNS)

    def test_revenue_keeps_all_twelve_month_columns(self):
        self.assertEqual(len(REVENUE_MONTH_COLUMNS), 12)
        for month in REVENUE_MONTH_COLUMNS:
            self.assertIn(month, REVENUE_COLUMNS)

    def test_no_duplicate_columns(self):
        for cols in (APPROPRIATION_COLUMNS, REVENUE_COLUMNS):
            self.assertEqual(len(cols), len(set(cols)))


class ModelFieldDeclarationTests(SimpleTestCase):
    """Field shape, read off _meta — no rows, no database."""

    def _field(self, model):
        return model._meta.get_field('budget_code')

    def test_both_models_carry_the_field(self):
        from budget.models import Appropriation, RevenueBudget
        for model in (Appropriation, RevenueBudget):
            self.assertIsNotNone(self._field(model))

    def test_field_is_optional_and_not_nullable(self):
        # blank=True makes it optional in forms and DRF; null=False keeps
        # "no code" a single value ('') rather than two ('' and None) that
        # every reader would have to handle.
        from budget.models import Appropriation, RevenueBudget
        for model in (Appropriation, RevenueBudget):
            f = self._field(model)
            self.assertTrue(f.blank, f'{model.__name__}.budget_code should be blank=True')
            self.assertFalse(f.null, f'{model.__name__}.budget_code should be null=False')
            self.assertEqual(f.default, '')

    def test_field_is_not_unique(self):
        # Several lines legitimately roll up to one budget line — a
        # programme split across economic segments. Uniqueness would
        # reject correct data.
        from budget.models import Appropriation, RevenueBudget
        for model in (Appropriation, RevenueBudget):
            self.assertFalse(self._field(model).unique)

    def test_field_is_indexed_for_grouping(self):
        from budget.models import Appropriation, RevenueBudget
        for model in (Appropriation, RevenueBudget):
            self.assertTrue(self._field(model).db_index)

    def test_max_length_matches_the_importer_truncation(self):
        # If these drift, a long code either fails the insert or is cut
        # somewhere the operator cannot predict.
        from budget.models import Appropriation, RevenueBudget
        for model in (Appropriation, RevenueBudget):
            self.assertEqual(self._field(model).max_length, BUDGET_CODE_MAX_LENGTH)


class SerializerExposureTests(SimpleTestCase):
    """A field the API does not serve cannot be tracked from the UI."""

    def test_appropriation_serializer_serves_it(self):
        from budget.serializers import AppropriationSerializer
        self.assertIn('budget_code', AppropriationSerializer.Meta.fields)

    def test_revenue_serializer_serves_it(self):
        from budget.serializers import RevenueBudgetSerializer
        self.assertIn('budget_code', RevenueBudgetSerializer.Meta.fields)

    def test_it_is_writable(self):
        # Read-only would make the column importable but not editable,
        # which is a confusing half-feature.
        from budget.serializers import AppropriationSerializer, RevenueBudgetSerializer
        for ser in (AppropriationSerializer, RevenueBudgetSerializer):
            self.assertNotIn('budget_code', getattr(ser.Meta, 'read_only_fields', []))


class AbsentColumnVersusBlankCellTests(SimpleTestCase):
    """Two different statements that must not be collapsed.

    The appropriation import upserts on (fiscal_year, mda, economic,
    fund), and the template tells operators to edit a saved CSV and
    re-upload it to adjust amounts. A file exported before this column
    existed therefore arrives regularly — and must leave stored codes
    alone rather than clearing every one of them while reporting
    success.
    """

    WITH = ['fiscal_year', 'amount_approved', 'budget_code']
    WITHOUT = ['fiscal_year', 'amount_approved']

    def test_absent_column_writes_nothing(self):
        self.assertEqual(budget_code_update(self.WITHOUT, None), {})

    def test_absent_column_writes_nothing_even_if_a_value_is_passed(self):
        # Defensive: the caller reads the cell before asking. If the
        # column is not in the upload, whatever it read is meaningless.
        self.assertEqual(budget_code_update(self.WITHOUT, 'BL-2026-0142'), {})

    def test_present_column_with_a_value_writes_it(self):
        self.assertEqual(
            budget_code_update(self.WITH, 'BL-2026-0142'),
            {'budget_code': 'BL-2026-0142'},
        )

    def test_present_but_blank_is_an_explicit_clear(self):
        # The operator deleted the cell contents; honour that.
        self.assertEqual(budget_code_update(self.WITH, ''), {'budget_code': ''})

    def test_present_column_normalises_like_clean_budget_code(self):
        self.assertEqual(
            budget_code_update(self.WITH, float('nan')), {'budget_code': ''},
        )
        self.assertEqual(
            budget_code_update(self.WITH, '  BL-1 '), {'budget_code': 'BL-1'},
        )

    def test_accepts_any_column_container(self):
        # df.columns is a pandas Index, not a list.
        self.assertEqual(
            budget_code_update(iter(self.WITH), 'BL-1'), {'budget_code': 'BL-1'},
        )
