"""Tests for accounting/signals/workflow_dispatch.py.

All tests run without a real database — the receiver logic is isolated
via MagicMock and unittest.mock.patch. Pattern mirrors test_s6_mfa.py.

Because the receiver uses lazy ``from X import Y`` inside the function
body (to avoid circular imports at app startup), we patch at the SOURCE
module path rather than the local name in the receiver module.

Coverage:
  * JournalHeader auto-post fires when signal arrives with the right model_name
  * Auto-post is skipped when header is already 'Posted' (idempotency)
  * Signal for a different model_name is ignored (tight scoping)
  * Reject action is ignored
  * Service failure is logged as WARNING and NOT re-raised
  * None document is silently skipped

  * RevenueCollection auto-post fires on approve
  * RevenueCollection is skipped when already POSTED
  * RevenueCollection is skipped when is_reconciled=True
  * RevenueCollection wrong model_name ignored
  * RevenueCollection failure logged not raised

  * PaymentVoucherGov auto-post fires on approve
  * PaymentVoucherGov skipped when status is terminal (PAID / REVERSED)
  * PaymentVoucher (legacy) skipped when journal_id already set
  * PaymentVouchergov model_name triggers the same receiver
  * Wrong model_name for PV receiver ignored
  * PaymentVoucher failure logged not raised

  * BadDebtWriteOff GL posting fires on approve
  * BadDebtWriteOff skipped when status is already POSTED (idempotency)
  * BadDebtWriteOff skipped when journal_id already set (idempotency)
  * BadDebtWriteOff wrong model_name ignored
  * BadDebtWriteOff failure re-raises (approval rolls back)

  * VendorAdvance disbursement fires on approve
  * VendorAdvance skipped when disbursement_journal_id already set (idempotency)
  * VendorAdvance skipped when status is CLEARED (idempotency)
  * VendorAdvance wrong model_name ignored
  * VendorAdvance failure re-raises (approval rolls back)

  * TSAReconciliation completion fires on approve
  * TSAReconciliation skipped when status is already COMPLETED (idempotency)
  * TSAReconciliation wrong model_name ignored
  * TSAReconciliation failure re-raises (approval rolls back)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fire_signal(model_name, document, action='approve'):
    """Call the journalheader receiver function directly — DB-free."""
    from accounting.signals.workflow_dispatch import auto_post_journalheader_on_approval

    auto_post_journalheader_on_approval(
        sender=MagicMock(),
        approval=MagicMock(pk=1),
        model_name=model_name,
        document=document,
        action=action,
    )


def _fire_revenuecollection(model_name, document, action='approve'):
    """Call the revenuecollection receiver directly — DB-free."""
    from accounting.signals.workflow_dispatch import (
        auto_post_revenuecollection_on_approval,
    )

    auto_post_revenuecollection_on_approval(
        sender=MagicMock(),
        approval=MagicMock(pk=2),
        model_name=model_name,
        document=document,
        action=action,
    )


def _fire_paymentvoucher(model_name, document, action='approve'):
    """Call the paymentvoucher receiver directly — DB-free."""
    from accounting.signals.workflow_dispatch import (
        auto_post_paymentvoucher_on_approval,
    )

    auto_post_paymentvoucher_on_approval(
        sender=MagicMock(),
        approval=MagicMock(pk=3),
        model_name=model_name,
        document=document,
        action=action,
    )


# ---------------------------------------------------------------------------
# JournalHeader receiver tests
# ---------------------------------------------------------------------------

class TestJournalHeaderAutoPost:

    def test_journalheader_auto_post_fires_on_approve(self):
        """Signal with model_name='journalheader' and action='approve' calls
        IPSASJournalService.post_journal once with the header document."""
        header = MagicMock()
        header.status = 'Approved'
        header.pk = 42

        with patch(
            'accounting.services.ipsas_journal_service.IPSASJournalService.post_journal',
        ) as mock_post:
            _fire_signal('journalheader', header)

        mock_post.assert_called_once_with(header, user=None)

    def test_journalheader_skipped_when_already_posted(self):
        """Header whose status is already 'Posted' is silently skipped —
        idempotency guard prevents double-posting."""
        header = MagicMock()
        header.status = 'Posted'
        header.pk = 99

        with patch(
            'accounting.services.ipsas_journal_service.IPSASJournalService.post_journal',
        ) as mock_post:
            _fire_signal('journalheader', header)

        mock_post.assert_not_called()

    def test_journalheader_other_model_name_ignored(self):
        """Signal for a different document type must not invoke the service."""
        document = MagicMock()
        document.status = 'Approved'

        with patch(
            'accounting.services.ipsas_journal_service.IPSASJournalService.post_journal',
        ) as mock_post:
            _fire_signal('vendorinvoice', document)

        mock_post.assert_not_called()

    def test_journalheader_other_action_ignored(self):
        """Reject actions must not trigger auto-post."""
        header = MagicMock()
        header.status = 'Rejected'
        header.pk = 7

        with patch(
            'accounting.services.ipsas_journal_service.IPSASJournalService.post_journal',
        ) as mock_post:
            _fire_signal('journalheader', header, action='reject')

        mock_post.assert_not_called()

    def test_journalheader_failure_logged_not_raised(self):
        """When IPSASJournalService.post_journal raises, the receiver logs a
        WARNING but does NOT re-raise, preserving the approval commit."""
        header = MagicMock()
        header.status = 'Approved'
        header.pk = 55

        boom = ValueError('GL period closed')

        with patch(
            'accounting.services.ipsas_journal_service.IPSASJournalService.post_journal',
            side_effect=boom,
        ), patch(
            'accounting.signals.workflow_dispatch.logger',
        ) as mock_logger, patch(
            'accounting.models.gl.JournalHeader',
        ):
            # Must NOT raise
            _fire_signal('journalheader', header)

        # Warning was logged
        assert mock_logger.warning.called
        log_call_args = mock_logger.warning.call_args[0]
        assert 'JournalHeader' in log_call_args[0]

    def test_journalheader_none_document_ignored(self):
        """None document should be silently skipped."""
        with patch(
            'accounting.services.ipsas_journal_service.IPSASJournalService.post_journal',
        ) as mock_post:
            _fire_signal('journalheader', document=None)

        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# RevenueCollection receiver tests
# ---------------------------------------------------------------------------

class TestRevenueCollectionAutoPost:
    """Tests for auto_post_revenuecollection_on_approval."""

    _PATCH_SERVICE = (
        'accounting.services.revenue_collection_posting'
        '.post_revenue_collection_to_gl'
    )

    def _make_collection(self, status='CONFIRMED', is_reconciled=False):
        doc = MagicMock()
        doc.pk = 101
        doc.status = status
        doc.is_reconciled = is_reconciled
        # No gl_post_error field on the real model yet — hasattr returns False.
        del doc.gl_post_error
        return doc

    def test_revenuecollection_fires_on_approve(self):
        """Service is called with the document when signal fires correctly."""
        doc = self._make_collection()
        mock_journal = MagicMock(pk=99)

        with patch(self._PATCH_SERVICE, return_value=mock_journal) as mock_svc, \
             patch('accounting.models.revenue.RevenueCollection') as mock_model:
            _fire_revenuecollection('revenuecollection', doc)

        mock_svc.assert_called_once_with(doc, user=None)
        # Status + journal stamped via update()
        mock_model.objects.filter.assert_called_once_with(pk=101)
        mock_model.objects.filter.return_value.update.assert_called_once_with(
            status='POSTED',
            journal=mock_journal,
        )

    def test_revenuecollection_skipped_when_already_posted(self):
        """Collection with status='POSTED' is silently skipped."""
        doc = self._make_collection(status='POSTED')

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_revenuecollection('revenuecollection', doc)

        mock_svc.assert_not_called()

    def test_revenuecollection_skipped_when_is_reconciled(self):
        """Collection with is_reconciled=True is silently skipped."""
        doc = self._make_collection(is_reconciled=True)

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_revenuecollection('revenuecollection', doc)

        mock_svc.assert_not_called()

    def test_revenuecollection_other_model_name_ignored(self):
        """Signal for a different model_name must not invoke the service."""
        doc = self._make_collection()

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_revenuecollection('paymentvoucher', doc)

        mock_svc.assert_not_called()

    def test_revenuecollection_failure_logged_not_raised(self):
        """Service raises → handler logs WARNING, does NOT re-raise."""
        doc = self._make_collection()

        with patch(
            self._PATCH_SERVICE,
            side_effect=RuntimeError('DB deadlock'),
        ), patch(
            'accounting.signals.workflow_dispatch.logger',
        ) as mock_logger:
            # Must NOT raise
            _fire_revenuecollection('revenuecollection', doc)

        assert mock_logger.warning.called
        log_msg = mock_logger.warning.call_args[0][0]
        assert 'RevenueCollection' in log_msg

    def test_revenuecollection_none_document_ignored(self):
        """None document is silently skipped."""
        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_revenuecollection('revenuecollection', document=None)

        mock_svc.assert_not_called()

    def test_revenuecollection_reject_action_ignored(self):
        """Reject action must not trigger the service."""
        doc = self._make_collection()

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_revenuecollection('revenuecollection', doc, action='reject')

        mock_svc.assert_not_called()


# ---------------------------------------------------------------------------
# PaymentVoucher / PaymentVoucherGov receiver tests
# ---------------------------------------------------------------------------

class TestPaymentVoucherAutoPost:
    """Tests for auto_post_paymentvoucher_on_approval."""

    _PATCH_SERVICE = (
        'accounting.services.payment_voucher_posting'
        '.post_payment_voucher_to_gl'
    )

    def _make_pv_gov(self, status='APPROVED'):
        """Simulate a PaymentVoucherGov — no journal_id field."""
        doc = MagicMock(spec=[
            'pk', 'status', 'voucher_number', 'payee_name',
            'gross_amount', 'wht_amount', 'narration', 'ncoa_code',
            'tsa_account', 'deductions',
        ])
        doc.pk = 200
        doc.status = status
        return doc

    def _make_pv_legacy(self, journal_id=None, status='APPROVED'):
        """Simulate a legacy PaymentVoucher — has journal_id field."""
        doc = MagicMock()
        doc.pk = 300
        doc.status = status
        doc.journal_id = journal_id
        return doc

    def test_paymentvouchergov_fires_on_approve(self):
        """Service called for paymentvouchergov + action='approve'."""
        doc = self._make_pv_gov()
        mock_journal = MagicMock(pk=77)

        with patch(self._PATCH_SERVICE, return_value=mock_journal) as mock_svc, \
             patch('accounting.models.treasury.PaymentVoucherGov') as mock_model:
            _fire_paymentvoucher('paymentvouchergov', doc)

        mock_svc.assert_called_once_with(doc, user=None)
        mock_model.objects.filter.assert_called_once_with(pk=200)
        mock_model.objects.filter.return_value.update.assert_called_once_with(
            journal=mock_journal,
        )

    def test_paymentvoucher_variant_fires_on_approve(self):
        """Service is also called for model_name='paymentvoucher' (legacy)."""
        doc = self._make_pv_legacy(journal_id=None)
        mock_journal = MagicMock(pk=78)

        with patch(self._PATCH_SERVICE, return_value=mock_journal) as mock_svc:
            _fire_paymentvoucher('paymentvoucher', doc)

        mock_svc.assert_called_once_with(doc, user=None)

    def test_paymentvouchergov_skipped_when_status_paid(self):
        """PV with status='PAID' is silently skipped."""
        doc = self._make_pv_gov(status='PAID')

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_paymentvoucher('paymentvouchergov', doc)

        mock_svc.assert_not_called()

    def test_paymentvouchergov_skipped_when_status_reversed(self):
        """PV with status='REVERSED' is silently skipped."""
        doc = self._make_pv_gov(status='REVERSED')

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_paymentvoucher('paymentvouchergov', doc)

        mock_svc.assert_not_called()

    def test_paymentvoucher_legacy_skipped_when_journal_id_set(self):
        """Legacy PaymentVoucher with an existing journal_id is skipped."""
        doc = self._make_pv_legacy(journal_id=42)

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_paymentvoucher('paymentvoucher', doc)

        mock_svc.assert_not_called()

    def test_paymentvoucher_other_model_name_ignored(self):
        """Signal for a different model_name must not invoke the service."""
        doc = self._make_pv_gov()

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_paymentvoucher('revenuecollection', doc)

        mock_svc.assert_not_called()

    def test_paymentvoucher_failure_logged_not_raised(self):
        """Service raises → handler logs WARNING, does NOT re-raise."""
        doc = self._make_pv_gov()

        with patch(
            self._PATCH_SERVICE,
            side_effect=ValueError('NCoA bridge not seeded'),
        ), patch(
            'accounting.signals.workflow_dispatch.logger',
        ) as mock_logger:
            # Must NOT raise
            _fire_paymentvoucher('paymentvouchergov', doc)

        assert mock_logger.warning.called
        log_msg = mock_logger.warning.call_args[0][0]
        assert 'PaymentVoucher' in log_msg

    def test_paymentvoucher_reject_action_ignored(self):
        """Reject action must not trigger the service."""
        doc = self._make_pv_gov()

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_paymentvoucher('paymentvouchergov', doc, action='reject')

        mock_svc.assert_not_called()

    def test_paymentvoucher_none_document_ignored(self):
        """None document is silently skipped."""
        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_paymentvoucher('paymentvouchergov', document=None)

        mock_svc.assert_not_called()

    def test_paymentvouchergov_handles_paymentvouchergov_variant(self):
        """Both 'paymentvoucher' and 'paymentvouchergov' route through the
        same receiver and produce an identical service call."""
        mock_journal = MagicMock(pk=99)
        doc_gov = self._make_pv_gov()
        doc_legacy = self._make_pv_legacy(journal_id=None)

        calls = []
        with patch(self._PATCH_SERVICE, side_effect=lambda d, user: (calls.append(d), mock_journal)[1]):
            _fire_paymentvoucher('paymentvouchergov', doc_gov)
            _fire_paymentvoucher('paymentvoucher', doc_legacy)

        assert len(calls) == 2
        assert calls[0] is doc_gov
        assert calls[1] is doc_legacy


# ---------------------------------------------------------------------------
# BadDebtWriteOff receiver tests
# ---------------------------------------------------------------------------

def _fire_baddebtwriteoff(model_name, document, action='approve'):
    """Call the baddebtwriteoff receiver directly — DB-free."""
    from accounting.signals.workflow_dispatch import post_baddebtwriteoff_on_approval

    post_baddebtwriteoff_on_approval(
        sender=MagicMock(),
        approval=MagicMock(pk=10),
        model_name=model_name,
        document=document,
        action=action,
    )


class TestBadDebtWriteOffAutoPost:
    """Tests for post_baddebtwriteoff_on_approval."""

    _PATCH_SERVICE = (
        'accounting.services.bad_debt_writeoff_posting'
        '.post_bad_debt_writeoff'
    )

    def _make_writeoff(self, status='APPROVED', journal_id=None):
        doc = MagicMock()
        doc.pk = 500
        doc.status = status
        doc.journal_id = journal_id
        return doc

    def test_baddebtwriteoff_fires_on_approve(self):
        """Service called once with the document when signal fires correctly."""
        doc = self._make_writeoff()

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_baddebtwriteoff('baddebtwriteoff', doc)

        mock_svc.assert_called_once_with(doc, user=None)

    def test_baddebtwriteoff_skipped_when_already_posted(self):
        """Write-off with status='POSTED' is silently skipped (idempotency)."""
        doc = self._make_writeoff(status='POSTED')

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_baddebtwriteoff('baddebtwriteoff', doc)

        mock_svc.assert_not_called()

    def test_baddebtwriteoff_skipped_when_journal_id_set(self):
        """Write-off with journal_id already set is silently skipped (idempotency)."""
        doc = self._make_writeoff(journal_id=77)

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_baddebtwriteoff('baddebtwriteoff', doc)

        mock_svc.assert_not_called()

    def test_baddebtwriteoff_other_model_name_ignored(self):
        """Signal for a different model_name must not invoke the service."""
        doc = self._make_writeoff()

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_baddebtwriteoff('revenuecollection', doc)

        mock_svc.assert_not_called()

    def test_baddebtwriteoff_failure_reraises(self):
        """Service raises → receiver re-raises (approval rolls back)."""
        doc = self._make_writeoff()

        with patch(
            self._PATCH_SERVICE,
            side_effect=ValueError('GL period closed'),
        ), patch(
            'accounting.signals.workflow_dispatch.logger',
        ) as mock_logger, pytest.raises(ValueError, match='GL period closed'):
            _fire_baddebtwriteoff('baddebtwriteoff', doc)

        # Warning was logged before re-raise.
        assert mock_logger.warning.called
        log_msg = mock_logger.warning.call_args[0][0]
        assert 'BadDebtWriteOff' in log_msg

    def test_baddebtwriteoff_none_document_ignored(self):
        """None document is silently skipped."""
        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_baddebtwriteoff('baddebtwriteoff', document=None)

        mock_svc.assert_not_called()


# ---------------------------------------------------------------------------
# VendorAdvance receiver tests
# ---------------------------------------------------------------------------

def _fire_vendoradvance(model_name, document, action='approve'):
    """Call the vendoradvance receiver directly — DB-free."""
    from accounting.signals.workflow_dispatch import disburse_vendoradvance_on_approval

    disburse_vendoradvance_on_approval(
        sender=MagicMock(),
        approval=MagicMock(pk=11),
        model_name=model_name,
        document=document,
        action=action,
    )


class TestVendorAdvanceDisburse:
    """Tests for disburse_vendoradvance_on_approval."""

    _PATCH_SERVICE = (
        'accounting.services.vendor_advance'
        '.VendorAdvanceService.disburse'
    )

    def _make_advance(self, status='OUTSTANDING', disbursement_journal_id=None):
        doc = MagicMock()
        doc.pk = 600
        doc.status = status
        doc.disbursement_journal_id = disbursement_journal_id
        doc.vendor = MagicMock()
        doc.amount_paid = MagicMock()
        doc.source_type = 'MOBILIZATION'
        doc.source_id = 1
        doc.reference = 'DSG/MOB/2026/001'
        doc.posting_date = MagicMock()
        return doc

    def test_vendoradvance_fires_on_approve(self):
        """Service called once with document fields when signal fires correctly."""
        doc = self._make_advance()

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_vendoradvance('vendoradvance', doc)

        mock_svc.assert_called_once_with(
            vendor=doc.vendor,
            amount=doc.amount_paid,
            source_type=doc.source_type,
            source_id=doc.source_id,
            reference=doc.reference,
            posting_date=doc.posting_date,
            actor=None,
        )

    def test_vendoradvance_skipped_when_disbursement_journal_set(self):
        """VendorAdvance with disbursement_journal_id already set is skipped
        (idempotency — journal already posted via another path)."""
        doc = self._make_advance(disbursement_journal_id=42)

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_vendoradvance('vendoradvance', doc)

        mock_svc.assert_not_called()

    def test_vendoradvance_skipped_when_status_cleared(self):
        """VendorAdvance with status='CLEARED' is silently skipped (idempotency)."""
        doc = self._make_advance(status='CLEARED')

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_vendoradvance('vendoradvance', doc)

        mock_svc.assert_not_called()

    def test_vendoradvance_other_model_name_ignored(self):
        """Signal for a different model_name must not invoke the service."""
        doc = self._make_advance()

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_vendoradvance('paymentvoucher', doc)

        mock_svc.assert_not_called()

    def test_vendoradvance_failure_reraises(self):
        """Service raises → receiver re-raises (approval rolls back)."""
        doc = self._make_advance()

        with patch(
            self._PATCH_SERVICE,
            side_effect=RuntimeError('No vendor-advance GL configured'),
        ), patch(
            'accounting.signals.workflow_dispatch.logger',
        ) as mock_logger, pytest.raises(RuntimeError, match='No vendor-advance GL'):
            _fire_vendoradvance('vendoradvance', doc)

        assert mock_logger.warning.called
        log_msg = mock_logger.warning.call_args[0][0]
        assert 'VendorAdvance' in log_msg

    def test_vendoradvance_none_document_ignored(self):
        """None document is silently skipped."""
        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_vendoradvance('vendoradvance', document=None)

        mock_svc.assert_not_called()


# ---------------------------------------------------------------------------
# TSAReconciliation receiver tests
# ---------------------------------------------------------------------------

def _fire_tsareconciliation(model_name, document, action='approve'):
    """Call the tsareconciliation receiver directly — DB-free."""
    from accounting.signals.workflow_dispatch import (
        complete_tsareconciliation_on_approval,
    )

    complete_tsareconciliation_on_approval(
        sender=MagicMock(),
        approval=MagicMock(pk=12),
        model_name=model_name,
        document=document,
        action=action,
    )


class TestTSAReconciliationComplete:
    """Tests for complete_tsareconciliation_on_approval."""

    _PATCH_SERVICE = (
        'accounting.services.tsa_reconciliation_service'
        '.complete_reconciliation'
    )

    def _make_recon(self, status='REVIEWED'):
        doc = MagicMock()
        doc.pk = 700
        doc.status = status
        return doc

    def test_tsareconciliation_fires_on_approve(self):
        """Service called once with the document when signal fires correctly."""
        doc = self._make_recon()

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_tsareconciliation('tsareconciliation', doc)

        mock_svc.assert_called_once_with(doc, user=None)

    def test_tsareconciliation_skipped_when_already_completed(self):
        """Reconciliation with status='COMPLETED' is silently skipped (idempotency)."""
        doc = self._make_recon(status='COMPLETED')

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_tsareconciliation('tsareconciliation', doc)

        mock_svc.assert_not_called()

    def test_tsareconciliation_other_model_name_ignored(self):
        """Signal for a different model_name must not invoke the service."""
        doc = self._make_recon()

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_tsareconciliation('journalheader', doc)

        mock_svc.assert_not_called()

    def test_tsareconciliation_failure_reraises(self):
        """Service raises → receiver re-raises (approval rolls back)."""
        doc = self._make_recon()

        with patch(
            self._PATCH_SERVICE,
            side_effect=RuntimeError('DB deadlock on reconciliation'),
        ), patch(
            'accounting.signals.workflow_dispatch.logger',
        ) as mock_logger, pytest.raises(RuntimeError, match='DB deadlock'):
            _fire_tsareconciliation('tsareconciliation', doc)

        assert mock_logger.warning.called
        log_msg = mock_logger.warning.call_args[0][0]
        assert 'TSAReconciliation' in log_msg

    def test_tsareconciliation_none_document_ignored(self):
        """None document is silently skipped."""
        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_tsareconciliation('tsareconciliation', document=None)

        mock_svc.assert_not_called()

    def test_tsareconciliation_reject_action_ignored(self):
        """Reject action must not trigger the service."""
        doc = self._make_recon()

        with patch(self._PATCH_SERVICE) as mock_svc:
            _fire_tsareconciliation('tsareconciliation', doc, action='reject')

        mock_svc.assert_not_called()
