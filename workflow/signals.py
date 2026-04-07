import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger('dtsg')


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
