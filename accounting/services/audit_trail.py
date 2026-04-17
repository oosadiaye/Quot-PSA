"""Audit Trail Service

Provides comprehensive audit logging for all financial transactions:
- Transaction event logging
- Checksum generation for data integrity
- Immutable audit records
- Query interface for audit reports
"""
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from django.contrib.auth.models import User
from accounting.models import TransactionAuditLog


@dataclass
class AuditEntry:
    """Data class for creating audit entries."""
    transaction_type: str
    transaction_id: int
    action: str
    user: Optional[User] = None
    old_values: Dict[str, Any] = None
    new_values: Dict[str, Any] = None
    ip_address: str = ''
    user_agent: str = ''
    description: str = ''
    reference_number: str = ''
    tenant_id: int = None


class AuditTrailService:
    """Service for managing audit trails."""

    DOCUMENT_TYPE_MAP = {
        'JournalHeader': 'JE',
        'JournalLine': 'JE',
        'VendorInvoice': 'VI',
        'Payment': 'PAY',
        'CustomerInvoice': 'CI',
        'Receipt': 'RCT',
        'Budget': 'BGT',
        'BudgetAmendment': 'BGT',
        'BudgetTransfer': 'BGT',
        'FixedAsset': 'AST',
        'BankReconciliation': 'BANK',
        'InterCompanyInvoice': 'IC',
        'InterCompanyTransaction': 'IC',
    }

    @classmethod
    def log(
        cls,
        transaction_type: str,
        transaction_id: int,
        action: str,
        user: Optional[User] = None,
        old_values: Dict[str, Any] = None,
        new_values: Dict[str, Any] = None,
        request=None,
        description: str = '',
        reference_number: str = ''
    ) -> TransactionAuditLog:
        """
        Create an audit log entry.

        Args:
            transaction_type: Type of document (e.g., 'JE', 'VI')
            transaction_id: ID of the document
            action: Action performed (e.g., 'CREATE', 'UPDATE', 'POST')
            user: User performing the action
            old_values: Previous values (for updates)
            new_values: New values
            request: HTTP request for IP/UA extraction
            description: Human-readable description
            reference_number: Document reference number

        Returns:
            Created TransactionAuditLog instance
        """
        ip_address = ''
        user_agent = ''

        if request:
            ip_address = cls.get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]

        tenant_id = None
        if request and hasattr(request, 'tenant'):
            tenant_id = getattr(request.tenant, 'id', None)

        username = ''
        if user:
            username = user.username

        audit_log = TransactionAuditLog.objects.create(
            transaction_type=transaction_type,
            transaction_id=transaction_id,
            action=action,
            user=user,
            username=username,
            old_values=old_values or {},
            new_values=new_values or {},
            ip_address=ip_address,
            user_agent=user_agent,
            description=description,
            reference_number=reference_number,
            tenant_id=tenant_id,
        )

        return audit_log

    @classmethod
    def log_journal_event(
        cls,
        journal: Any,
        action: str,
        user: Optional[User] = None,
        request=None,
        description: str = ''
    ) -> TransactionAuditLog:
        """
        Log a journal entry event.

        Args:
            journal: JournalHeader instance
            action: Action performed
            user: User performing the action
            request: HTTP request
            description: Event description

        Returns:
            Created audit log entry
        """
        old_values = {}
        new_values = {}

        if action == 'UPDATE':
            old_values = {
                'status': journal.status,
                'description': journal.description,
            }

        if action in ['CREATE', 'UPDATE', 'POST', 'APPROVE']:
            new_values = {
                'status': journal.status,
                'description': journal.description,
                'posting_date': str(journal.posting_date),
                'reference_number': journal.reference_number,
                'total_debit': str(journal.total_debit if hasattr(journal, 'total_debit') else 0),
                'total_credit': str(journal.total_credit if hasattr(journal, 'total_credit') else 0),
            }

        return cls.log(
            transaction_type='JE',
            transaction_id=journal.id,
            action=action,
            user=user,
            old_values=old_values,
            new_values=new_values,
            request=request,
            description=description or f"Journal {action.lower()}: {journal.reference_number}",
            reference_number=journal.reference_number,
        )

    @classmethod
    def log_invoice_event(
        cls,
        invoice: Any,
        action: str,
        user: Optional[User] = None,
        request=None,
        description: str = ''
    ) -> TransactionAuditLog:
        """
        Log an invoice event (AP or AR).

        Args:
            invoice: Invoice instance
            action: Action performed
            user: User performing the action
            request: HTTP request
            description: Event description

        Returns:
            Created audit log entry
        """
        doc_type = 'VI' if invoice.__class__.__name__ == 'VendorInvoice' else 'CI'

        return cls.log(
            transaction_type=doc_type,
            transaction_id=invoice.id,
            action=action,
            user=user,
            new_values={
                'invoice_number': invoice.invoice_number,
                'total_amount': str(invoice.total_amount),
                'status': invoice.status,
            },
            request=request,
            description=description or f"Invoice {action.lower()}: {invoice.invoice_number}",
            reference_number=invoice.invoice_number,
        )

    @classmethod
    def log_payment_event(
        cls,
        payment: Any,
        action: str,
        user: Optional[User] = None,
        request=None,
        description: str = ''
    ) -> TransactionAuditLog:
        """Log a payment event."""
        return cls.log(
            transaction_type='PAY',
            transaction_id=payment.id,
            action=action,
            user=user,
            new_values={
                'payment_number': payment.payment_number,
                'amount': str(payment.total_amount),
                'status': payment.status,
            },
            request=request,
            description=description or f"Payment {action.lower()}: {payment.payment_number}",
            reference_number=payment.payment_number,
        )

    @classmethod
    def get_client_ip(cls, request) -> str:
        """Extract client IP from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')

    @classmethod
    def get_transaction_history(
        cls,
        transaction_type: str,
        transaction_id: int
    ) -> List[TransactionAuditLog]:
        """Get complete audit history for a transaction."""
        return list(TransactionAuditLog.objects.filter(
            transaction_type=transaction_type,
            transaction_id=transaction_id
        ).order_by('timestamp'))

    @classmethod
    def verify_integrity(
        cls,
        transaction_type: str,
        transaction_id: int
    ) -> Tuple[bool, List[str]]:
        """
        Verify the integrity of an audit trail.

        Args:
            transaction_type: Type of document
            transaction_id: ID of the document

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        # ── S3-03 — verify_integrity is READ-ONLY ────────────────────
        # Previous implementation rewrote ``previous_checksum`` on every
        # row during "verification", silently healing a tampered chain.
        # Verification must NEVER mutate. We now recompute each row's
        # checksum and compare to the stored hash; every row whose
        # stored hash doesn't match the recomputed value or whose
        # stored ``previous_checksum`` doesn't match the prior row's
        # stored ``checksum`` is reported as a chain break.
        logs = cls.get_transaction_history(transaction_type, transaction_id)
        # Preserve oldest-first order for chain verification (the
        # history helper returns newest-first by default).
        logs = sorted(logs, key=lambda l: (
            l.sequence_number if getattr(l, 'sequence_number', None) is not None else 0,
            l.timestamp,
        ))
        issues: list[str] = []

        if not logs:
            issues.append("No audit trail found")
            return False, issues

        prior_checksum = ''
        for log in logs:
            # 1. Row-level self-check: recompute the hash over stored
            #    values and compare to the stored checksum.
            if log.checksum:
                try:
                    recomputed = log.generate_checksum()
                except Exception as exc:
                    issues.append(
                        f"Row {getattr(log, 'sequence_number', log.pk)}: "
                        f"checksum recomputation failed ({exc})"
                    )
                    prior_checksum = log.checksum
                    continue
                if recomputed != log.checksum:
                    issues.append(
                        f"Row {getattr(log, 'sequence_number', log.pk)} "
                        f"({log.timestamp}): stored checksum does not "
                        f"match recomputed value — row has been tampered."
                    )

                # 2. Chain-level check: the stored previous_checksum
                #    must match the immediately-prior row's stored
                #    checksum.
                expected_prev = prior_checksum
                if (log.previous_checksum or '') != expected_prev:
                    issues.append(
                        f"Chain break at row "
                        f"{getattr(log, 'sequence_number', log.pk)} "
                        f"({log.timestamp}): previous_checksum does not "
                        f"match the prior row."
                    )
                prior_checksum = log.checksum
            else:
                issues.append(
                    f"Row {getattr(log, 'sequence_number', log.pk)} "
                    f"({log.timestamp}): missing checksum."
                )

        return len(issues) == 0, issues

    @classmethod
    def generate_audit_report(
        cls,
        start_date: datetime,
        end_date: datetime,
        transaction_types: List[str] = None,
        user_id: int = None,
        actions: List[str] = None
    ) -> List[TransactionAuditLog]:
        """
        Generate an audit report for a date range.

        Args:
            start_date: Start of report period
            end_date: End of report period
            transaction_types: Filter by transaction types
            user_id: Filter by user
            actions: Filter by actions

        Returns:
            List of audit log entries
        """
        queryset = TransactionAuditLog.objects.filter(
            timestamp__gte=start_date,
            timestamp__lte=end_date
        )

        if transaction_types:
            queryset = queryset.filter(transaction_type__in=transaction_types)

        if user_id:
            queryset = queryset.filter(user_id=user_id)

        if actions:
            queryset = queryset.filter(action__in=actions)

        return list(queryset.order_by('timestamp'))

    @classmethod
    def export_audit_trail(
        cls,
        transaction_type: str,
        transaction_id: int
    ) -> Dict[str, Any]:
        """
        Export complete audit trail for a transaction.

        Args:
            transaction_type: Type of document
            transaction_id: ID of the document

        Returns:
            Dictionary with complete audit trail
        """
        logs = cls.get_transaction_history(transaction_type, transaction_id)

        return {
            'transaction_type': transaction_type,
            'transaction_id': transaction_id,
            'entry_count': len(logs),
            'entries': [
                {
                    'timestamp': log.timestamp.isoformat(),
                    'action': log.action,
                    'user': log.username,
                    'ip_address': log.ip_address,
                    'old_values': log.old_values,
                    'new_values': log.new_values,
                    'description': log.description,
                    'reference_number': log.reference_number,
                    'checksum': log.checksum,
                }
                for log in logs
            ],
            'integrity_verified': cls.verify_integrity(transaction_type, transaction_id)[0],
        }


