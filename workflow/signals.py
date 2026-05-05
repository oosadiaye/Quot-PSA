import logging
from django.db.models.signals import post_save
from django.dispatch import Signal, receiver

logger = logging.getLogger('dtsg')


# Custom signal for cross-module workflow side-effects.
#
# Emitted by ``ApprovalViewSet._trigger_document_action`` immediately
# after a document has been transitioned to its terminal status as a
# result of an Approval reaching ``Approved`` (or ``Rejected``).
#
# Receivers run synchronously inside the same ``transaction.atomic()``
# block as the approval transition — so a receiver that raises will
# roll back BOTH the approval status change and any DB writes the
# receiver itself made. That's the property the previous direct
# ``from procurement.views import InvoiceMatchingViewSet`` import was
# relying on; the signal preserves it without the cross-module
# coupling.
#
# Receiver kwargs:
#   sender:     workflow.Approval
#   approval:   the Approval instance
#   model_name: lowercase ContentType model name (e.g. 'invoicematching')
#   document:   the resolved content_object
#   action:     'approve' or 'reject'
document_approval_completed = Signal()


@receiver(post_save, sender='workflow.Approval')
def sync_document_status_on_approval(sender, instance, **kwargs):
    """
    When an Approval reaches a terminal state (Approved/Rejected),
    update the linked document's status accordingly.
    """
    if instance.status not in ('Approved', 'Rejected'):
        return

    doc = instance.content_object
    if doc is None:
        return

    # Only update if the document has a 'status' field
    if not hasattr(doc, 'status'):
        return

    new_status = instance.status  # 'Approved' or 'Rejected'

    # Map approval status to document-specific statuses
    STATUS_MAP = {
        'Approved': 'Approved',
        'Rejected': 'Rejected',
    }

    target_status = STATUS_MAP.get(new_status)
    if not target_status:
        return

    # Check that the target status is valid for the document
    current = doc.status
    if current == target_status:
        return

    # For models with ALLOWED_TRANSITIONS, validate the transition
    allowed = getattr(doc, 'ALLOWED_TRANSITIONS', {})
    if allowed:
        valid_next = allowed.get(current, [])
        if target_status not in valid_next:
            logger.warning(
                f"Approval {instance.id} completed with status '{new_status}', "
                f"but document {doc.__class__.__name__} cannot transition "
                f"from '{current}' to '{target_status}'. Skipping auto-update."
            )
            return

    doc.status = target_status
    doc.save(update_fields=['status', 'updated_at'] if hasattr(doc, 'updated_at') else ['status'])
    logger.info(
        f"Document {doc.__class__.__name__} #{doc.pk} status updated to "
        f"'{target_status}' via Approval #{instance.id}"
    )
