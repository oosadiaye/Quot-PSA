from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    groups = serializers.SlugRelatedField(
        many=True,
        read_only=True,
        slug_field='name'
    )

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_superuser', 'groups', 'permissions']
        read_only_fields = ['id', 'username']

    def get_permissions(self, obj):
        if obj.is_superuser:
            return []
        perm_list = obj.get_all_permissions()
        return [p.split('.')[-1] for p in perm_list]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and not request.user.is_superuser:
            data.pop('is_superuser', None)
        return data


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password_confirm', 'first_name', 'last_name']

    def validate_username(self, value):
        value = value.lower()
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password": "Passwords don't match"})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        validated_data['username'] = validated_data['username'].lower()
        user = User.objects.create_user(**validated_data)
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect")
        return value

    def validate(self, attrs):
        if attrs['old_password'] == attrs['new_password']:
            raise serializers.ValidationError(
                {"new_password": "New password must be different from the current password."}
            )
        return attrs


# ── Tenant User Management Serializers ────────────────────────────────

class TenantUserSerializer(serializers.Serializer):
    """Read serializer for tenant user listing — combines User + UserTenantRole."""
    id = serializers.IntegerField(source='user.id')
    username = serializers.CharField(source='user.username')
    email = serializers.EmailField(source='user.email')
    first_name = serializers.CharField(source='user.first_name')
    last_name = serializers.CharField(source='user.last_name')
    is_active = serializers.BooleanField()
    role = serializers.CharField()
    role_display = serializers.CharField(source='get_role_display')
    groups = serializers.SerializerMethodField()
    employee = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()

    def get_groups(self, obj):
        return list(obj.groups.values_list('name', flat=True))

    def get_employee(self, obj):
        try:
            emp = obj.user.employee
            return {
                'id': emp.id,
                'employee_number': emp.employee_number,
                'department': emp.department.name if emp.department else None,
                'position': emp.position.title if emp.position else None,
            }
        except Exception:
            return None


class TenantUserCreateSerializer(serializers.Serializer):
    """Create a new user and assign them to the current tenant with a role."""
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, required=False, default='')
    last_name = serializers.CharField(max_length=150, required=False, default='')
    password = serializers.CharField(write_only=True, validators=[validate_password])
    role = serializers.ChoiceField(choices=[
        ('senior_manager', 'Senior Manager'),
        ('manager', 'Mid-Level Manager'),
        ('user', 'Standard User'),
        ('viewer', 'Read-Only Viewer'),
    ])
    group_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )
    link_employee = serializers.BooleanField(default=False, required=False)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value


class TenantUserUpdateSerializer(serializers.Serializer):
    """Update an existing tenant user's profile and role."""
    email = serializers.EmailField(required=False)
    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False)
    is_active = serializers.BooleanField(required=False)
    role = serializers.ChoiceField(
        choices=[
            ('senior_manager', 'Senior Manager'),
            ('manager', 'Mid-Level Manager'),
            ('user', 'Standard User'),
            ('viewer', 'Read-Only Viewer'),
        ],
        required=False,
    )
    group_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False
    )


class RoleAssignmentSerializer(serializers.Serializer):
    """Assign a role and groups to a user for the current tenant."""
    role = serializers.ChoiceField(choices=[
        ('senior_manager', 'Senior Manager'),
        ('manager', 'Mid-Level Manager'),
        ('user', 'Standard User'),
        ('viewer', 'Read-Only Viewer'),
    ])
    group_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )
