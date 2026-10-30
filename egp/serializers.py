from rest_framework import serializers

from .models import (
    TenderNotice,
    BidderRegistration,
    Bid,
    BidDocument,
    BidOpening,
    EvaluationCommittee,
    EvaluationCriterion,
    BidScore,
    TenderAward,
)


class TenderNoticeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenderNotice
        fields = [
            'id', 'reference', 'title', 'description', 'category', 'method',
            'published_date', 'closing_date', 'status', 'documents',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class BidderRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = BidderRegistration
        fields = [
            'id', 'vendor', 'status', 'certificate_expiry',
            'tax_clearance_expiry', 'pencom_evidence', 'itf_compliance',
            'categories', 'registered_at',
        ]
        read_only_fields = ['registered_at']


class BidSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bid
        fields = [
            'id', 'tender', 'bidder', 'status', 'submitted_at',
            'encrypted_payload', 'payload_hash', 'opened_at', 'opened_by',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['payload_hash', 'opened_at', 'opened_by', 'created_at', 'updated_at']


class BidDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = BidDocument
        fields = ['id', 'bid', 'name', 'file']


class BidOpeningSerializer(serializers.ModelSerializer):
    class Meta:
        model = BidOpening
        fields = [
            'id', 'tender', 'opened_at', 'attendance', 'opened_by', 'minutes',
        ]
        read_only_fields = ['opened_by']


class EvaluationCommitteeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvaluationCommittee
        fields = ['id', 'tender', 'name', 'members', 'is_active']


class EvaluationCriterionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvaluationCriterion
        fields = ['id', 'committee', 'name', 'weight']


class BidScoreSerializer(serializers.ModelSerializer):
    weighted_score = serializers.DecimalField(read_only=True, max_digits=6, decimal_places=2)

    class Meta:
        model = BidScore
        fields = ['id', 'bid', 'criterion', 'score', 'weighted_score', 'comment', 'scored_by']
        read_only_fields = ['scored_by']


class TenderAwardSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenderAward
        fields = [
            'id', 'tender', 'winning_bid', 'status', 'award_amount',
            'contract', 'purchase_order', 'awarded_at', 'awarded_by',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['awarded_at', 'awarded_by', 'created_at', 'updated_at']
