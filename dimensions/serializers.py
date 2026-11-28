from rest_framework import serializers

from .models import RECORD_TYPES, DimensionType, DimensionValue


def _record_types(value):
    unknown = [v for v in value if v not in RECORD_TYPES]
    if unknown:
        raise serializers.ValidationError(f'Unknown record type(s): {", ".join(unknown)}.')
    return list(value)


class DimensionTypeSerializer(serializers.ModelSerializer):
    parent_type_code = serializers.CharField(source='parent_type.code', read_only=True, default=None)
    value_count = serializers.IntegerField(source='values.count', read_only=True)

    class Meta:
        model = DimensionType
        fields = ['id', 'code', 'name', 'parent_type', 'parent_type_code', 'applies_to', 'required_on',
                  'is_active', 'value_count']

    def validate_applies_to(self, value):
        return _record_types(value)

    def validate_required_on(self, value):
        return _record_types(value)

    def validate(self, attrs):
        applies = attrs.get('applies_to', getattr(self.instance, 'applies_to', []))
        required = attrs.get('required_on', getattr(self.instance, 'required_on', []))
        missing = [r for r in required if r not in applies]
        if missing:
            raise serializers.ValidationError({'required_on': 'A dimension can only be mandatory where it is switched on.'})
        parent = attrs.get('parent_type')
        if parent is not None and self.instance is not None and parent.pk == self.instance.pk:
            raise serializers.ValidationError({'parent_type': 'A dimension cannot be its own parent.'})
        return attrs


class DimensionValueSerializer(serializers.ModelSerializer):
    dimension_type_code = serializers.CharField(source='dimension_type.code', read_only=True)
    parent_code = serializers.CharField(source='parent.code', read_only=True, default=None)

    class Meta:
        model = DimensionValue
        fields = ['id', 'dimension_type', 'dimension_type_code', 'code', 'name', 'parent', 'parent_code', 'is_active']

    def validate(self, attrs):
        dimension = attrs.get('dimension_type', getattr(self.instance, 'dimension_type', None))
        parent = attrs.get('parent', getattr(self.instance, 'parent', None))
        if dimension is not None and parent is not None:
            if dimension.parent_type_id is None:
                raise serializers.ValidationError({'parent': f'{dimension.name} has no parent dimension.'})
            if parent.dimension_type_id != dimension.parent_type_id:
                raise serializers.ValidationError(
                    {'parent': f'The parent must be a {dimension.parent_type.name} value.'})
        return attrs
