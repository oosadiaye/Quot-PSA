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
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 1000


class DimensionImportExportMixin:
    """Reusable mixin providing import-template, bulk-import, and export actions.

    Subclasses can override ``dimension_template_columns`` to customise the CSV
    template and ``get_import_field_mapping`` to extract extra fields from each
    imported row.  The defaults preserve backward compatibility with the legacy
    4-column (code, name, description, is_active) dimension models.
    """

    dimension_label = 'dimension'
    dimension_example_rows: list[list[str]] = []
    dimension_template_columns: list[str] = ['code', 'name', 'description', 'is_active']

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
        """Download a CSV template for dimension imports."""
        import io
        import csv
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv.writer(output)
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

        try:
            if file.name.endswith('.xlsx'):
                df = pd.read_excel(file, nrows=10000)
            else:
                df = pd.read_csv(file, nrows=10000)
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

        model_class = self.queryset.model
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

                if not code or len(code) > 50:
                    errors.append(f"Row {row_num}: Invalid code '{code}'.")
                    continue
                if not name or len(name) > 200:
                    errors.append(f"Row {row_num}: Invalid name (must be 1-200 chars).")
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

        queryset = self.queryset.all()
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
