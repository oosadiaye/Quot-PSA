"""
REP-L1: Quality Metrics Reports
Inspection pass/fail rate reports and quality analytics.
"""
from decimal import Decimal
from django.db.models import Count, Avg, Sum, Q
from django.utils import timezone


class QualityMetricsService:
    """Service for generating quality metrics and reports."""

    @staticmethod
    def get_pass_fail_rate(date_from=None, date_to=None, inspection_type=None):
        """
        Get pass/fail rate for inspections.
        
        Args:
            date_from: Start date filter
            date_to: End date filter
            inspection_type: Filter by type (Incoming, InProcess, Final)
            
        Returns:
            dict with pass/fail counts and rates
        """
        from quality.models import QualityInspection, InspectionLine
        
        queryset = QualityInspection.objects.all()
        
        if date_from:
            queryset = queryset.filter(inspection_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(inspection_date__lte=date_to)
        if inspection_type:
            queryset = queryset.filter(inspection_type=inspection_type)
        
        total_inspections = queryset.count()
        passed = queryset.filter(lines__result='Pass').distinct().count()
        failed = queryset.filter(lines__result='Fail').distinct().count()
        
        return {
            'total_inspections': total_inspections,
            'passed': passed,
            'failed': failed,
            'pass_rate': round((passed / total_inspections * 100) if total_inspections > 0 else 0, 2),
            'fail_rate': round((failed / total_inspections * 100) if total_inspections > 0 else 0, 2),
        }

    @staticmethod
    def get_ncr_summary(date_from=None, date_to=None):
        """
        Get NCR (Non-Conformance Report) summary.
        
        Returns:
            dict with NCR counts by severity and status
        """
        from quality.models import NonConformance
        
        queryset = NonConformance.objects.all()
        
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        
        total = queryset.count()
        by_severity = dict(
            queryset.values('severity')
            .annotate(count=Count('id'))
            .values_list('severity', 'count')
        )
        by_status = dict(
            queryset.values('status')
            .annotate(count=Count('id'))
            .values_list('status', 'count')
        )
        
        return {
            'total_ncrs': total,
            'by_severity': by_severity,
            'by_status': by_status,
        }

    @staticmethod
    def get_supplier_quality_score(date_from=None, date_to=None, limit=10):
        """
        Get quality scores by supplier based on incoming inspection results.
        
        Returns:
            list of suppliers with quality scores
        """
        from quality.models import QualityInspection, InspectionLine
        from procurement.models import GoodsReceivedNote, PurchaseOrder
        
        queryset = QualityInspection.objects.filter(inspection_type='Incoming')
        
        if date_from:
            queryset = queryset.filter(inspection_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(inspection_date__lte=date_to)
        
        results = []
        
        for inspection in queryset.select_related('goods_received_note__purchase_order__vendor').distinct():
            if not inspection.goods_received_note or not inspection.goods_received_note.purchase_order:
                continue
                
            vendor = inspection.goods_received_note.purchase_order.vendor
            if not vendor:
                continue
            
            total_lines = inspection.lines.count()
            passed_lines = inspection.lines.filter(result='Pass').count()
            failed_lines = inspection.lines.filter(result='Fail').count()
            
            score = (passed_lines / total_lines * 100) if total_lines > 0 else 0
            
            results.append({
                'supplier_id': vendor.id,
                'supplier_name': vendor.name,
                'inspections': 1,
                'total_items': total_lines,
                'passed': passed_lines,
                'failed': failed_lines,
                'quality_score': round(score, 2),
            })
        
        return results

    @staticmethod
    def get_inspection_trend(months=6):
        """
        Get monthly inspection trends.
        
        Args:
            months: Number of months to include
            
        Returns:
            list of monthly inspection data
        """
        from django.db.models.functions import TruncMonth
        from quality.models import QualityInspection
        
        today = timezone.now().date()
        start_date = today.replace(day=1)
        for _ in range(months - 1):
            from datetime import relativedelta
            start_date = start_date - relativedelta(months=1)
        
        monthly_data = []
        
        for i in range(months):
            month_start = start_date.replace(day=1)
            from datetime import relativedelta
            month_end = month_start + relativedelta(months=1, days=-1)
            
            inspections = QualityInspection.objects.filter(
                inspection_date__gte=month_start,
                inspection_date__lte=month_end
            )
            
            total = inspections.count()
            passed = inspections.filter(lines__result='Pass').distinct().count()
            failed = inspections.filter(lines__result='Fail').distinct().count()
            
            monthly_data.append({
                'month': month_start.strftime('%Y-%m'),
                'total': total,
                'passed': passed,
                'failed': failed,
                'pass_rate': round((passed / total * 100) if total > 0 else 0, 2),
            })
            
            start_date = month_start + relativedelta(months=1)
        
        return monthly_data
