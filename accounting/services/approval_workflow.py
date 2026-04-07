"""Approval Workflow Service

Provides configurable multi-level approval workflows for:
- Journal entries
- Vendor/Customer invoices
- Budget amendments/transfers
- Payments
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.models import User
from accounting.models import ApprovalRule, ApprovalLevel, ApprovalInstance


@dataclass
class ApprovalCheckResult:
    """Result of approval requirement check."""
    requires_approval: bool
    approval_levels: List[Dict[str, Any]]
    is_auto_approvable: bool
    auto_approved_by: Optional[str]
    messages: List[str]


@dataclass
class ApprovalActionResult:
    """Result of an approval action."""
    success: bool
    action: str
    new_status: str
    message: str
    next_level: Optional[int]
    is_fully_approved: bool


class ApprovalWorkflowService:
    """Service for managing approval workflows."""

    @classmethod
    def check_approval_required(
        cls,
        document_type: str,
        amount: Decimal,
        user: User,
        document_id: int = None
    ) -> ApprovalCheckResult:
        """
        Check if a document requires approval.
        
        Args:
            document_type: Type of document (e.g., 'JE', 'VI')
            amount: Document amount
            user: User submitting the document
            document_id: Optional document ID for context
            
        Returns:
            ApprovalCheckResult with approval requirements
        """
        messages = []
        
        rule = cls.get_applicable_rule(document_type, amount)
        
        if not rule:
            return ApprovalCheckResult(
                requires_approval=False,
                approval_levels=[],
                is_auto_approvable=True,
                auto_approved_by='SYSTEM',
                messages=["No approval rule found for this document type/amount"],
            )
        
        levels = []
        for level in rule.levels.all():
            levels.append({
                'level': level.level,
                'approver_type': level.approver_type,
                'approver_value': level.approver_value,
                'min_approvers': level.min_approvers,
            })
        
        is_auto = cls._is_auto_approvable(rule, user)
        
        return ApprovalCheckResult(
            requires_approval=True,
            approval_levels=levels,
            is_auto_approvable=is_auto,
            auto_approved_by=user.username if is_auto else None,
            messages=[f"Approval required: {len(levels)} level(s)"] if levels else [],
        )

    @classmethod
    def get_applicable_rule(cls, document_type: str, amount: Decimal) -> Optional[ApprovalRule]:
        """Get the most applicable approval rule for a document."""
        rules = ApprovalRule.objects.filter(
            document_type=document_type,
            is_active=True,
            min_amount__lte=amount,
        )
        
        for rule in rules.order_by('-min_amount'):
            if rule.max_amount is None or rule.max_amount >= amount:
                return rule
        
        return None

    @classmethod
    def _is_auto_approvable(cls, rule: ApprovalRule, user: User) -> bool:
        """Check if a rule allows auto-approval for this user."""
        if not rule.approval_levels:
            return True
        
        if not rule.auto_approve_roles:
            return False
        
        user_roles = list(user.groups.values_list('name', flat=True))
        
        for role in rule.auto_approve_roles:
            if role in user_roles:
                return True
        
        return False

    @classmethod
    def submit_for_approval(
        cls,
        document_type: str,
        document_id: int,
        amount: Decimal,
        user: User,
        reference_number: str = '',
        description: str = ''
    ) -> ApprovalInstance:
        """
        Submit a document for approval.
        
        Args:
            document_type: Type of document
            document_id: Document ID
            amount: Document amount
            user: User submitting
            reference_number: Document reference
            description: Document description
            
        Returns:
            ApprovalInstance for tracking
        """
        check_result = cls.check_approval_required(
            document_type, amount, user, document_id
        )
        
        instance = ApprovalInstance.objects.create(
            document_type=document_type,
            document_id=document_id,
            reference_number=reference_number,
            amount=amount,
            description=description,
            submitted_by=user,
            current_level=0,
            max_level=len(check_result.approval_levels),
            status='PENDING' if check_result.requires_approval else 'APPROVED',
            approvals=[],
        )
        
        if check_result.is_auto_approvable:
            cls._record_auto_approval(instance, user)
        
        return instance

    @classmethod
    def _record_auto_approval(cls, instance: ApprovalInstance, user: User):
        """Record automatic approval."""
        instance.approvals.append({
            'level': 0,
            'user_id': user.id,
            'username': user.username,
            'action': 'AUTO_APPROVE',
            'timestamp': timezone.now().isoformat(),
            'comment': 'Auto-approved by system',
        })
        instance.status = 'APPROVED'
        instance.completed_at = timezone.now()
        instance.completed_by = user
        instance.save()

    @classmethod
    def approve(
        cls,
        instance_id: int,
        user: User,
        level: int = None,
        comment: str = ''
    ) -> ApprovalActionResult:
        """
        Approve a document at the current level.
        
        Args:
            instance_id: ApprovalInstance ID
            user: User approving
            level: Specific level to approve (optional)
            comment: Approval comment
            
        Returns:
            ApprovalActionResult with action outcome
        """
        try:
            instance = ApprovalInstance.objects.get(id=instance_id)
        except ApprovalInstance.DoesNotExist:
            return ApprovalActionResult(
                success=False,
                action='APPROVE',
                new_status='ERROR',
                message='Approval instance not found',
                next_level=None,
                is_fully_approved=False,
            )
        
        if instance.status != 'PENDING':
            return ApprovalActionResult(
                success=False,
                action='APPROVE',
                new_status=instance.status,
                message=f'Cannot approve: document is {instance.status}',
                next_level=instance.current_level,
                is_fully_approved=False,
            )
        
        target_level = level or (instance.current_level + 1)
        
        instance.approvals.append({
            'level': target_level,
            'user_id': user.id,
            'username': user.username,
            'action': 'APPROVE',
            'timestamp': timezone.now().isoformat(),
            'comment': comment,
        })
        
        instance.current_level = target_level
        
        if target_level >= instance.max_level:
            instance.status = 'APPROVED'
            instance.completed_at = timezone.now()
            instance.completed_by = user
            
            cls._execute_document_action(instance)
            
            return ApprovalActionResult(
                success=True,
                action='APPROVE',
                new_status='APPROVED',
                message='Document fully approved',
                next_level=None,
                is_fully_approved=True,
            )
        
        instance.save()
        
        return ApprovalActionResult(
            success=True,
            action='APPROVE',
            new_status='PENDING',
            message=f'Level {target_level} approved, {instance.max_level - target_level} more levels required',
            next_level=target_level + 1,
            is_fully_approved=False,
        )

    @classmethod
    def reject(
        cls,
        instance_id: int,
        user: User,
        reason: str
    ) -> ApprovalActionResult:
        """
        Reject a document.
        
        Args:
            instance_id: ApprovalInstance ID
            user: User rejecting
            reason: Rejection reason
            
        Returns:
            ApprovalActionResult with action outcome
        """
        try:
            instance = ApprovalInstance.objects.get(id=instance_id)
        except ApprovalInstance.DoesNotExist:
            return ApprovalActionResult(
                success=False,
                action='REJECT',
                new_status='ERROR',
                message='Approval instance not found',
                next_level=None,
                is_fully_approved=False,
            )
        
        if instance.status != 'PENDING':
            return ApprovalActionResult(
                success=False,
                action='REJECT',
                new_status=instance.status,
                message=f'Cannot reject: document is {instance.status}',
                next_level=instance.current_level,
                is_fully_approved=False,
            )
        
        instance.approvals.append({
            'level': instance.current_level,
            'user_id': user.id,
            'username': user.username,
            'action': 'REJECT',
            'timestamp': timezone.now().isoformat(),
            'reason': reason,
        })
        
        instance.status = 'REJECTED'
        instance.rejection_reason = reason
        instance.completed_at = timezone.now()
        instance.completed_by = user
        instance.save()
        
        cls._execute_rejection_action(instance)
        
        return ApprovalActionResult(
            success=True,
            action='REJECT',
            new_status='REJECTED',
            message=f'Document rejected: {reason}',
            next_level=None,
            is_fully_approved=False,
        )

    @classmethod
    def _execute_document_action(cls, instance: ApprovalInstance):
        """Execute the document-specific action after full approval."""
        pass

    @classmethod
    def _execute_rejection_action(cls, instance: ApprovalInstance):
        """Execute the document-specific action after rejection."""
        pass

    @classmethod
    def get_pending_approvals(
        cls,
        user: User = None,
        document_type: str = None,
        level: int = None
    ) -> List[ApprovalInstance]:
        """
        Get pending approvals, optionally filtered.
        
        Args:
            user: Filter by approver (optional)
            document_type: Filter by document type (optional)
            level: Filter by current level (optional)
            
        Returns:
            List of ApprovalInstance objects
        """
        queryset = ApprovalInstance.objects.filter(status='PENDING')
        
        if document_type:
            queryset = queryset.filter(document_type=document_type)
        
        if level is not None:
            queryset = queryset.filter(current_level=level)
        
        return list(queryset.order_by('-submitted_at'))

    @classmethod
    def get_approval_status(
        cls,
        document_type: str,
        document_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get the approval status for a document.
        
        Args:
            document_type: Type of document
            document_id: Document ID
            
        Returns:
            Dictionary with approval status or None
        """
        try:
            instance = ApprovalInstance.objects.get(
                document_type=document_type,
                document_id=document_id
            )
        except ApprovalInstance.DoesNotExist:
            return None
        
        return {
            'status': instance.status,
            'current_level': instance.current_level,
            'max_level': instance.max_level,
            'approvals': instance.approvals,
            'submitted_by': instance.submitted_by.username if instance.submitted_by else None,
            'submitted_at': instance.submitted_at.isoformat() if instance.submitted_at else None,
            'completed_at': instance.completed_at.isoformat() if instance.completed_at else None,
            'rejection_reason': instance.rejection_reason,
        }
