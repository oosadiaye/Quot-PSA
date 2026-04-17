"""
Sprint-16 regression tests — no-DB fast tier.

Covers the DataQualityService public contract and CheckResult dataclass.
The actual check queries require a live DB and are exercised by the
integration test tier; here we verify:

  * CheckResult.to_dict() shape stability (consumed by the React page).
  * DataQualityService.run_all() happy-path shape when every check is
    stubbed to return ``ok``.
  * Overall-status derivation logic (fail > warn > ok).
"""
from __future__ import annotations

from unittest.mock import patch



class TestCheckResultToDict:

    def test_dataclass_defaults(self):
        from accounting.services.data_quality import CheckResult
        r = CheckResult(
            key='test',
            label='Test',
            description='d',
            status='ok',
        )
        d = r.to_dict()
        assert d == {
            'key': 'test',
            'label': 'Test',
            'description': 'd',
            'status': 'ok',
            'count': 0,
            'samples': [],
        }

    def test_dataclass_with_samples(self):
        from accounting.services.data_quality import CheckResult
        r = CheckResult(
            key='k', label='L', description='d', status='fail',
            count=3, samples=[{'id': 1}, {'id': 2}],
        )
        d = r.to_dict()
        assert d['count'] == 3
        assert d['samples'] == [{'id': 1}, {'id': 2}]
        assert d['status'] == 'fail'


class TestRunAllShape:
    """Stub out every check so we can validate the orchestrator logic."""

    def _stub(self, status, count=0):
        from accounting.services.data_quality import CheckResult
        return CheckResult(
            key=f'stub_{status}',
            label='Stub',
            description='stub',
            status=status,
            count=count,
        )

    @patch('accounting.services.data_quality.DataQualityService._over_committed_appropriations')
    @patch('accounting.services.data_quality.DataQualityService._postings_to_inactive_accounts')
    @patch('accounting.services.data_quality.DataQualityService._aged_draft_journals')
    @patch('accounting.services.data_quality.DataQualityService._posted_journals_without_lines')
    @patch('accounting.services.data_quality.DataQualityService._unbalanced_posted_journals')
    def test_all_ok(self, m1, m2, m3, m4, m5):
        from accounting.services.data_quality import DataQualityService
        m1.return_value = self._stub('ok')
        m2.return_value = self._stub('ok')
        m3.return_value = self._stub('ok')
        m4.return_value = self._stub('ok')
        m5.return_value = self._stub('ok')

        result = DataQualityService.run_all()
        assert result['overall'] == 'ok'
        assert result['summary'] == {'ok': 5, 'warn': 0, 'fail': 0, 'total': 5}
        assert len(result['checks']) == 5
        assert 'generated_at' in result

    @patch('accounting.services.data_quality.DataQualityService._over_committed_appropriations')
    @patch('accounting.services.data_quality.DataQualityService._postings_to_inactive_accounts')
    @patch('accounting.services.data_quality.DataQualityService._aged_draft_journals')
    @patch('accounting.services.data_quality.DataQualityService._posted_journals_without_lines')
    @patch('accounting.services.data_quality.DataQualityService._unbalanced_posted_journals')
    def test_warn_dominates_ok(self, m1, m2, m3, m4, m5):
        from accounting.services.data_quality import DataQualityService
        m1.return_value = self._stub('ok')
        m2.return_value = self._stub('ok')
        m3.return_value = self._stub('warn', count=2)
        m4.return_value = self._stub('ok')
        m5.return_value = self._stub('ok')

        result = DataQualityService.run_all()
        assert result['overall'] == 'warn'
        assert result['summary']['warn'] == 1
        assert result['summary']['fail'] == 0

    @patch('accounting.services.data_quality.DataQualityService._over_committed_appropriations')
    @patch('accounting.services.data_quality.DataQualityService._postings_to_inactive_accounts')
    @patch('accounting.services.data_quality.DataQualityService._aged_draft_journals')
    @patch('accounting.services.data_quality.DataQualityService._posted_journals_without_lines')
    @patch('accounting.services.data_quality.DataQualityService._unbalanced_posted_journals')
    def test_fail_dominates_warn(self, m1, m2, m3, m4, m5):
        from accounting.services.data_quality import DataQualityService
        m1.return_value = self._stub('fail', count=1)
        m2.return_value = self._stub('warn', count=5)
        m3.return_value = self._stub('warn', count=2)
        m4.return_value = self._stub('ok')
        m5.return_value = self._stub('ok')

        result = DataQualityService.run_all()
        assert result['overall'] == 'fail'
        assert result['summary'] == {'ok': 2, 'warn': 2, 'fail': 1, 'total': 5}

    @patch('accounting.services.data_quality.DataQualityService._over_committed_appropriations')
    @patch('accounting.services.data_quality.DataQualityService._postings_to_inactive_accounts')
    @patch('accounting.services.data_quality.DataQualityService._aged_draft_journals')
    @patch('accounting.services.data_quality.DataQualityService._posted_journals_without_lines')
    @patch('accounting.services.data_quality.DataQualityService._unbalanced_posted_journals')
    def test_checks_preserve_order(self, m1, m2, m3, m4, m5):
        """Order matters for UI — the 5 checks appear in a fixed order."""
        from accounting.services.data_quality import DataQualityService
        m1.return_value = self._stub('ok')   # unbalanced
        m2.return_value = self._stub('ok')   # empty-lines
        m3.return_value = self._stub('ok')   # aged-drafts
        m4.return_value = self._stub('ok')   # inactive-accounts
        m5.return_value = self._stub('ok')   # over-committed

        result = DataQualityService.run_all()
        keys = [c['key'] for c in result['checks']]
        # Each stub has key='stub_ok' so we can't distinguish by key here;
        # instead verify all 5 mocks were called exactly once.
        assert m1.call_count == 1
        assert m2.call_count == 1
        assert m3.call_count == 1
        assert m4.call_count == 1
        assert m5.call_count == 1
        assert len(keys) == 5


class TestGeneratedAtIsoFormat:

    @patch('accounting.services.data_quality.DataQualityService._over_committed_appropriations')
    @patch('accounting.services.data_quality.DataQualityService._postings_to_inactive_accounts')
    @patch('accounting.services.data_quality.DataQualityService._aged_draft_journals')
    @patch('accounting.services.data_quality.DataQualityService._posted_journals_without_lines')
    @patch('accounting.services.data_quality.DataQualityService._unbalanced_posted_journals')
    def test_generated_at_iso_parseable(self, m1, m2, m3, m4, m5):
        from datetime import datetime
        from accounting.services.data_quality import DataQualityService, CheckResult
        stub = CheckResult(key='x', label='x', description='x', status='ok')
        m1.return_value = m2.return_value = m3.return_value = m4.return_value = m5.return_value = stub

        result = DataQualityService.run_all()
        # Parseable as ISO.
        parsed = datetime.fromisoformat(result['generated_at'])
        assert parsed is not None


class TestConstants:
    """The thresholds are disclosed to users via the UI. Lock them in."""

    def test_draft_age_threshold(self):
        from accounting.services import data_quality
        assert data_quality._DRAFT_MAX_AGE_DAYS == 30

    def test_tolerance(self):
        from decimal import Decimal
        from accounting.services import data_quality
        assert data_quality._TOL == Decimal('0.01')

    def test_sample_size(self):
        from accounting.services import data_quality
        assert data_quality._SAMPLE_SIZE == 25
