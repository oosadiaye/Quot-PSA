"""
Sprint-1 regression tests: approval workflow maker-checker.

Covers S1-08:
  * Submitter cannot approve their own document (maker-checker)
  * Same user cannot clear the same level twice (idempotency)
  * Superusers bypass the maker-checker check (emergency override)
"""
from __future__ import annotations

import pytest


@pytest.mark.django_db(transaction=True)
class TestMakerCheckerEnforcement:

    def _make_instance(self, submitted_by, max_level: int = 2):
        """Create a bare ApprovalInstance in PENDING status."""
        from accounting.models import ApprovalInstance
        return ApprovalInstance.objects.create(
            document_type='JE',
            document_id=1,
            document_reference='TEST-001',
            status='PENDING',
            current_level=0,
            max_level=max_level,
            submitted_by=submitted_by,
            approvals=[],
        )

    def test_submitter_cannot_self_approve(self, maker_user):
        """Same user who submitted cannot call approve()."""
        from accounting.services.approval_workflow import ApprovalWorkflowService
        inst = self._make_instance(submitted_by=maker_user)

        result = ApprovalWorkflowService.approve(
            instance_id=inst.id, user=maker_user, comment='self-approve attempt',
        )
        assert result.success is False
        assert 'maker-checker' in result.message.lower()

    def test_checker_approves_makers_submission(self, maker_user, checker_user):
        """Different user from submitter CAN approve."""
        from accounting.services.approval_workflow import ApprovalWorkflowService
        inst = self._make_instance(submitted_by=maker_user, max_level=1)

        result = ApprovalWorkflowService.approve(
            instance_id=inst.id, user=checker_user, comment='approved',
        )
        assert result.success is True
        inst.refresh_from_db()
        assert inst.status == 'APPROVED'

    def test_same_user_cannot_approve_same_level_twice(
        self, maker_user, checker_user,
    ):
        """Idempotency: pressing approve twice at the same level fails the
        second time."""
        from accounting.services.approval_workflow import ApprovalWorkflowService
        inst = self._make_instance(submitted_by=maker_user, max_level=3)

        r1 = ApprovalWorkflowService.approve(
            instance_id=inst.id, user=checker_user, level=1,
        )
        assert r1.success is True

        r2 = ApprovalWorkflowService.approve(
            instance_id=inst.id, user=checker_user, level=1,
        )
        assert r2.success is False
        assert 'already approved' in r2.message.lower()

    def test_superuser_bypasses_maker_checker(self, maker_user, superuser):
        """Superuser can self-approve — emergency override path."""
        from accounting.services.approval_workflow import ApprovalWorkflowService
        inst = self._make_instance(submitted_by=superuser, max_level=1)

        result = ApprovalWorkflowService.approve(
            instance_id=inst.id, user=superuser, comment='emergency',
        )
        assert result.success is True
