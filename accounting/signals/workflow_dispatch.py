"""Accounting workflow-dispatch signal receiver.

Listens for ``document_approval_completed`` signals emitted by the
workflow engine and triggers the appropriate accounting-domain
side-effect (e.g. auto-posting a JournalHeader to GL once its
approval workflow completes).

This module is imported by ``accounting/signals/__init__.py`` so it
loads at app startup via ``AccountingConfig.ready()``.

Failure policy (mirrors procurement/signals.py template):
- JournalHeader auto-post failure: log WARNING, do NOT roll back the
  approval. The approval commit is preserved and the error is stamped
  into ``JournalHeader.gl_post_error`` if that field exists; otherwise
  just logged. A subsequent "Post to GL" click can retry.

Idempotency:
- Skip if JournalHeader.status is already 'Posted'.
"""
import logging

from django.dispatch import receiver

logger = logging.getLogger(__name__)

try:
    from workflow.signals import document_approval_completed
except ImportError:  # pragma: no cover — workflow is always installed
    document_approval_completed = None


if document_approval_completed is not None:

    @receiver(
        document_approval_completed,
        dispatch_uid='accounting.journalheader_auto_post',
    )
    def auto_post_journalheader_on_approval(
        sender, approval, model_name, document, action, **kwargs,
    ):
        """Auto-post a JournalHeader to GL when its workflow approval completes.

        The user expectation for manual journal entries that go through
        an approval workflow is that the journal posts to GL the moment
        the approval clears — no separate "Post to GL" click required.

        Runs inside the workflow's ``transaction.atomic()`` block, but
        deliberately does NOT re-raise on failure so the approval commit
        is preserved. The failure is surfaced via a WARNING log (and an
        optional ``gl_post_error`` stamp) so the operator can retry via
        the "Post to GL" button.

        Idempotency: skips silently if the header is already 'Posted'.
        """
        if action != 'approve' or model_name != 'journalheader':
            return

        if document is None:
            return

        # Idempotency guard — already posted by some other path.
        if getattr(document, 'status', None) == 'Posted':
            return

        try:
            # Lazy imports — avoids circular import at module load time
            # (accounting.signals is imported by accounting.apps.ready(),
            # which fires before accounting.services is fully resolved in
            # some import orderings). Safe at signal-dispatch time.
            from accounting.services.ipsas_journal_service import IPSASJournalService

            IPSASJournalService.post_journal(document, user=None)

        except Exception as exc:
            # Log the failure but do NOT re-raise: the approval itself
            # should commit even if GL posting fails. The operator can
            # retry via the "Post to GL" endpoint.
            logger.warning(
                'Workflow-approved JournalHeader %s auto-post to GL failed '
                '(retry via Post to GL): %s',
                getattr(document, 'pk', '?'),
                exc,
            )
            err_msg = f'{type(exc).__name__}: {exc}'[:5000]
            # Stamp error field if it exists on the model, using update()
            # to avoid re-triggering save-time signals inside the atomic.
            try:
                from accounting.models.gl import JournalHeader
                if hasattr(JournalHeader, 'gl_post_error'):
                    JournalHeader.objects.filter(pk=document.pk).update(
                        gl_post_error=err_msg,
                    )
            except Exception:  # noqa: BLE001 — best-effort stamp
                logger.exception(
                    'Failed to stamp gl_post_error on JournalHeader %s',
                    getattr(document, 'pk', '?'),
                )
        else:
            # Clear any prior error stamp on success (best-effort).
            try:
                from accounting.models.gl import JournalHeader
                if hasattr(JournalHeader, 'gl_post_error'):
                    if getattr(document, 'gl_post_error', ''):
                        JournalHeader.objects.filter(pk=document.pk).update(
                            gl_post_error='',
                        )
            except Exception:  # noqa: BLE001 — best-effort clear
                pass
