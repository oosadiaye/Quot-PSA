import logging
from rest_framework import serializers
from .models import Customer, CustomerCategory, Lead, Opportunity, Quotation, QuotationLine, SalesOrder, SalesOrderLine, DeliveryNote, DeliveryNoteLine, SalesReturn, SalesReturnLine, CreditNote

logger = logging.getLogger(__name__)


class CustomerCategorySerializer(serializers.ModelSerializer):
    accounts_receivable_account_name = serializers.CharField(
        source='accounts_receivable_account.name', read_only=True, allow_null=True
    )
    accounts_receivable_account_code = serializers.CharField(
        source='accounts_receivable_account.code', read_only=True, allow_null=True
    )
    customer_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomerCategory
        fields = [
            'id', 'name', 'code', 'description',
            'accounts_receivable_account',
            'accounts_receivable_account_name',
            'accounts_receivable_account_code',
            'customer_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_customer_count(self, obj):
        return obj.customers.count()



class CustomerSerializer(serializers.ModelSerializer):
    credit_available = serializers.ReadOnlyField()
    credit_status = serializers.ReadOnlyField()
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    category_code = serializers.CharField(source='category.code', read_only=True, allow_null=True)
    category_ar_account_name = serializers.CharField(
        source='category.accounts_receivable_account.name', read_only=True, allow_null=True
    )
    category_ar_account_code = serializers.CharField(
        source='category.accounts_receivable_account.code', read_only=True, allow_null=True
    )

    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'customer_code', 'vat_number', 'credit_limit', 'balance',
            'credit_available', 'credit_status', 'is_active',
            'category', 'category_name', 'category_code',
            'category_ar_account_name', 'category_ar_account_code',
            'industry', 'website', 'address',
            'contact_person', 'contact_phone', 'contact_email',
            'payment_terms',
            'withholding_tax_code', 'wht_exempt',
            'created_at', 'updated_at',
        ]

    def validate(self, attrs):
        # Category is required — it carries the AR GL account
        category = attrs.get('category')
        if not category and not self.instance:
            raise serializers.ValidationError({'category': 'Customer category is required.'})
        if self.instance and 'category' in attrs and not attrs['category']:
            raise serializers.ValidationError({'category': 'Customer category is required.'})

        credit_limit = attrs.get('credit_limit')
        if credit_limit is not None and credit_limit < 0:
            raise serializers.ValidationError({'credit_limit': 'Credit limit cannot be negative'})

        email = attrs.get('contact_email')
        if email and '@' not in email:
            raise serializers.ValidationError({'contact_email': 'Invalid email format'})

        return attrs

