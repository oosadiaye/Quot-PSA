from rest_framework import serializers
from .models import (
    ApprovalGroup, ApprovalTemplate, ApprovalTemplateStep, Approval, ApprovalStep, ApprovalLog,
    ApprovalDelegation, WorkflowDefinition, WorkflowStep, WorkflowInstance, WorkflowLog
)
from django.contrib.contenttypes.models import ContentType


class ApprovalGroupSerializer(serializers.ModelSerializer):
    member_names = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalGroup
        fields = [
            'id', 'name', 'description', 'members', 'member_names',
            'min_amount', 'max_amount', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_member_names(self, obj):
        """Return up to 5 member usernames — gated by staff/superuser.

        Without the gate any authenticated user enumerating approval
        groups via the API harvests usernames of every approver in the
        tenant. Group membership / approver identities are sensitive
        meta-data (who approves what, at what threshold). Non-staff
        readers see only the count via ``len(members)`` on the parent
        serializer; the names themselves require elevated read.
        """
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not (user and (user.is_staff or user.is_superuser)):
            return []
        return [u.username for u in obj.members.all()[:5]]


class ApprovalTemplateStepSerializer(serializers.ModelSerializer):
    group_name = serializers.ReadOnlyField(source='group.name')

    class Meta:
        model = ApprovalTemplateStep
        fields = ['id', 'group', 'group_name', 'sequence']
        read_only_fields = ['id']


class ApprovalTemplateSerializer(serializers.ModelSerializer):
    content_type_name = serializers.ReadOnlyField(source='content_type.model')
    steps = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalTemplate
        fields = [
            'id', 'name', 'description', 'content_type', 'content_type_name',
            'approval_type', 'steps', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_steps(self, obj):
        through_qs = ApprovalTemplateStep.objects.filter(
            template=obj
        ).select_related('group').order_by('sequence')
        return ApprovalTemplateStepSerializer(through_qs, many=True).data

    def to_internal_value(self, data):
        """Resolve content_type model name string to PK before validation."""
        if isinstance(data, dict):
            ct_val = data.get('content_type')
            if isinstance(ct_val, str) and not ct_val.isdigit():
                ct = ContentType.objects.filter(model=ct_val).first()
                if not ct:
                    raise serializers.ValidationError({'content_type': f"Unknown document type: {ct_val}"})
                data = {**data, 'content_type': ct.pk}
        return super().to_internal_value(data)

    def create(self, validated_data):
        template = ApprovalTemplate.objects.create(**validated_data)
        steps_data = self.initial_data.get('steps', [])
        for step in steps_data:
            ApprovalTemplateStep.objects.create(
                template=template,
                group_id=int(step['group']),
                sequence=int(step['sequence']),
            )
        return template

    def update(self, instance, validated_data):
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        # Replace steps if provided
        steps_data = self.initial_data.get('steps', None)
        if steps_data is not None:
            ApprovalTemplateStep.objects.filter(template=instance).delete()
            for step in steps_data:
                ApprovalTemplateStep.objects.create(
                    template=instance,
                    group_id=int(step['group']),
                    sequence=int(step['sequence']),
                )
        return instance


class ApprovalStepSerializer(serializers.ModelSerializer):
    approver_name = serializers.ReadOnlyField(source='approver.username')
    group_name = serializers.ReadOnlyField(source='approver_group.name')

    class Meta:
        model = ApprovalStep
        fields = [
            'id', 'approval', 'step_number', 'approver_group', 'group_name',
            'approver', 'approver_name', 'status', 'comment', 'acted_at',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def validate(self, data):
        """Reject an ``approver`` who isn't a member of ``approver_group``.

        The two fields are independent today, so it's possible to assign
        a step to "Director Finance" group but record an approval by a
        user who isn't in that group — defeating the SOD point of the
        group abstraction. Allow it only when the user is staff/super
        (platform admin override, e.g. break-glass approval).
        """
        approver = data.get('approver') or getattr(self.instance, 'approver', None)
        group = data.get('approver_group') or getattr(self.instance, 'approver_group', None)
        if approver and group:
            request = self.context.get('request')
            actor = getattr(request, 'user', None)
            if not (actor and (actor.is_staff or actor.is_superuser)):
                if not group.members.filter(pk=approver.pk).exists():
                    raise serializers.ValidationError({
                        'approver': (
                            f"User '{approver}' is not a member of "
                            f"approver group '{group.name}'."
                        ),
                    })
        return data


class ApprovalLogSerializer(serializers.ModelSerializer):
    user_name = serializers.ReadOnlyField(source='user.username')
    step_number = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalLog
        fields = [
            'id', 'approval', 'step', 'step_number', 'action', 'comment',
            'user', 'user_name',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

    def get_step_number(self, obj):
        return obj.step.step_number if obj.step else None


class ApprovalSerializer(serializers.ModelSerializer):
    steps = ApprovalStepSerializer(many=True, read_only=True)
    logs = ApprovalLogSerializer(many=True, read_only=True)
    content_type_name = serializers.ReadOnlyField(source='content_type.model')
    requested_by_name = serializers.ReadOnlyField(source='requested_by.username')

    class Meta:
        model = Approval
        fields = [
            'id', 'content_type', 'content_type_name', 'object_id',
            'title', 'description', 'amount', 'status', 'current_step',
            'total_steps', 'requested_by', 'requested_by_name', 'template',
            'steps', 'logs',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

class ApprovalDelegationSerializer(serializers.ModelSerializer):
    delegator_name = serializers.ReadOnlyField(source='delegator.username')
    delegate_name = serializers.ReadOnlyField(source='delegate.username')

    class Meta:
        model = ApprovalDelegation
        fields = [
            'id', 'delegator', 'delegator_name', 'delegate', 'delegate_name',
            'start_date', 'end_date', 'is_active', 'reason',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    # Hard ceiling on delegation duration. A delegation that runs for
    # years is almost always a configuration mistake (someone leaving
    # the organisation should be deactivated, not "delegated to forever")
    # and it neuters the audit trail's ability to reason about who was
    # legitimately authorised on a given date. 365 days matches the
    # typical fiscal cycle.
    MAX_DELEGATION_DAYS = 365

    def validate(self, data):
        from django.utils import timezone
        start = data.get('start_date')
        end = data.get('end_date')
        if start and end:
            if end < start:
                raise serializers.ValidationError(
                    {'end_date': 'End date must be on or after start date.'},
                )
            # Reject backdated delegations on creation. Updates may
            # legitimately adjust the end date of an in-flight
            # delegation, so the past-date check only applies when
            # creating a new row.
            if self.instance is None and start < timezone.now().date():
                raise serializers.ValidationError(
                    {'start_date': 'Start date cannot be in the past for a new delegation.'},
                )
            duration_days = (end - start).days
            if duration_days > self.MAX_DELEGATION_DAYS:
                raise serializers.ValidationError(
                    {'end_date': (
                        f'Delegation duration ({duration_days} days) exceeds '
                        f'the {self.MAX_DELEGATION_DAYS}-day maximum. Renew '
                        f'or extend instead of creating an open-ended delegation.'
                    )},
                )
        if data.get('delegator') == data.get('delegate'):
            raise serializers.ValidationError('Cannot delegate to yourself.')
        return data


class WorkflowStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowStep
        fields = ['id', 'name', 'sequence', 'approver_role']
        read_only_fields = ['id']

class WorkflowDefinitionSerializer(serializers.ModelSerializer):
    steps = WorkflowStepSerializer(many=True, read_only=True)
    model_name = serializers.ReadOnlyField(source='target_model.model')

    class Meta:
        model = WorkflowDefinition
        fields = [
            'id', 'name', 'target_model', 'model_name', 'is_active', 'steps',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

class WorkflowLogSerializer(serializers.ModelSerializer):
    step_name = serializers.ReadOnlyField(source='step.name')
    class Meta:
        model = WorkflowLog
        fields = [
            'id', 'instance', 'step', 'step_name', 'action', 'comment',
            'user_display',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

class WorkflowInstanceSerializer(serializers.ModelSerializer):
    logs = WorkflowLogSerializer(many=True, read_only=True)
    workflow_name = serializers.ReadOnlyField(source='workflow.name')
    current_step_name = serializers.ReadOnlyField(source='current_step.name')

    class Meta:
        model = WorkflowInstance
        fields = [
            'id', 'workflow', 'workflow_name', 'status', 'current_step',
            'current_step_name', 'content_type', 'object_id', 'logs',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']
