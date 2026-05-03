"""
Shared pytest fixtures for contracts/tests.

Two layers of fixtures live here:

1. **Stub fixtures (no DB)** — ``stub_contract``, ``stub_balance`` build
   ``types.SimpleNamespace`` imitations of Contract / ContractBalance so
   pure-logic tests can exercise the control layer without a tenant-schema
   round trip. Used by ``test_structural_controls.py``.

2. **DB-backed fixtures (tenant schema)** — create real rows under the
   ``pytest_schema`` tenant so integration / attack tests can hit the
   PostgreSQL trigger and the service layer's SELECT-FOR-UPDATE paths.
   Used by ``test_overpayment_integration.py`` and ``test_db_trigger.py``.

The tenant-schema plumbing is intentionally duplicated from
``accounting/tests/conftest.py`` (pytest does NOT share session-scoped
``django_db_setup`` fixtures across sibling conftests, only between
parent and child conftests). Keeping the schema setup here means the
contracts test suite can run standalone via
``pytest contracts/tests/``.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest


# ── Stub factories (no DB) ─────────────────────────────────────────────

@pytest.fixture
def stub_contract():
    """
    Factory → ``SimpleNamespace`` imitating a Contract model instance.

    Populates the exact attributes the service layer reads.  Good enough
    for pure-logic tests where we never call ``.save()``.
    """
    def _make(
        *,
        pk: int = 1,
        original_sum: Decimal = Decimal("10000000.00"),
        mobilization_rate: Decimal = Decimal("15.00"),
        retention_rate: Decimal = Decimal("5.00"),
        status: str = "ACTIVATED",
        fiscal_year_start: date = date(2026, 1, 1),
        fiscal_year_end: date = date(2026, 12, 31),
        contract_number: str = "DSG/WORKS/2026/001",
        created_by_id: int = 100,
    ):
        fy = SimpleNamespace(
            start_date=fiscal_year_start,
            end_date=fiscal_year_end,
        )
        return SimpleNamespace(
            pk=pk,
            id=pk,
            original_sum=original_sum,
            mobilization_rate=mobilization_rate,
            retention_rate=retention_rate,
            status=status,
            fiscal_year=fy,
            contract_number=contract_number,
            created_by_id=created_by_id,
        )

    return _make


@pytest.fixture
def stub_balance():
    """
    Factory → ``SimpleNamespace`` imitating a ContractBalance row.
    """
    def _make(
        *,
        contract_ceiling: Decimal = Decimal("10000000.00"),
        cumulative_gross_certified: Decimal = Decimal("0.00"),
        pending_voucher_amount: Decimal = Decimal("0.00"),
        cumulative_gross_paid: Decimal = Decimal("0.00"),
        mobilization_paid: Decimal = Decimal("0.00"),
        mobilization_recovered: Decimal = Decimal("0.00"),
        retention_held: Decimal = Decimal("0.00"),
        retention_released: Decimal = Decimal("0.00"),
        version: int = 1,
    ):
        return SimpleNamespace(
            contract_ceiling=contract_ceiling,
            cumulative_gross_certified=cumulative_gross_certified,
            pending_voucher_amount=pending_voucher_amount,
            cumulative_gross_paid=cumulative_gross_paid,
            mobilization_paid=mobilization_paid,
            mobilization_recovered=mobilization_recovered,
            retention_held=retention_held,
            retention_released=retention_released,
            version=version,
        )

    return _make


# ───────────────────────────────────────────────────────────────────────
#                 Tenant-schema plumbing (DB-backed tests)
# ───────────────────────────────────────────────────────────────────────
#
# Integration tests for the contracts module must touch a tenant schema
# because every contracts app table (contracts_contract,
# contracts_contractbalance, …) is in TENANT_APPS. Replicate the pattern
# from ``accounting/tests/conftest.py``:
#
#   • Session-scoped ``django_db_setup`` creates ``pytest_schema`` via a
#     Client.save() which runs migrate_schemas.
#   • Autouse ``_route_to_pytest_schema`` switches the DB connection to
#     that schema for any test that asks for the ``db`` fixture.

PYTEST_SCHEMA_NAME = "pytest_schema"


@pytest.fixture(scope="session")
def django_db_setup(request, django_db_setup, django_db_blocker):  # noqa: F811
    """Ensure tenant-app tables exist before any DB-touching test runs.

    The audit-log ``post_save`` signal (``core.models.log_model_changes``)
    fires during migration 0080's ``BudgetCheckRule`` data seed. The signal
    calls ``ContentType.objects.get_for_model``, which hits the tenant's
    ``django_content_type`` table — that table still carries the legacy
    NOT NULL ``name`` column because ``contenttypes.0002_remove_content_type_name``
    never runs inside the tenant schema under django-tenants. We disconnect
    the signal for the duration of tenant schema migration to side-step the
    issue, then reconnect so tests observe the real audit behaviour.
    """
    with django_db_blocker.unblock():
        from django.db import connection
        from django.db.models.signals import post_save
        from django_tenants.utils import schema_exists
        from core.models import log_model_changes
        from tenants.models import Client, Domain

        connection.set_schema_to_public()

        # Suspend the audit signal so migration data-seeds don't trip on
        # legacy tenant-schema ContentType columns (see docstring).
        post_save.disconnect(dispatch_uid="core_audit_log_model_changes")
        try:
            if not Client.objects.filter(schema_name=PYTEST_SCHEMA_NAME).exists():
                client = Client(
                    schema_name=PYTEST_SCHEMA_NAME,
                    name="PyTest Tenant",
                )
                client.save()

                Domain.objects.get_or_create(
                    domain="pytest.localhost",
                    tenant=client,
                    defaults={"is_primary": True},
                )

            if not schema_exists(PYTEST_SCHEMA_NAME):
                from django.core.management import call_command
                call_command(
                    "migrate_schemas",
                    schema_name=PYTEST_SCHEMA_NAME,
                    verbosity=0,
                )
        finally:
            post_save.connect(
                log_model_changes,
                dispatch_uid="core_audit_log_model_changes",
            )

        connection.set_schema_to_public()


@pytest.fixture(autouse=True)
def _route_to_pytest_schema(request):
    """Auto-switch to ``pytest_schema`` for DB-touching tests."""
    needs_db = any(
        name in request.fixturenames
        for name in ("db", "transactional_db", "django_db_reset_sequences")
    )
    if not needs_db:
        yield
        return

    from django.db import connection
    try:
        connection.set_schema(PYTEST_SCHEMA_NAME)
    except Exception:
        pass
    try:
        yield
    finally:
        try:
            connection.set_schema_to_public()
        except Exception:
            try:
                connection.schema_name = "public"
                connection.tenant = None
            except Exception:
                pass


# ── User fixtures (5 distinct users for SoD coverage) ─────────────────

@pytest.fixture
def _user_factory(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()

    def _make(username: str, **extra):
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={"email": f"{username}@test.local", **extra},
        )
        return user

    return _make


@pytest.fixture
def drafter(_user_factory):
    return _user_factory("drafter")


@pytest.fixture
def certifier(_user_factory):
    return _user_factory("certifier")


@pytest.fixture
def approver(_user_factory):
    """Approver needs permission to approve LOCAL variations."""
    from django.contrib.auth.models import Permission
    user = _user_factory("approver")
    # Grant every contracts-app permission — the SoD check runs before
    # the permission check in approve(), so we don't need fine-grained
    # granting for non-variation tests.
    perms = Permission.objects.filter(
        content_type__app_label="contracts",
    )
    user.user_permissions.add(*perms)
    return user


@pytest.fixture
def voucher_raiser(_user_factory):
    return _user_factory("voucher_raiser")


@pytest.fixture
def payer(_user_factory):
    return _user_factory("payer")


@pytest.fixture
def activator(_user_factory):
    """Separate user for contract activation (SoD from drafter)."""
    return _user_factory("activator")


# ── Minimal NCoA + FiscalYear + Vendor + Contract fixtures ────────────

@pytest.fixture
def fiscal_year(db):
    from accounting.models import FiscalYear
    fy, _ = FiscalYear.objects.get_or_create(
        year=2026,
        defaults={
            "name": "FY2026",
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 12, 31),
            "status": "Open",
            "is_active": True,
            "period_type": "Yearly",
        },
    )
    return fy


@pytest.fixture
def mda_segment(db):
    from accounting.models import AdministrativeSegment
    seg, _ = AdministrativeSegment.objects.get_or_create(
        code="050101000000",
        defaults={
            "name": "Ministry of Works",
            "level": "ORGANIZATION",
            "sector_code": "05",
            "organization_code": "01",
            "is_mda": True,
            "mda_type": "MINISTRY",
            "is_active": True,
        },
    )
    return seg


@pytest.fixture
def _segments(db):
    """Build one of each non-administrative NCoA segment for composite code."""
    from accounting.models import (
        EconomicSegment,
        FunctionalSegment,
        ProgrammeSegment,
        FundSegment,
        GeographicSegment,
    )
    econ, _ = EconomicSegment.objects.get_or_create(
        code="22010101",
        defaults={
            "name": "Construction Expenditure",
            "account_type_code": "2",
            "is_posting_level": True,
            "normal_balance": "DEBIT",
            "is_active": True,
        },
    )
    func, _ = FunctionalSegment.objects.get_or_create(
        code="70111",
        defaults={
            "name": "Executive and Legislative Organs",
            "division_code": "701",
            "group_code": "1",
            "class_code": "1",
            "is_active": True,
        },
    )
    prog, _ = ProgrammeSegment.objects.get_or_create(
        code="01010001000100",
        defaults={
            "name": "Test Programme",
            "policy_code": "01",
            "programme_code": "01",
            "project_code": "000100",
            "objective_code": "01",
            "activity_code": "00",
            "is_active": True,
        },
    )
    fund, _ = FundSegment.objects.get_or_create(
        code="01100",
        defaults={
            "name": "Consolidated Revenue Fund",
            "main_fund_code": "01",
            "sub_fund_code": "1",
            "fund_source_code": "00",
            "is_active": True,
        },
    )
    geo, _ = GeographicSegment.objects.get_or_create(
        code="52500000",
        defaults={
            "name": "Delta State",
            "zone_code": "5",
            "state_code": "25",
            "is_active": True,
        },
    )
    return SimpleNamespace(economic=econ, functional=func, programme=prog, fund=fund, geographic=geo)


@pytest.fixture
def ncoa_code(mda_segment, _segments):
    from accounting.models import NCoACode
    code, _ = NCoACode.objects.get_or_create(
        administrative=mda_segment,
        economic=_segments.economic,
        functional=_segments.functional,
        programme=_segments.programme,
        fund=_segments.fund,
        geographic=_segments.geographic,
        defaults={"is_active": True, "description": "Test composite code"},
    )
    return code


@pytest.fixture
def vendor(db):
    from procurement.models import Vendor
    v, _ = Vendor.objects.get_or_create(
        code="V0001",
        defaults={"name": "Delta Construction Ltd", "is_active": True},
    )
    return v


@pytest.fixture
def draft_contract(db, vendor, mda_segment, ncoa_code, fiscal_year, drafter):
    """A DRAFT contract (no balance yet) — activated by ``activated_contract``."""
    from contracts.models import Contract, ContractType, ProcurementMethod, ContractStatus
    contract = Contract.objects.create(
        contract_number="",  # assigned at activation
        title="Construction of Warri-Sapele Road (Section A)",
        contract_type=ContractType.WORKS,
        procurement_method=ProcurementMethod.OPEN_TENDER,
        status=ContractStatus.DRAFT,
        vendor=vendor,
        mda=mda_segment,
        ncoa_code=ncoa_code,
        fiscal_year=fiscal_year,
        original_sum=Decimal("100000000.00"),  # ₦100 M
        mobilization_rate=Decimal("15.00"),
        retention_rate=Decimal("5.00"),
        signed_date=date(2026, 1, 15),
        contract_start_date=date(2026, 2, 1),
        contract_end_date=date(2026, 11, 30),
        created_by=drafter,
        updated_by=drafter,
    )
    return contract


@pytest.fixture
def activated_contract(draft_contract, activator):
    """
    A fully ACTIVATED contract with a ContractBalance row.

    Ceiling: ₦100,000,000
    Mobilization rate: 15 %  (advance = ₦15,000,000)
    Retention rate:    5 %
    """
    from contracts.services.contract_activation import ContractActivationService
    ContractActivationService.activate(contract=draft_contract, actor=activator)
    draft_contract.refresh_from_db()
    return draft_contract


@pytest.fixture
def contract_balance(activated_contract):
    """Return the ContractBalance row for the activated contract."""
    from contracts.models import ContractBalance
    return ContractBalance.objects.get(pk=activated_contract.pk)


@pytest.fixture
def tsa_account(db):
    """Minimal TreasuryAccount for PaymentVoucher FKs."""
    from accounting.models.treasury import TreasuryAccount
    acc, _ = TreasuryAccount.objects.get_or_create(
        account_number="1234567890",
        defaults={
            "account_name": "PyTest TSA Sub-Account",
            "bank": "CBN",
            "account_type": "SUB_ACCOUNT",
        },
    )
    return acc


@pytest.fixture
def payment_voucher(ncoa_code, tsa_account, vendor):
    """A minimal PaymentVoucherGov row so raise_voucher has a real FK target."""
    from accounting.models.treasury import PaymentVoucherGov
    pv, _ = PaymentVoucherGov.objects.get_or_create(
        voucher_number="PV/TEST/2026/0001",
        defaults={
            "payment_type": "VENDOR",
            "ncoa_code": ncoa_code,
            "payee_name": vendor.name,
            "payee_account": "0011223344",
            "payee_bank": "Zenith Bank",
            "gross_amount": Decimal("0.00"),
            "net_amount": Decimal("0.00"),
            "narration": "PyTest voucher",
            "tsa_account": tsa_account,
        },
    )
    return pv
