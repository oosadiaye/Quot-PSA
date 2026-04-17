from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
import pandas as pd
from ..models import (
    CostCenter, ProfitCenter, CostAllocationRule,
)
from ..serializers import (
    CostCenterSerializer, ProfitCenterSerializer, CostAllocationRuleSerializer,
)


class CostCenterViewSet(viewsets.ModelViewSet):
    queryset = CostCenter.objects.all().select_related('parent', 'manager', 'gl_account')
    serializer_class = CostCenterSerializer
    filterset_fields = ['center_type', 'is_active']
    search_fields = ['name', 'code']

    @action(detail=False, methods=['post'], url_path='import')
    def import_data(self, request):
        """Import cost centers from CSV/Excel file."""
        file = request.FILES.get('file')
        if not file:
            return Response({"error": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)

        MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024  # 5MB
        if file.size > MAX_IMPORT_FILE_SIZE:
            return Response({"error": "File too large. Maximum 5MB allowed."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if file.name.endswith('.csv'):
                df = pd.read_csv(file, nrows=5000)
            else:
                df = pd.read_excel(file, nrows=5000)

            created = 0
            errors = []
            for idx, row in df.iterrows():
                try:
                    CostCenter.objects.update_or_create(
                        code=str(row.get('code', '')).strip(),
                        defaults={
                            'name': str(row.get('name', '')).strip(),
                            'description': str(row.get('description', '')).strip() if pd.notna(row.get('description', '')) else '',
                            'is_active': True,
                        }
                    )
                    created += 1
                except Exception as e:
                    errors.append(f"Row {idx + 2}: {str(e)}")

            return Response({
                "message": f"Imported {created} cost centers.",
                "errors": errors[:20]
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def export(self, request):
        """Export cost centers as CSV."""
        import csv
        from django.http import HttpResponse

        cost_centers = self.filter_queryset(self.get_queryset())
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="cost_centers.csv"'

        writer = csv.writer(response)
        writer.writerow(['Code', 'Name', 'Description', 'Active', 'Parent Code'])
        for cc in cost_centers:
            writer.writerow([cc.code, cc.name, cc.description, cc.is_active, cc.parent.code if cc.parent else ''])
        return response


class ProfitCenterViewSet(viewsets.ModelViewSet):
    queryset = ProfitCenter.objects.all().select_related('manager').prefetch_related('cost_centers')
    serializer_class = ProfitCenterSerializer
    filterset_fields = ['is_active']


class CostAllocationRuleViewSet(viewsets.ModelViewSet):
    queryset = CostAllocationRule.objects.all().select_related('source_cost_center', 'source_account')
    serializer_class = CostAllocationRuleSerializer
    filterset_fields = ['allocation_method', 'is_active']
