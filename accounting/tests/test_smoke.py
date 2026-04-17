"""
Smoke test: verifies the test harness is wired correctly.

Runs without any database access so it passes even when the live dev DB
is locked (common on Windows when ``manage.py runserver`` is up).

If this test fails, the issue is pytest configuration or module imports,
NOT the business logic. Fix this first before investigating other failures.
"""


def test_settings_module_loads():
    """DJANGO_SETTINGS_MODULE points at quot_pse.settings and imports."""
    from django.conf import settings
    assert settings.configured is True
    # Sprint 3 settings field exists.
    from accounting.models import AccountingSettings
    assert AccountingSettings._meta.get_field('accumulated_fund_account_code') is not None


def test_sprint_1_guards_importable():
    """All Sprint-1 services import without errors."""
    from accounting.services.journal_sequence import JournalSequenceService
    # Sprint-1 sequence helper is year-scoped.
    assert JournalSequenceService._sequence_name(2026) == 'journal:2026'
    assert JournalSequenceService._sequence_name() == 'journal'


def test_sprint_2_ipsas_reports_importable():
    """All IPSAS report methods are registered on the service."""
    from accounting.services.ipsas_reports import IPSASReportService
    for name in (
        'statement_of_financial_position',
        'statement_of_financial_performance',
        'cash_flow_statement',
        'statement_of_changes_in_net_assets',
        'budget_vs_actual',
        'notes_to_financial_statements',
        'revenue_performance',
        'tsa_cash_position',
        'functional_classification_report',
        'programme_performance_report',
        'geographic_distribution_report',
    ):
        assert hasattr(IPSASReportService, name), (
            f'IPSASReportService missing method: {name}'
        )


def test_sprint_3_audit_helpers_importable():
    """Sprint-3 redaction helpers work without DB access."""
    from accounting.models.audit import _redact_sensitive, _is_sensitive_key

    assert _is_sensitive_key('password') is True
    assert _is_sensitive_key('api_key') is True
    assert _is_sensitive_key('customer_name') is False

    redacted = _redact_sensitive({
        'password': 'abc',
        'username': 'alice',
        'nested': {'api_key': 'xyz', 'safe': 'ok'},
    })
    assert redacted['password'] == '***REDACTED***'
    assert redacted['username'] == 'alice'
    assert redacted['nested']['api_key'] == '***REDACTED***'
    assert redacted['nested']['safe'] == 'ok'


def test_sprint_3_year_end_service_importable():
    from accounting.services.year_end_close import (
        YearEndCloseService, DEFAULT_ACCUMULATED_FUND_CODE,
    )
    assert DEFAULT_ACCUMULATED_FUND_CODE == '43100000'
    assert hasattr(YearEndCloseService, 'close_fiscal_year')
