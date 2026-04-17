"""
Serializers for TSA Bank Reconciliation
=======================================
Mirrors the tsa_reconciliation.py models.

Match-count fields (``matched_count`` / ``unmatched_count``) expect the
viewset queryset to annotate them in bulk to avoid N+1 queries (M1); the
fallback is a live count via the reverse manager.
"""
from rest_framework import serializers
from accounting.models import (
    TSABankStatement, TSABankStatementLine, TSAReconciliation,
)


class TSABankStatementLineSerializer(serializers.ModelSerializer):
    # Book-side denormalisation for the match UI.
    matched_payment_number  = serializers.SerializerMethodField()
    matched_revenue_number  = serializers.SerializerMethodField()
    matched_by_name         = serializers.SerializerMethodField()
    amount                  = serializers.DecimalField(
        max_digits=22, decimal_places=2, read_only=True,
    )

    class Meta:
        model = TSABankStatementLine
        fields = [
            'id', 'line_number', 'transaction_date', 'value_date',
            'description', 'reference', 'debit', 'credit', 'balance_after',
            'match_status', 'match_confidence',
            'matched_payment', 'matched_payment_number',
            'matched_revenue', 'matched_revenue_number',
            'matched_by', 'matched_by_name', 'matched_at',
            'updated_at', 'amount',
        ]
        read_only_fields = fields  # mutations go through dedicated actions

    def get_matched_payment_number(self, obj):
        if not obj.matched_payment_id:
            return None
        pi = obj.matched_payment
        return (
            pi.bank_reference
            or (pi.payment_voucher.voucher_number if pi.payment_voucher_id else '')
            or pi.batch_reference
            or f'PI-{pi.id}'
        )

    def get_matched_revenue_number(self, obj):
        if not obj.matched_revenue_id:
            return None
        rc = obj.matched_revenue
        return rc.payment_reference or rc.rrr or f'RC-{rc.id}'

    def get_matched_by_name(self, obj):
        return getattr(obj.matched_by, 'username', None)


class TSABankStatementSerializer(serializers.ModelSerializer):
    tsa_account_number = serializers.CharField(
        source='tsa_account.account_number', read_only=True,
    )
    tsa_account_name   = serializers.CharField(
        source='tsa_account.account_name', read_only=True,
    )
    uploaded_by_name   = serializers.SerializerMethodField()
    matched_count      = serializers.SerializerMethodField()
    unmatched_count    = serializers.SerializerMethodField()
    ignored_count      = serializers.SerializerMethodField()
    file_url           = serializers.SerializerMethodField()

    class Meta:
        model = TSABankStatement
        fields = [
            'id', 'tsa_account', 'tsa_account_number', 'tsa_account_name',
            'original_filename', 'file_url',
            'statement_from', 'statement_to',
            'opening_balance', 'closing_balance',
            'total_debits', 'total_credits', 'line_count',
            'status', 'parse_errors', 'uploaded_by', 'uploaded_by_name',
            'notes', 'created_at',
            'matched_count', 'unmatched_count', 'ignored_count',
            'file_hash',
        ]
        read_only_fields = [f for f in fields if f not in ('notes',)]

    def get_uploaded_by_name(self, obj):
        return getattr(obj.uploaded_by, 'username', None)

    def get_file_url(self, obj):
        """Expose the download URL so users can re-view the uploaded file."""
        if not obj.statement_file:
            return None
        request = self.context.get('request')
        try:
            url = obj.statement_file.url
        except ValueError:
            return None
        return request.build_absolute_uri(url) if request else url

    # N+1 avoidance (M1): prefer the annotated value if present.
    def get_matched_count(self, obj):
        val = getattr(obj, 'annotated_matched_count', None)
        if val is not None:
            return val
        return obj.lines.exclude(match_status='UNMATCHED').count()

    def get_unmatched_count(self, obj):
        val = getattr(obj, 'annotated_unmatched_count', None)
        if val is not None:
            return val
        return obj.lines.filter(match_status='UNMATCHED').count()

    def get_ignored_count(self, obj):
        val = getattr(obj, 'annotated_ignored_count', None)
        if val is not None:
            return val
        return obj.lines.filter(match_status='IGNORED').count()


class TSABankStatementDetailSerializer(TSABankStatementSerializer):
    """Adds the full line set — used only on detail GET."""
    lines = TSABankStatementLineSerializer(many=True, read_only=True)

    class Meta(TSABankStatementSerializer.Meta):
        fields = TSABankStatementSerializer.Meta.fields + ['lines']


class TSAReconciliationSerializer(serializers.ModelSerializer):
    tsa_account_number = serializers.CharField(
        source='tsa_account.account_number', read_only=True,
    )
    tsa_account_name   = serializers.CharField(
        source='tsa_account.account_name', read_only=True,
    )
    difference         = serializers.DecimalField(
        max_digits=22, decimal_places=2, read_only=True,
    )
    completed_by_name  = serializers.SerializerMethodField()

    class Meta:
        model = TSAReconciliation
        fields = [
            'id', 'tsa_account', 'tsa_account_number', 'tsa_account_name',
            'period_start', 'period_end',
            'book_balance', 'statement_balance', 'adjusted_balance',
            'unmatched_debits', 'unmatched_credits', 'difference',
            'statement_import', 'status',
            'completed_at', 'completed_by', 'completed_by_name',
            'notes', 'created_at',
        ]
        read_only_fields = [
            'tsa_account_number', 'tsa_account_name',
            'book_balance', 'adjusted_balance',
            'unmatched_debits', 'unmatched_credits', 'difference',
            'completed_at', 'completed_by_name', 'created_at',
        ]

    def get_completed_by_name(self, obj):
        return getattr(obj.completed_by, 'username', None)
