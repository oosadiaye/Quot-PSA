from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from django.db.models import Sum, F, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from decimal import Decimal
import pandas as pd


class AccountingPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 1000


class DimensionImportExportMixin:
    """Reusable mixin providing import-template, bulk-import, and export actions for dimension models."""

    dimension_label = 'dimension'
    dimension_example_rows = []

    @action(detail=False, methods=['get'], url_path='import-template')
    def import_template(self, request):
        """Download a CSV template for dimension imports."""
        import io
        import csv
        from django.http import HttpResponse

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['code', 'name', 'description', 'is_active'])
        for row in self.dimension_example_rows:
            writer.writerow(row)

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{self.dimension_label}_import_template.csv"'
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
        created_count = 0
        updated_count = 0
        skipped_count = 0
        errors = []

        for index, row in df.iterrows():
            row_num = index + 2
            try:
                code = str(row['code']).strip()
                name = str(row['name']).strip()

                if not code or len(code) > 20:
                    errors.append(f"Row {row_num}: Invalid code '{code}' (must be 1-20 characters).")
                    continue

                if not name or len(name) > 100:
                    errors.append(f"Row {row_num}: Invalid name (must be 1-100 characters).")
                    continue

                description = ''
                if 'description' in df.columns:
                    desc_val = row.get('description', '')
                    description = '' if pd.isna(desc_val) else str(desc_val).strip()

                is_active = True
                if 'is_active' in df.columns:
                    raw = str(row.get('is_active', 'true')).strip().lower()
                    is_active = raw in ('true', '1', 'yes', 'active')

                existing = model_class.objects.filter(code=code).first()
                if existing:
                    existing.name = name
                    existing.description = description
                    existing.is_active = is_active
                    existing.save()
                    updated_count += 1
                else:
                    model_class.objects.create(
                        code=code,
                        name=name,
                        description=description,
                        is_active=is_active,
                    )
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
            data = []
            for obj in queryset:
                data.append({
                    'code': obj.code,
                    'name': obj.name,
                    'description': obj.description or '',
                    'is_active': obj.is_active,
                })
            df = pd.DataFrame(data)
            output = io.BytesIO()
            df.to_excel(output, index=False, engine='openpyxl')
            output.seek(0)
            response = HttpResponse(
                output.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            response['Content-Disposition'] = f'attachment; filename="{self.dimension_label}_export.xlsx"'
            return response

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['code', 'name', 'description', 'is_active'])
        for obj in queryset:
            writer.writerow([obj.code, obj.name, obj.description or '', obj.is_active])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{self.dimension_label}_export.csv"'
        return response