class AuditTrailMixin:
    """Mixin to add audit logging to ViewSets."""

    def get_audit_user(self):
        """Get the current user for audit logging."""
        if hasattr(self, 'request') and self.request and hasattr(self.request, 'user'):
            return self.request.user
        return None

    def get_audit_request(self):
        """Get the request for audit logging."""
        return getattr(self, 'request', None)

    def perform_create(self, serializer):
        """Log creation events."""
        instance = serializer.save()
        AuditTrailService.log(
            transaction_type=self.audit_document_type,
            transaction_id=instance.id,
            action='CREATE',
            user=self.get_audit_user(),
            request=self.get_audit_request(),
            new_values=serializer.data,
        )

    def perform_update(self, serializer):
        """Log update events."""
        old_instance = self.get_object()
        old_values = {
            field: getattr(old_instance, field)
            for field in serializer.Meta.fields
            if hasattr(old_instance, field)
        }

        instance = serializer.save()

        AuditTrailService.log(
            transaction_type=self.audit_document_type,
            transaction_id=instance.id,
            action='UPDATE',
            user=self.get_audit_user(),
            request=self.get_audit_request(),
            old_values=old_values,
            new_values=serializer.data,
        )

    def perform_destroy(self, instance):
        """Log deletion events.

        S3-02 — physical delete is refused for financial/posting records.
        IPSAS requires that posted transactions never be removed —
        corrections happen via reversal journals. This mixin enforces
        that by refusing ``DELETE`` on a whitelist of critical document
        types; callers must use void/reverse endpoints instead.

        Non-whitelisted document types (e.g. draft artefacts) still
        delete but always leave an audit trail first.
        """
        # Whitelist of document types that MUST NOT be physically deleted.
        _NO_PHYSICAL_DELETE = {
            'JOURNAL', 'JOURNAL_HEADER', 'JOURNAL_LINE',
            'VENDOR_INVOICE', 'CUSTOMER_INVOICE',
            'PAYMENT', 'RECEIPT',
            'PAYMENT_VOUCHER', 'PAYMENT_INSTRUCTION',
            'REVENUE_COLLECTION',
            'APPROPRIATION', 'WARRANT',
            'FIXED_ASSET', 'GL_BALANCE',
        }
        doc_type = (self.audit_document_type or '').upper()
        if doc_type in _NO_PHYSICAL_DELETE:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({
                'detail': (
                    f'Posted {doc_type} records cannot be physically '
                    f'deleted. Use the reverse/void endpoint instead '
                    f'to preserve the audit trail.'
                ),
            })

        AuditTrailService.log(
            transaction_type=self.audit_document_type,
            transaction_id=instance.id,
            action='DELETE',
            user=self.get_audit_user(),
            request=self.get_audit_request(),
            old_values={
                field: getattr(instance, field)
                for field in instance.__class__._meta.fields
            },
        )
        instance.delete()
