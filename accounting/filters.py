import django_filters
from .models import JournalHeader
from django.db.models import Q

class JournalFilter(django_filters.FilterSet):
    document_number = django_filters.CharFilter(lookup_expr='icontains')
    reference_number = django_filters.CharFilter(lookup_expr='icontains')
    description = django_filters.CharFilter(lookup_expr='icontains')

    # Filter for headers that contain at least one line with this account code or name
    account = django_filters.CharFilter(method='filter_by_account')

    # Amount filters (mapping to the annotated fields total_debit/total_credit)
    min_amount = django_filters.NumberFilter(field_name='total_debit', lookup_expr='gte')
    max_amount = django_filters.NumberFilter(field_name='total_debit', lookup_expr='lte')

    class Meta:
        model = JournalHeader
        fields = ['status', 'posting_date', 'document_number', 'reference_number']

    def filter_by_account(self, queryset, name, value):
        return queryset.filter(
            Q(lines__account__code__icontains=value) |
            Q(lines__account__name__icontains=value)
        ).distinct()