class LeadSerializer(serializers.ModelSerializer):
    converted_customer_name = serializers.ReadOnlyField(source='converted_to_customer.name')
    duplicate_warning = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = [
            'id', 'name', 'company', 'email', 'phone', 'source', 'status',
            'estimated_value', 'notes', 'converted_to_customer',
            'converted_customer_name', 'converted_date',
            'duplicate_warning',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_duplicate_warning(self, obj):
        return getattr(obj, '_duplicate_warning', None)

    def validate(self, attrs):
        """HR-M1: Check for duplicate leads by email or phone."""
        email = attrs.get('email')
        phone = attrs.get('phone')
        duplicates = []
        
        if email:
            existing = Lead.objects.filter(email__iexact=email)
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                duplicates.append(f"Email '{email}' already exists")
        
        if phone:
            existing = Lead.objects.filter(phone=phone)
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                duplicates.append(f"Phone '{phone}' already exists")
        
        if duplicates:
            attrs['_duplicate_warning'] = '; '.join(duplicates)
        
        return attrs

class OpportunitySerializer(serializers.ModelSerializer):
    customer_name = serializers.ReadOnlyField(source='customer.name')
    lead_name = serializers.ReadOnlyField(source='lead.name')

    class Meta:
        model = Opportunity
        fields = [
            'id', 'name', 'customer', 'customer_name', 'lead', 'lead_name',
            'stage', 'expected_close_date', 'probability', 'expected_value',
            'notes',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

class QuotationLineSerializer(serializers.ModelSerializer):
    total_price = serializers.ReadOnlyField()
    item_name = serializers.CharField(source='item.name', read_only=True, allow_null=True)
    
    class Meta:
        model = QuotationLine
        fields = ['id', 'item', 'item_name', 'item_description', 'quantity', 'unit_price', 'discount_percent', 'total_price']

class QuotationSerializer(serializers.ModelSerializer):
    lines = QuotationLineSerializer(many=True)
    # Allow blank so the serializer passes validation; create() auto-generates if omitted
    quotation_number = serializers.CharField(required=False, allow_blank=True)
    customer_name = serializers.ReadOnlyField(source='customer.name')
    mda_name = serializers.ReadOnlyField(source='mda.name', allow_null=True)
    fund_name = serializers.ReadOnlyField(source='fund.name', allow_null=True)
    function_name = serializers.ReadOnlyField(source='function.name', allow_null=True)
    program_name = serializers.ReadOnlyField(source='program.name', allow_null=True)
    geo_name = serializers.ReadOnlyField(source='geo.name', allow_null=True)
    total_amount = serializers.SerializerMethodField()
    price_list_name = serializers.ReadOnlyField(source='price_list.name', allow_null=True)
    tax_code_name = serializers.CharField(source='tax_code.name', read_only=True, allow_null=True)
    tax_code_rate = serializers.DecimalField(source='tax_code.rate', max_digits=8, decimal_places=4, read_only=True, allow_null=True)

    class Meta:
        model = Quotation
        fields = [
            'id', 'quotation_number', 'customer', 'customer_name', 'quotation_date', 'valid_until',
            'mda', 'mda_name', 'fund', 'fund_name', 'function', 'function_name',
            'program', 'program_name', 'geo', 'geo_name',
            'status', 'notes', 'terms', 'total_amount', 'lines',
            'price_list', 'price_list_name',
            'tax_code', 'tax_code_name', 'tax_code_rate', 'wht_exempt',
            'created_at', 'updated_at'
        ]
    
    def get_total_amount(self, obj):
        return sum(line.total_price for line in obj.lines.all())

    def _get_price_from_list(self, price_list, item, quantity):
        """Get price for item from price list."""
        if not price_list:
            return None
        try:
            price_item = price_list.items.filter(
                item=item,
                min_quantity__lte=quantity
            ).order_by('-min_quantity').first()
            if price_item:
                return {
                    'unit_price': price_item.unit_price,
                    'discount_percent': price_item.discount_percent,
                }
        except Exception as exc:
            logger.warning(
                "sales serializer: could not fetch price list for item %s "
                "(qty=%s): %s", getattr(item, 'pk', item), quantity, exc,
            )
        return None

    def create(self, validated_data):
        lines_data = validated_data.pop('lines', [])
        from django.utils.crypto import get_random_string
        if not validated_data.get('quotation_number'):
            validated_data['quotation_number'] = f"QT-{get_random_string(8, allowed_chars='0123456789')}"
        
        price_list = validated_data.get('price_list')
        
        quotation = Quotation.objects.create(**validated_data)
        for line_data in lines_data:
            item_id = line_data.get('item') if isinstance(line_data, dict) else getattr(line_data, 'item', None)
            quantity = line_data.get('quantity') if isinstance(line_data, dict) else getattr(line_data, 'quantity', 1)
            
            if price_list and item_id:
                price_info = self._get_price_from_list(price_list, item_id, quantity)
                if price_info:
                    line_data['unit_price'] = price_info['unit_price']
                    line_data['discount_percent'] = price_info['discount_percent']
            
            if isinstance(line_data, dict):
                QuotationLine.objects.create(quotation=quotation, **line_data)
            else:
                line_data.quotation = quotation
                line_data.save()
        return quotation

class SalesOrderLineSerializer(serializers.ModelSerializer):
    total_price = serializers.ReadOnlyField()
    item_name = serializers.CharField(source='item.name', read_only=True, allow_null=True)
    product_type_name = serializers.CharField(source='product_type.get_name_display', read_only=True, allow_null=True)
    product_category_name = serializers.CharField(source='product_category.name', read_only=True, allow_null=True)
    
    class Meta:
        model = SalesOrderLine
        fields = [
            'id', 'item_description', 'quantity', 'unit_price', 'discount_percent', 'total_price',
            'item', 'item_name', 'product_type', 'product_type_name',
            'product_category', 'product_category_name'
        ]

class SalesOrderSerializer(serializers.ModelSerializer):
    lines = SalesOrderLineSerializer(many=True)
    customer_name = serializers.ReadOnlyField(source='customer.name')
    mda_name = serializers.ReadOnlyField(source='mda.name', allow_null=True)
    fund_name = serializers.ReadOnlyField(source='fund.name', allow_null=True)
    function_name = serializers.ReadOnlyField(source='function.name', allow_null=True)
    program_name = serializers.ReadOnlyField(source='program.name', allow_null=True)
    geo_name = serializers.ReadOnlyField(source='geo.name', allow_null=True)
    revenue_account_name = serializers.CharField(source='revenue_account.name', read_only=True, allow_null=True)
    subtotal = serializers.ReadOnlyField()
    total_amount = serializers.ReadOnlyField()
    
    class Meta:
        model = SalesOrder
        fields = [
            'id', 'order_number', 'customer', 'customer_name', 'quotation', 'order_date',
            'expected_delivery_date', 'mda', 'mda_name',
            'fund', 'fund_name', 'function', 'function_name',
            'program', 'program_name', 'geo', 'geo_name',
            'revenue_account', 'revenue_account_name',
            'delivery_address', 'delivery_contact', 'payment_terms',
            'tax_rate', 'tax_amount', 'subtotal', 'total_amount',
            'tax_code', 'wht_exempt',
            'notes', 'terms_and_conditions', 'status',
            'lines', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'order_number', 'created_at', 'updated_at']
    
    def validate(self, attrs):
        """Add custom validation for sales order"""
        # Validate lines exist
        lines = attrs.get('lines', [])
        if not lines or len(lines) == 0:
            raise serializers.ValidationError({'lines': 'At least one line item is required'})
        
        # Validate each line has positive quantity and price
        for idx, line in enumerate(lines):
            if line.get('quantity', 0) <= 0:
                raise serializers.ValidationError({f'lines[{idx}]': 'Quantity must be positive'})
            if line.get('unit_price', 0) <= 0:
                raise serializers.ValidationError({f'lines[{idx}]': 'Unit price must be positive'})
            if line.get('discount_percent', 0) < 0:
                raise serializers.ValidationError({f'lines[{idx}]': 'Discount cannot be negative'})
            if line.get('discount_percent', 0) > 100:
                raise serializers.ValidationError({f'lines[{idx}]': 'Discount cannot exceed 100%'})
        
        # Validate tax rate
        tax_rate = attrs.get('tax_rate', 0)
        if tax_rate < 0:
            raise serializers.ValidationError({'tax_rate': 'Tax rate cannot be negative'})
        if tax_rate > 100:
            raise serializers.ValidationError({'tax_rate': 'Tax rate cannot exceed 100%'})
        
        return attrs
    
    def create(self, validated_data):
        lines_data = validated_data.pop('lines', [])
        from django.utils.crypto import get_random_string
        from decimal import Decimal
        
        # O2C-H2: Credit Check at SO Creation - Show warning if credit exceeded
        customer = validated_data.get('customer')
        if customer and customer.credit_check_enabled:
            order_total = sum(
                Decimal(str(line.get('quantity', 0))) * Decimal(str(line.get('unit_price', 0)))
                for line in lines_data
            )
            credit_available = customer.credit_available
            
            if order_total > credit_available:
                import warnings
                warnings.warn(
                    f"Credit warning: Order total ({order_total}) exceeds available credit ({credit_available}) "
                    f"for customer {customer.name}. Order will be created but approval may be blocked.",
                    UserWarning
                )
        
        if 'order_number' not in validated_data:
            validated_data['order_number'] = f"SO-{get_random_string(8, allowed_chars='0123456789')}"
        order = SalesOrder.objects.create(**validated_data)
        for line_data in lines_data:
            SalesOrderLine.objects.create(order=order, **line_data)
        return order

class DeliveryNoteLineSerializer(serializers.ModelSerializer):
    item_description = serializers.ReadOnlyField(source='so_line.item_description')
    line_total = serializers.ReadOnlyField()
    
    class Meta:
        model = DeliveryNoteLine
        fields = ['id', 'so_line', 'item_description', 'quantity_delivered', 'line_total']

class DeliveryNoteSerializer(serializers.ModelSerializer):
    lines = DeliveryNoteLineSerializer(many=True)
    so_number = serializers.ReadOnlyField(source='sales_order.order_number')
    customer_name = serializers.ReadOnlyField(source='sales_order.customer.name')
    
    class Meta:
        model = DeliveryNote
        fields = [
            'id', 'delivery_number', 'sales_order', 'so_number', 'customer_name',
            'delivery_date', 'delivered_by', 'status',
            'driver_name', 'vehicle_number', 'notes',
            'lines', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'delivery_number', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        lines_data = validated_data.pop('lines', [])
        from django.utils.crypto import get_random_string
        if 'delivery_number' not in validated_data:
            validated_data['delivery_number'] = f"DN-{get_random_string(8, allowed_chars='0123456789')}"
        delivery = DeliveryNote.objects.create(**validated_data)
        for line_data in lines_data:
            DeliveryNoteLine.objects.create(delivery_note=delivery, **line_data)
        return delivery


class SalesReturnLineSerializer(serializers.ModelSerializer):
    total_amount = serializers.ReadOnlyField()
    item_name = serializers.CharField(source='item.name', read_only=True, allow_null=True)

    class Meta:
        model = SalesReturnLine
        fields = ['id', 'sales_order_line', 'item', 'item_name', 'quantity', 'unit_price', 'reason', 'total_amount']


class SalesReturnSerializer(serializers.ModelSerializer):
    lines = SalesReturnLineSerializer(many=True, read_only=True)
    customer_name = serializers.ReadOnlyField(source='customer.name')

    class Meta:
        model = SalesReturn
        fields = [
            'id', 'return_number', 'sales_order', 'customer', 'customer_name',
            'return_date', 'reason', 'status', 'lines',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CreditNoteSerializer(serializers.ModelSerializer):
    customer_name = serializers.ReadOnlyField(source='customer.name')
    return_number = serializers.ReadOnlyField(source='sales_return.return_number')

    class Meta:
        model = CreditNote
        fields = [
            'id', 'credit_note_number', 'customer', 'customer_name',
            'sales_return', 'return_number',
            'issue_date', 'amount', 'tax_amount', 'total_amount',
            'reason', 'status',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'total_amount', 'created_at', 'updated_at']
