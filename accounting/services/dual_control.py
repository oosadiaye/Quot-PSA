"""Dual Control Service

Provides dual control and segregation of duties for large transactions:
- Configurable thresholds for dual approval
- Role-based dual control requirements
- Override with justification
"""
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from django.contrib.auth.models import User
from accounting.models import DualControlSetting, DualControlOverride


@dataclass
class DualControlCheckResult:
    """Result of dual control check."""
    requires_dual_approval: bool
    threshold_amount: Optional[Decimal]
    current_amount: Decimal
    first_approver: Optional[str]
    second_approver: Optional[str]
    is_fully_approved: bool
    pending_approvals: List[str]
    messages: List[str]


@dataclass
class DualControlActionResult:
    """Result of dual control action."""
    success: bool
    action: str
    new_status: str
    message: str
    is_complete: bool


class DualControlService:
    """Service for managing dual control requirements."""

    DEFAULT_THRESHOLDS = {
        'journal': Decimal('50000'),
        'invoice': Decimal('100000'),
        'payment': Decimal('50000'),
        'refund': Decimal('25000'),
    }

    DEFAULT_APPROVER_ROLES = ['Supervisor', 'Director', 'Manager']

    @classmethod
    def check_dual_control_required(
        cls,
        document_type: str,
        amount: Decimal,
        user: User
    ) -> DualControlCheckResult:
        """
        Check if dual approval is required for a transaction.

        Args:
            document_type: Type of document
            amount: Transaction amount
            user: User initiating the transaction

        Returns:
            DualControlCheckResult with requirements
        """
        messages = []

        setting = cls.get_setting(document_type)

        if not setting or not setting.is_active:
            threshold = cls.DEFAULT_THRESHOLDS.get(document_type, Decimal('50000'))
            if amount >= threshold:
                messages.append(f"Amount {amount} exceeds threshold {threshold}")
            else:
                return DualControlCheckResult(
                    requires_dual_approval=False,
                    threshold_amount=threshold,
                    current_amount=amount,
                    first_approver=None,
                    second_approver=None,
                    is_fully_approved=True,
                    pending_approvals=[],
                    messages=["Amount below threshold, no dual approval required"],
                )
        else:
            threshold = setting.threshold_amount
            if not setting.require_dual_approval or amount < threshold:
                return DualControlCheckResult(
                    requires_dual_approval=False,
                    threshold_amount=threshold,
                    current_amount=amount,
                    first_approver=None,
                    second_approver=None,
                    is_fully_approved=True,
                    pending_approvals=[],
                    messages=["Dual approval not required for this transaction"],
                )

        # S1-09 — handle None/missing threshold gracefully. Previously:
        #   setting.dual_approval_threshold (nullable) → None → TypeError
        #   on `amount >= None`.
        # Default to a conservative NGN 100,000 so any missing config still
        # enforces dual control on meaningful amounts rather than silently
        # disabling it.
        raw_threshold = getattr(setting, 'dual_approval_threshold', None) if setting else None
        dual_threshold = raw_threshold if raw_threshold is not None else Decimal('100000')
        requires_dual = (amount or Decimal('0')) >= dual_threshold

        messages.append(
            f"Dual approval {'required' if requires_dual else 'not required'} "
            f"for {document_type} of {amount} (threshold: {dual_threshold})"
        )

        return DualControlCheckResult(
            requires_dual_approval=requires_dual,
            threshold_amount=dual_threshold,
            current_amount=amount,
            first_approver=user.username,
            second_approver=None,
            is_fully_approved=not requires_dual,
            pending_approvals=['Second Approver'] if requires_dual else [],
            messages=messages,
        )

    @classmethod
    def get_setting(cls, document_type: str) -> Optional[DualControlSetting]:
        """Get dual control setting for a document type."""
        try:
            return DualControlSetting.objects.get(
                document_type=document_type,
                is_active=True
            )
        except DualControlSetting.DoesNotExist:
            return None

    @classmethod
    def get_effective_threshold(
        cls,
        document_type: str
    ) -> Decimal:
        """Get the effective threshold for dual control."""
        setting = cls.get_setting(document_type)
        if setting and setting.is_active:
            return setting.threshold_amount
        return cls.DEFAULT_THRESHOLDS.get(document_type, Decimal('50000'))

    @classmethod
    def get_dual_control_status(
        cls,
        document_type: str,
        document_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get dual control status for a document."""
        overrides = DualControlOverride.objects.filter(
            document_type=document_type,
            document_id=document_id
        ).order_by('-requested_at').first()

        if not overrides:
            return None

        return {
            'requires_override': overrides.status == 'PENDING',
            'status': overrides.status,
            'requested_by': overrides.requested_by.username,
            'requested_at': overrides.requested_at.isoformat(),
            'justification': overrides.justification,
            'approved_by': overrides.approved_by.username if overrides.approved_by else None,
            'approved_at': overrides.approved_at.isoformat() if overrides.approved_at else None,
        }

    @classmethod
    def request_override(
        cls,
        document_type: str,
        document_id: int,
        user: User,
        justification: str,
        ip_address: str = ''
    ) -> DualControlOverride:
        """
        Request an override for dual control.

        Args:
            document_type: Type of document
            document_id: Document ID
            user: User requesting override
            justification: Reason for override
            ip_address: User's IP address

        Returns:
            DualControlOverride instance
        """
        override = DualControlOverride.objects.create(
            document_type=document_type,
            document_id=document_id,
            requested_by=user,
            justification=justification,
            ip_address=ip_address,
            status='PENDING',
        )

        cls._notify_override_request(override)

        return override

    @classmethod
    def approve_override(
        cls,
        override_id: int,
        approver: User
    ) -> DualControlActionResult:
        """
        Approve a dual control override.

        Args:
            override_id: Override ID
            approver: User approving the override

        Returns:
            DualControlActionResult
        """
        try:
            override = DualControlOverride.objects.get(id=override_id)
        except DualControlOverride.DoesNotExist:
            return DualControlActionResult(
                success=False,
                action='APPROVE',
                new_status='ERROR',
                message='Override request not found',
                is_complete=False,
            )

        if override.status != 'PENDING':
            return DualControlActionResult(
                success=False,
                action='APPROVE',
                new_status=override.status,
                message=f'Cannot approve: status is {override.status}',
                is_complete=False,
            )

        if override.requested_by.id == approver.id:
            return DualControlActionResult(
                success=False,
                action='APPROVE',
                new_status='PENDING',
                message='Cannot approve your own override request',
                is_complete=False,
            )

        override.approved_by = approver
        override.approved_at = timezone.now()
        override.status = 'APPROVED'
        override.save()

        cls._notify_override_approval(override)

        return DualControlActionResult(
            success=True,
            action='APPROVE',
            new_status='APPROVED',
            message=f'Override approved by {approver.username}',
            is_complete=True,
        )

    @classmethod
    def reject_override(
        cls,
        override_id: int,
        rejector: User,
        reason: str
    ) -> DualControlActionResult:
        """Reject a dual control override."""
        try:
            override = DualControlOverride.objects.get(id=override_id)
        except DualControlOverride.DoesNotExist:
            return DualControlActionResult(
                success=False,
                action='REJECT',
                new_status='ERROR',
                message='Override request not found',
                is_complete=False,
            )

        override.approved_by = rejector
        override.approved_at = timezone.now()
        override.status = 'REJECTED'
        override.justification = f"{override.justification}\n\nRejection reason: {reason}"
        override.save()

        cls._notify_override_rejection(override)

        return DualControlActionResult(
            success=True,
            action='REJECT',
            new_status='REJECTED',
            message=f'Override rejected: {reason}',
            is_complete=True,
        )

    @classmethod
    def can_proceed(
        cls,
        document_type: str,
        document_id: int,
        user: User,
        amount: Decimal = None,
    ) -> Tuple[bool, str]:
        """
        Check if a transaction can proceed.

        S1-09 — ``amount`` is now a required effective parameter. The old
        signature hard-coded ``Decimal('0')`` which always passed the
        threshold check, silently disabling dual control. Callers MUST
        pass the real transaction amount; we still default to ``None``
        for backward compatibility but raise if the resulting amount is
        falsy AND a threshold exists.
        """
        effective_amount = amount if amount is not None else Decimal('0')
        check_result = cls.check_dual_control_required(
            document_type,
            effective_amount,
            user
        )
        # Defensive: if caller passed no amount and the document type has
        # any dual-control setting, refuse to proceed rather than fall
        # through "not required" when we simply don't know the amount.
        if amount is None:
            setting = cls.get_setting(document_type)
            if setting and getattr(setting, 'dual_approval_threshold', None) is not None:
                return False, (
                    'Dual-control check could not determine the transaction '
                    'amount. Pass `amount=` explicitly from the caller.'
                )

        if not check_result.requires_dual_approval:
            return True, "No dual approval required"

        override_status = cls.get_dual_control_status(document_type, document_id)

        if override_status and override_status['status'] == 'APPROVED':
            return True, "Dual control override approved"

        if override_status and override_status['status'] == 'PENDING':
            return False, "Dual control override pending approval"

        return False, "Dual approval required but not obtained"

    @classmethod
    def _notify_override_request(cls, override: DualControlOverride):
        """Send notification for override request."""
        pass

    @classmethod
    def _notify_override_approval(cls, override: DualControlOverride):
        """Send notification for override approval."""
        pass

    @classmethod
    def _notify_override_rejection(cls, override: DualControlOverride):
        """Send notification for override rejection."""
        pass

    @classmethod
    def get_pending_overrides(
        cls,
        role: str = None
    ) -> List[DualControlOverride]:
        """Get all pending override requests."""
        queryset = DualControlOverride.objects.filter(status='PENDING')

        if role:
            pass

        return list(queryset.order_by('-requested_at'))

    @classmethod
    def configure_dual_control(
        cls,
        document_type: str,
        threshold_amount: Decimal,
        require_dual_approval: bool = True,
        dual_approval_threshold: Decimal = None,
        approver_roles: List[str] = None
    ) -> DualControlSetting:
        """
        Configure dual control for a document type.

        Args:
            document_type: Type of document
            threshold_amount: Basic threshold
            require_dual_approval: Whether dual approval is required
            dual_approval_threshold: Threshold for dual approval (higher amount)
            approver_roles: List of roles that can approve

        Returns:
            DualControlSetting instance
        """
        setting, created = DualControlSetting.objects.update_or_create(
            document_type=document_type,
            defaults={
                'threshold_amount': threshold_amount,
                'require_dual_approval': require_dual_approval,
                'dual_approval_threshold': dual_approval_threshold or threshold_amount * 2,
                'approver_roles': approver_roles or cls.DEFAULT_APPROVER_ROLES,
                'is_active': True,
            }
        )

        return setting


try:
    from django.utils import timezone
except ImportError:
    timezone = None
