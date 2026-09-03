from rest_framework import serializers

from .models import SupplierCatalogue, CatalogueItem, PriceHistory


class SupplierCatalogueSerializer(serializers.ModelSerializer):
    is_current = serializers.BooleanField(read_only=True)

    class Meta:
        model = SupplierCatalogue
        fields = [
            'id', 'name', 'supplier', 'reference', 'valid_from', 'valid_to',
            'status', 'framework_agreement', 'is_current',
        ]


class CatalogueItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogueItem
        fields = [
            'id', 'catalogue', 'item', 'unit_price', 'specification',
            'is_active', 'price_effective_date',
        ]


class PriceHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceHistory
        fields = [
            'id', 'item', 'supplier', 'unit_price', 'effective_date',
        ]
