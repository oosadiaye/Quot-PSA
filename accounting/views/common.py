# NB: accounting.views.common is used as a re-export hub by sibling view
# modules (assets, payables, receivables, workflows, dimensions). Keep
# these `noqa: F401` imports — removing any of them breaks imports across
# the views package.
from decimal import Decimal  # noqa: F401 — re-exported

from django.db import transaction  # noqa: F401 — re-exported
from django.db.models import Sum  # noqa: F401 — re-exported
from rest_framework import status, viewsets  # noqa: F401 — re-exported
from rest_framework.response import Response  # noqa: F401 — re-exported
from rest_framework.decorators import action  # noqa: F401 — re-exported
from rest_framework.pagination import PageNumberPagination
import pandas as pd  # noqa: F401 — re-exported for dimension importers


class AccountingPagination(PageNumberPagination):
    """Shared paginator for the accounting app.

    ``max_page_size`` is set high enough to return the entire Chart of
    Accounts in a single response. Real Nigerian tenants run into the
    1000-account cap (typical state-level COA is 1,000–2,000 lines after
    NCoA expansion); when the cap was 1000 the JournalForm dropdown showed
    a partial list — Income + Expense came through (codes starting with
    1/2 sort first), but Asset / Liability were silently truncated. The
    Journal Entry form needs every account so a CFO can post entries
    against any GL, not just P&L codes.

    10000 is a safety belt — even a maximalist NCoA hierarchy has fewer
    than that, so we'll never silently truncate again, and a malicious
    client can still be told "no" if they ask for a million.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 10000


class DimensionImportExportMixin:
    """Reusable mixin providing import-template, bulk-import, and export actions.

    Subclasses can override ``dimension_template_columns`` to customise the CSV
    template and ``get_import_field_mapping`` to extract extra fields from each
    imported row.  The defaults preserve backward compatibility with the legacy
    4-column (code, name, description, is_active) dimension models.

    Also provides a friendly ``destroy()`` that catches ``ProtectedError`` and
    ``IntegrityError`` so blocked deletes return a 400 with a human message
    instead of a 500. NCoA segment rows are commonly referenced by NCoACode,
    Organization, and parent self-FKs — every segment can fail with PROTECT.

    To document required vs optional columns inside the template itself, set
    ``dimension_template_help`` to a list of human-readable lines. Each line is
    written to the CSV prefixed with ``# `` (skipped by the importer via
    ``pd.read_csv(comment='#')``; filtered after read for Excel).
    """

    dimension_label = 'dimension'
    dimension_example_rows: list[list[str]] = []
    dimension_template_columns: list[str] = ['code', 'name', 'description', 'is_active']
    dimension_template_help: list[str] = []

    def destroy(self, request, *args, **kwargs):
        """Override to surface PROTECT / IntegrityError as a clean 400.

        Without this, deleting a segment that is referenced by a composite
        ``NCoACode`` row (or an ``Organization`` row, or a child segment) raises
        ``django.db.models.ProtectedError`` which DRF returns as a 500 — the
        UI then sees only "Request failed with status code 500" with no clue
        about why. We catch the protected condition, count the offending
        related objects, and return a human-readable explanation that points
        the user at the right next step (deactivate instead of delete).
        """
        from django.db.models import ProtectedError
        from django.db.utils import IntegrityError

        instance = self.get_object()
        label = f"{getattr(instance, 'code', '')} — {getattr(instance, 'name', '')}".strip(' —')
        try:
            self.perform_destroy(instance)
        except ProtectedError as exc:
            # exc.protected_objects is a set / queryset of the related rows
            # blocking the delete. We summarise by model + count so the
            # message stays short even when hundreds of rows are protected.
            counts: dict[str, int] = {}
            for obj in exc.protected_objects:
                model_name = obj._meta.verbose_name or obj.__class__.__name__
                counts[str(model_name)] = counts.get(str(model_name), 0) + 1
            blocking = ', '.join(f'{c} {name}' for name, c in counts.items())
            return Response(
                {
                    'detail': (
                        f"Cannot delete {self.dimension_label} "
                        f"\"{label or getattr(instance, 'pk', '')}\": "
                        f"it is referenced by {blocking}. "
                        f"Deactivate it instead (set Active = false), or remove "
                        f"the references first."
                    ),
                    'protected_by': counts,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except IntegrityError as exc:
            # Catch-all for non-PROTECT FK constraints, NOT NULL violations
            # mid-cascade, etc. Less informative than ProtectedError but still
            # better than a 500.
            return Response(
                {
                    'detail': (
                        f"Cannot delete {self.dimension_label} "
                        f"\"{label or getattr(instance, 'pk', '')}\": "
                        f"the database refused the delete due to existing "
                        f"references. Details: {exc}"
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── helpers ────────────────────────────────────────────

    def get_import_field_mapping(self, row: 'pd.Series', columns: set[str]) -> dict:
        """Return a dict of model field→value extracted from *row*.

        Override in subclasses to add segment-specific fields.  The base
        implementation handles the four standard columns.
        """
        description = ''
        if 'description' in columns:
            desc_val = row.get('description', '')
            description = '' if pd.isna(desc_val) else str(desc_val).strip()

        is_active = True
        if 'is_active' in columns:
            raw = str(row.get('is_active', 'true')).strip().lower()
            is_active = raw in ('true', '1', 'yes', 'active')

        return {
            'code': str(row['code']).strip(),
            'name': str(row['name']).strip(),
            'description': description,
            'is_active': is_active,
        }

    def _obj_to_export_dict(self, obj: object) -> dict:
        """Return an ordered dict for a single model instance.

        Override in subclasses to include segment-specific fields.
        """
        result: dict = {}
        for col in self.dimension_template_columns:
            val = getattr(obj, col, '')
            result[col] = '' if val is None else val
        return result

    # ── actions ────────────────────────────────────────────

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """Download a CSV template for dimension imports.

        Output structure (when ``dimension_template_help`` is set):
            # <help line 1>
            # <help line 2>
            # ...
            <header row>
            <example row 1>
            <example row 2>
            ...

        Comment lines are skipped on import via ``pd.read_csv(comment='#')`` and
        a manual filter for Excel — see ``bulk_import`` below.
        """
        import io
        import csv
        from django.http import HttpResponse

        output = io.StringIO()
        # Write each help line as a CSV row whose FIRST cell starts with `# `.
        # We use csv.writer (not raw f-strings) so any commas in the help text
        # are properly quoted and the row stays a valid single-cell record.
        writer = csv.writer(output)
        for line in self.dimension_template_help:
            writer.writerow([f'# {line}'])
        writer.writerow(self.dimension_template_columns)
        for row in self.dimension_example_rows:
            writer.writerow(row)

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="{self.dimension_label}_import_template.csv"'
        )
        return response

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        """Import dimensions from CSV/Excel file."""
        file = request.FILES.get('file')
        if not file:
            return Response(
                {"error": "A CSV or Excel file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024  # 5MB
        if file.size > MAX_IMPORT_FILE_SIZE:
            return Response(
                {"error": "File too large. Maximum 5MB allowed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Detect comment lines/rows BEFORE pandas decides what the header is.
        # Pandas's ``comment='#'`` only catches un-quoted comment lines, but
        # ``csv.writer`` quotes any cell that contains a comma — so a help
        # line like "# REQUIRED columns: code, name" lands in the CSV as
        # ``"# REQUIRED columns: code, name"`` (starts with ``"``, not ``#``)
        # and slips past pandas's filter. Excel has no comment kwarg at all.
        # Stripping comment lines at the source treats both formats the same.
        def _is_comment_cell(cell: str) -> bool:
            s = (cell or '').strip()
            # Cover both raw "# …" and CSV-quoted "\"# …\"" forms.
            return s.startswith('#') or s.startswith('"#') or s.startswith("'#")

        try:
            if file.name.endswith('.xlsx'):
                # Read with no implicit header so we can pick it ourselves.
                # ``dtype=str`` forces every cell to a string so numeric-looking
                # codes (e.g. '10000000000') are NOT auto-promoted to float64
                # and stringified back as '10000000000.0'. Same fix prevents
                # leading-zero stripping ('01' -> '1') across the board.
                # ``keep_default_na=False, na_filter=False`` keeps blanks as
                # empty strings instead of converting to the literal 'nan'.
                df_raw = pd.read_excel(
                    file, header=None, nrows=10000, dtype=str,
                    keep_default_na=False, na_filter=False,
                )
                if df_raw.empty:
                    return Response(
                        {"error": "The uploaded spreadsheet is empty."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                # Walk down to the first row whose first cell is NOT a
                # comment — that's the user's actual header row.
                header_idx = None
                for i in range(len(df_raw)):
                    first = str(df_raw.iloc[i, 0]) if df_raw.shape[1] else ''
                    if first and first.strip() and not _is_comment_cell(first):
                        header_idx = i
                        break
                if header_idx is None:
                    return Response(
                        {"error": "Could not find a header row (every row starts with '#')."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                cols = df_raw.iloc[header_idx].astype(str).tolist()
                df = df_raw.iloc[header_idx + 1:].reset_index(drop=True)
                df.columns = cols
                # Defensive — drop any later comment rows the user may have
                # interleaved between data rows (rare but possible).
                if not df.empty:
                    first_col = df.columns[0]
                    mask = df[first_col].astype(str).map(_is_comment_cell)
                    df = df[~mask].reset_index(drop=True)
            else:
                # CSV: pre-strip comment lines at the line level so any
                # quoted cell starting with ``"#`` is also dropped, then
                # hand the cleaned text to pandas.
                import io as _io
                raw = file.read()
                if isinstance(raw, bytes):
                    # ``utf-8-sig`` strips a BOM if Excel saved the CSV.
                    text = raw.decode('utf-8-sig', errors='replace')
                else:
                    text = str(raw)
                cleaned_lines = []
                for line in text.splitlines():
                    if _is_comment_cell(line):
                        continue
                    cleaned_lines.append(line)
                if not cleaned_lines:
                    return Response(
                        {"error": "The uploaded CSV is empty (or contains only comment lines)."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                # dtype=str — same correctness reason as the xlsx path above.
                df = pd.read_csv(
                    _io.StringIO('\n'.join(cleaned_lines)),
                    nrows=10000, dtype=str,
                    keep_default_na=False, na_filter=False,
                )
        except Exception as e:
            return Response(
                {"error": f"Failed to parse file: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        df.columns = df.columns.str.strip().str.lower()

        required_columns = {'code', 'name'}
        missing = required_columns - set(df.columns)
        if missing:
            return Response(
                {"error": f"Missing required columns: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Use ``get_queryset()`` rather than the class-level ``queryset`` attribute:
        # every NCoA dimension viewset (Administrative, Economic, Functional,
        # Programmes, Fund, Geographic) defines only ``get_queryset()`` and leaves
        # ``queryset`` as None, so ``self.queryset.model`` raises AttributeError.
        # ``.model`` on a queryset doesn't execute the query — it reads the
        # underlying model class, which is cheap and correct.
        model_class = self.get_queryset().model
        # Read each column's actual ``max_length`` from the model so the
        # validator stays in sync as the schema evolves. Falls back to a
        # generous default if the field has no explicit limit (e.g. TextField).
        def _max_len(field_name: str, fallback: int) -> int:
            try:
                ml = model_class._meta.get_field(field_name).max_length
                return int(ml) if ml else fallback
            except Exception:
                return fallback
        code_max_len = _max_len('code', 50)
        name_max_len = _max_len('name', 200)
        columns = set(df.columns)
        created_count = 0
        updated_count = 0
        skipped_count = 0
        errors: list[str] = []

        for index, row in df.iterrows():
            row_num = index + 2
            try:
                fields = self.get_import_field_mapping(row, columns)
                code = fields.pop('code')
                name = fields.get('name', '')

                if not code:
                    errors.append(f"Row {row_num}: Code is empty.")
                    continue
                if len(code) > code_max_len:
                    errors.append(
                        f"Row {row_num}: Code '{code}' is {len(code)} chars; "
                        f"max is {code_max_len}. Remove separators (e.g. write "
                        f"'51000100', not '5-10-01-00')."
                    )
                    continue
                if not name or len(name) > name_max_len:
                    errors.append(
                        f"Row {row_num}: Invalid name (must be 1-{name_max_len} chars)."
                    )
                    continue

                existing = model_class.objects.filter(code=code).first()
                if existing:
                    for attr, val in fields.items():
                        setattr(existing, attr, val)
                    existing.save()
                    updated_count += 1
                else:
                    model_class.objects.create(code=code, **fields)
                    created_count += 1

            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")

        return Response({
            'success': True,
            'created': created_count,
            'updated': updated_count,
            'skipped': skipped_count,
            'errors': errors,
        })

    @action(detail=False, methods=['get'], url_path='export')
    def export_data(self, request):
        """Export all dimension records as CSV or Excel."""
        import io
        import csv
        from django.http import HttpResponse

        # Same NoneType fix as bulk_import — see comment there.
        queryset = self.get_queryset()
        fmt = request.query_params.get('format', 'csv')

        if fmt == 'xlsx':
            data = [self._obj_to_export_dict(obj) for obj in queryset]
            df = pd.DataFrame(data)
            output = io.BytesIO()
            df.to_excel(output, index=False, engine='openpyxl')
            output.seek(0)
            response = HttpResponse(
                output.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            response['Content-Disposition'] = (
                f'attachment; filename="{self.dimension_label}_export.xlsx"'
            )
            return response

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(self.dimension_template_columns)
        for obj in queryset:
            d = self._obj_to_export_dict(obj)
            writer.writerow([d.get(c, '') for c in self.dimension_template_columns])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="{self.dimension_label}_export.csv"'
        )
        return response
