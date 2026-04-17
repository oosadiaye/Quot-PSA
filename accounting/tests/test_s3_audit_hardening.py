"""
Sprint-3 regression tests: audit log hardening.

Covers:
  * S3-01 — Tamper-evident hash chain (user/IP/prev_checksum included)
  * S3-02 — Write-once (update / delete both blocked)
  * S3-03 — verify_integrity is READ-ONLY (recomputes + compares; never
            writes back)
  * S3-04 — Sensitive-field redaction before hashing

These tests are the forensic safety net. An attacker who tampers with a
single row must be detected on the next verify_integrity run — the old
implementation silently "healed" the chain.
"""
from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError


@pytest.mark.audit
@pytest.mark.django_db(transaction=True)
class TestAuditLogWriteOnce:
    """S3-02 — TransactionAuditLog rows are immutable after insert."""

    def _make_log(self, maker_user, **overrides):
        from accounting.models import TransactionAuditLog
        defaults = dict(
            transaction_type='journal',
            transaction_id=1,
            action='CREATE',
            user=maker_user,
            username=maker_user.username,
            old_values={},
            new_values={'foo': 'bar'},
        )
        defaults.update(overrides)
        return TransactionAuditLog.objects.create(**defaults)

    def test_update_rejected_after_insert(self, maker_user):
        """Second save() on an existing pk raises ValidationError."""
        log = self._make_log(maker_user)
        log.new_values = {'foo': 'tampered'}
        with pytest.raises(ValidationError):
            log.save()

    def test_delete_rejected(self, maker_user):
        """delete() on any audit row raises ValidationError."""
        log = self._make_log(maker_user)
        with pytest.raises(ValidationError):
            log.delete()

    def test_sequence_number_assigned_monotonically(self, maker_user):
        """Each new row gets the next integer sequence_number within its
        tenant bucket."""
        log1 = self._make_log(maker_user, new_values={'i': 1})
        log2 = self._make_log(maker_user, new_values={'i': 2})
        log3 = self._make_log(maker_user, new_values={'i': 3})
        seqs = [log1.sequence_number, log2.sequence_number, log3.sequence_number]
        # Monotonic, strictly increasing.
        assert seqs == sorted(seqs)
        assert seqs[1] == seqs[0] + 1
        assert seqs[2] == seqs[1] + 1


@pytest.mark.audit
@pytest.mark.django_db(transaction=True)
class TestAuditHashChain:
    """S3-01 — hash covers user/IP/prev; chain is linked."""

    def test_checksum_links_to_previous_row(self, maker_user):
        """Each row's previous_checksum == the prior row's checksum."""
        from accounting.models import TransactionAuditLog
        log1 = TransactionAuditLog.objects.create(
            transaction_type='journal', transaction_id=1, action='CREATE',
            user=maker_user, username=maker_user.username,
        )
        log2 = TransactionAuditLog.objects.create(
            transaction_type='journal', transaction_id=2, action='CREATE',
            user=maker_user, username=maker_user.username,
        )
        assert log2.previous_checksum == log1.checksum

    def test_checksum_includes_user_id(self, maker_user, checker_user):
        """Two otherwise-identical rows with different users produce
        different checksums — proves user_id is in the hash."""
        from accounting.models import TransactionAuditLog
        log1 = TransactionAuditLog.objects.create(
            transaction_type='journal', transaction_id=99, action='UPDATE',
            user=maker_user, username=maker_user.username,
            new_values={'x': 1},
        )
        log2 = TransactionAuditLog.objects.create(
            transaction_type='journal', transaction_id=99, action='UPDATE',
            user=checker_user, username=checker_user.username,
            new_values={'x': 1},
        )
        assert log1.checksum != log2.checksum

    def test_checksum_detects_tampered_values(self, maker_user):
        """If someone mutates new_values in-place and recomputes the
        checksum on a saved row, the recomputed hash no longer matches."""
        from accounting.models import TransactionAuditLog
        log = TransactionAuditLog.objects.create(
            transaction_type='journal', transaction_id=1, action='UPDATE',
            user=maker_user, username=maker_user.username,
            new_values={'amount': 100},
        )
        stored = log.checksum

        # Simulate a tamper (we can't save — S3-02 blocks that — but an
        # attacker with raw DB access could bypass Django).
        log.new_values = {'amount': 10_000_000}
        recomputed = log.generate_checksum()
        assert recomputed != stored


@pytest.mark.audit
@pytest.mark.django_db(transaction=True)
class TestAuditRedaction:
    """S3-04 — sensitive field names are redacted before persistence."""

    def test_password_redacted(self, maker_user):
        from accounting.models import TransactionAuditLog
        log = TransactionAuditLog.objects.create(
            transaction_type='user', transaction_id=1, action='UPDATE',
            user=maker_user, username=maker_user.username,
            new_values={'username': 'alice', 'password': 'hunter2'},
        )
        assert log.new_values['username'] == 'alice'
        assert log.new_values['password'] == '***REDACTED***'

    def test_nested_api_key_redacted(self, maker_user):
        """Redaction walks nested dicts."""
        from accounting.models import TransactionAuditLog
        log = TransactionAuditLog.objects.create(
            transaction_type='integration', transaction_id=2, action='CREATE',
            user=maker_user, username=maker_user.username,
            new_values={
                'name': 'Remita',
                'config': {'api_key': 'SECRET', 'endpoint': 'https://x'},
            },
        )
        assert log.new_values['config']['api_key'] == '***REDACTED***'
        assert log.new_values['config']['endpoint'] == 'https://x'


@pytest.mark.audit
@pytest.mark.django_db(transaction=True)
class TestVerifyIntegrityReadOnly:
    """S3-03 — verify_integrity must never write."""

    def test_verify_does_not_modify_rows(self, maker_user):
        """Row's previous_checksum stays exactly as persisted after verify."""
        from accounting.models import TransactionAuditLog
        from accounting.services.audit_trail import AuditTrailService

        TransactionAuditLog.objects.create(
            transaction_type='journal', transaction_id=77, action='CREATE',
            user=maker_user, username=maker_user.username,
        )
        TransactionAuditLog.objects.create(
            transaction_type='journal', transaction_id=77, action='UPDATE',
            user=maker_user, username=maker_user.username,
        )

        rows_before = list(
            TransactionAuditLog.objects
            .filter(transaction_type='journal', transaction_id=77)
            .values_list('pk', 'previous_checksum', 'checksum')
        )

        AuditTrailService.verify_integrity('journal', 77)

        rows_after = list(
            TransactionAuditLog.objects
            .filter(transaction_type='journal', transaction_id=77)
            .values_list('pk', 'previous_checksum', 'checksum')
        )
        assert rows_before == rows_after  # read-only!
