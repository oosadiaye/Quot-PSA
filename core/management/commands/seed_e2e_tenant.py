"""Seed a deterministic tenant + minimum viable data for E2E tests.

Creates (or updates) on the **tenant schema** specified by
``--schema``:

* Admin user with a known password (`E2E_USER` / `E2E_PASSWORD` env)
* Active fiscal year
* Six NCoA segments (Admin, Economic, Functional, Programme, Fund, Geo)
* Legacy GL dimension rows mirrored from the segments (so procurement
  PRs can reference them)
* One ``Appropriation`` row with a non-zero amount
* One ``Vendor`` row

Idempotent: every row is ``get_or_create``'d. Safe to re-run.

On the **public schema** it ensures the ``Client`` row + ``Domain``
row exist for the schema, so django-tenants routing resolves.

Usage::

    ./manage.py seed_e2e_tenant \\
        --schema=ci_e2e \\
        --domain=ci_e2e.dtsg.test \\
        --username=ci_admin \\
        --password=Insecure-CI-1234

Outputs JSON on stdout with the IDs your CI workflow needs.
"""
from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import connection, transaction


class Command(BaseCommand):
    help = "Seed a deterministic tenant + minimum viable data for E2E tests."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--schema", default=os.getenv("E2E_TENANT_SCHEMA", "ci_e2e"))
        parser.add_argument("--domain", default=os.getenv("E2E_TENANT_DOMAIN", "ci_e2e.dtsg.test"))
        parser.add_argument("--name", default=os.getenv("E2E_TENANT_NAME", "CI E2E Tenant"))
        parser.add_argument("--username", default=os.getenv("E2E_USER", "ci_admin"))
        parser.add_argument("--password", default=os.getenv("E2E_PASSWORD", "Insecure-CI-1234"))
        parser.add_argument("--email", default=os.getenv("E2E_EMAIL", "ci@example.com"))

    def handle(self, *args, **opts) -> None:
        schema = opts["schema"]
        domain = opts["domain"]
        tenant_name = opts["name"]
        username = opts["username"]
        password = opts["password"]
        email = opts["email"]

        # 1. Public-schema work: tenant + domain rows.
        connection.set_schema_to_public()
        from tenants.models import Client, Domain
        # Login and tenant selection are public-schema URLs: a request whose Host is the tenant's own domain gets 404 for
        # them. The suite reaches the API as localhost and names the tenant in a header, so localhost must resolve to the
        # public tenant. A fresh CI database has none.
        public, _ = Client.objects.get_or_create(schema_name="public", defaults={"name": "Public Schema"})
        for host in ("localhost", "127.0.0.1"):
            Domain.objects.get_or_create(domain=host, defaults={"tenant": public, "is_primary": host == "localhost"})
        client, _ = Client.objects.get_or_create(
            schema_name=schema,
            defaults={"name": tenant_name},
        )
        Domain.objects.get_or_create(
            domain=domain,
            defaults={"tenant": client, "is_primary": True},
        )

        # Client.auto_create_schema is False, so a fresh database (CI) has no tenant schema yet. Build it the way the test
        # suite does: create the empty schema, run the contenttypes migrations to completion first (otherwise a later
        # migration's seeder trips the legacy NOT NULL "name" column of django_content_type), then migrate everything.
        # A no-op when the schema already exists and is current.
        self._ensure_schema(schema)

        # 2. Tenant-schema work: user + dimension data + appropriation.
        connection.set_schema(schema)
        try:
            with transaction.atomic():
                user_id = self._ensure_user(username, password, email)
                fiscal_year_id = self._ensure_fiscal_year()
                admin_id, fund_id, function_id, program_id, geo_id, economic_id = (
                    self._ensure_ncoa_segments()
                )
                legacy_ids = self._ensure_legacy_dimensions()
                appropriation_id = self._ensure_appropriation(
                    fiscal_year_id, admin_id, fund_id, function_id,
                    program_id, geo_id, economic_id,
                )
                vendor_id = self._ensure_vendor(fiscal_year_id)
                self._ensure_modules()
                employee_id = self._ensure_employee(user_id)
                advance_accounts = self._ensure_advance_accounts()
                revenue_head_id = self._ensure_revenue_head()
                self._ensure_open_period()

            output = {
                "schema": schema,
                "domain": domain,
                "tenant_id": client.id,
                "user_id": user_id,
                "username": username,
                "fiscal_year_id": fiscal_year_id,
                "appropriation_id": appropriation_id,
                "vendor_id": vendor_id,
                "employee_id": employee_id,
                "revenue_head_id": revenue_head_id,
                "advance_accounts": advance_accounts,
                "ncoa": {
                    "administrative": admin_id, "fund": fund_id,
                    "functional": function_id, "programme": program_id,
                    "geographic": geo_id, "economic": economic_id,
                },
                "legacy": legacy_ids,
            }
            self.stdout.write(json.dumps(output, indent=2))
        finally:
            connection.set_schema_to_public()

    # ── ensures ──

    def _ensure_schema(self, schema: str) -> None:
        import re
        from django.core.management import CommandError, call_command
        from django_tenants.utils import schema_context, schema_exists
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema):
            raise CommandError(f"Not a usable schema name: {schema!r}")
        if not schema_exists(schema):
            with connection.cursor() as cur:
                cur.execute(f'CREATE SCHEMA "{schema}"')
            with schema_context(schema):
                call_command("migrate", "contenttypes", verbosity=0, interactive=False)
        call_command("migrate_schemas", schema_name=schema, verbosity=0, interactive=False)
        connection.set_schema_to_public()

    def _ensure_user(self, username: str, password: str, email: str) -> int:
        from django.contrib.auth import get_user_model
        U = get_user_model()
        u, created = U.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True},
        )
        # Always (re)set the password so CI runs are deterministic.
        u.set_password(password)
        u.is_active = True
        u.save()
        self._ensure_membership(u)
        return u.id

    def _ensure_membership(self, user) -> None:
        """The user must belong to the tenant as an admin, or every API call is refused ("You do not have access to this
        tenant"). Membership lives in the public schema, while this runs inside the tenant's."""
        from django_tenants.utils import schema_context
        from tenants.models import Client, UserTenantRole
        schema = connection.schema_name
        with schema_context("public"):
            tenant = Client.objects.get(schema_name=schema)
            UserTenantRole.objects.update_or_create(
                user=user, tenant=tenant, defaults={"role": "admin", "is_active": True})

    def _ensure_fiscal_year(self) -> int:
        from accounting.models.advanced import FiscalYear
        year = date.today().year
        fy, _ = FiscalYear.objects.get_or_create(
            year=year,
            defaults={
                "name": f"FY {year}",
                "start_date": date(year, 1, 1),
                "end_date": date(year, 12, 31),
                "status": "Open",
                "is_active": True,
            },
        )
        if not fy.is_active:
            fy.is_active = True
            fy.save(update_fields=["is_active"])
        return fy.id

    def _ensure_ncoa_segments(self) -> tuple[int, int, int, int, int, int]:
        from accounting.models.gl import Account
        from accounting.models.ncoa import (
            AdministrativeSegment, FunctionalSegment,
            ProgrammeSegment, FundSegment, GeographicSegment,
        )
        admin_, _ = AdministrativeSegment.objects.get_or_create(
            code="010000000000",
            defaults={
                "name": "CI Test MDA", "level": "ORGANIZATION",
                "sector_code": "01", "is_mda": True, "mda_type": "MINISTRY",
            },
        )
        fund, _ = FundSegment.objects.get_or_create(
            code="1", defaults={"name": "Main Envelope"},
        )
        func, _ = FunctionalSegment.objects.get_or_create(
            code="70111",
            defaults={"name": "Executive Organ"},
        )
        prog, _ = ProgrammeSegment.objects.get_or_create(
            code="000000",
            defaults={"name": "General Programme"},
        )
        geo, _ = GeographicSegment.objects.get_or_create(
            code="1",
            defaults={"name": "State HQ"},
        )
        # The economic classifier is the GL account.
        econ, _ = Account.objects.get_or_create(
            code="22020306",
            defaults={
                "name": "Printing of Security Documents",
                "account_type": "Expense",
                "is_postable": True,
            },
        )
        return admin_.id, fund.id, func.id, prog.id, geo.id, econ.id

    def _ensure_legacy_dimensions(self) -> dict:
        # Mirror NCoA segments into the legacy ``accounting.gl`` tables
        # that procurement FKs reference.
        from accounting.models.gl import MDA, Fund, Function, Program, Geo
        m, _ = MDA.objects.get_or_create(
            code="010000000000", defaults={"name": "CI Test MDA"},
        )
        fu, _ = Fund.objects.get_or_create(code="1", defaults={"name": "Main Envelope"})
        fn, _ = Function.objects.get_or_create(code="70111", defaults={"name": "Executive Organ"})
        pr, _ = Program.objects.get_or_create(code="000000", defaults={"name": "General Programme"})
        ge, _ = Geo.objects.get_or_create(code="1", defaults={"name": "State HQ"})
        return {"mda": m.id, "fund": fu.id, "function": fn.id, "program": pr.id, "geo": ge.id}

    def _ensure_appropriation(
        self, fy_id, admin_id, fund_id, func_id, prog_id, geo_id, econ_id,
    ) -> int:
        from budget.models import Appropriation
        appr, _ = Appropriation.objects.get_or_create(
            fiscal_year_id=fy_id,
            administrative_id=admin_id,
            economic_id=econ_id,
            fund_id=fund_id,
            functional_id=func_id,
            programme_id=prog_id,
            geographic_id=geo_id,
            defaults={
                "amount_approved": Decimal("100000000.00"),
                "appropriation_type": "RECURRENT",
                "status": "ACTIVE",
                "description": "CI E2E seed appropriation",
            },
        )
        return appr.id

    OPTIONAL_MODULES = (
        "budget_prep", "personnel_budget", "cash_planning", "catalogue", "egp", "revenue_admin", "debt",
        "staff_advances", "fleet", "legal", "disclosure", "internal_audit", "transparency", "results", "integrations",
    )

    def _ensure_modules(self) -> None:
        """Switch the optional modules on for this tenant. They default to off, and a spec that finds a module off can only
        see the 'Module Disabled' page, which proves nothing about the module."""
        from core.models import TenantModule
        for key in self.OPTIONAL_MODULES:
            TenantModule.objects.update_or_create(module_name=key, defaults={"is_active": True})

    def _ensure_employee(self, user_id: int) -> int:
        """An employee record for the e2e admin, so staff advances and travel requests have someone to belong to. It is the
        admin's own record because a user without the view-all permission only ever sees their own employee."""
        from django.contrib.auth import get_user_model
        from hrm.models import Department, Employee, Position
        user = get_user_model().objects.get(pk=user_id)
        dept, _ = Department.objects.get_or_create(code="CI-D", defaults={"name": "CI Department"})
        pos, _ = Position.objects.get_or_create(
            code="CI-P", defaults={"title": "CI Officer", "department": dept, "grade": "Mid"})
        emp, _ = Employee.objects.get_or_create(
            user=user,
            defaults={"employee_number": "CI-EMP-ADMIN", "department": dept, "position": pos, "hire_date": date(2025, 1, 1)},
        )
        return emp.id

    def _ensure_revenue_head(self) -> int:
        """One revenue head (and its revenue account), so revenue administration has something to assess against."""
        from accounting.models import Account, RevenueHead
        econ, _ = Account.objects.get_or_create(
            code="12000100",
            defaults={"name": "Ground Rent Revenue (CI)", "account_type": "Revenue", "is_active": True},
        )
        head, _ = RevenueHead.objects.get_or_create(
            code="CI-RH-001",
            defaults={"name": "CI Ground Rent", "economic_segment": econ, "revenue_type": "OTHER"},
        )
        return head.id

    def _ensure_advance_accounts(self) -> dict:
        """The accounts a staff advance touches: the tagged recon account (an asset) and a cash account."""
        from accounting.models import Account
        recon, _ = Account.objects.update_or_create(
            code="19001000",
            defaults={"name": "Staff Advances (CI)", "account_type": "Asset",
                      "reconciliation_type": "staff_advance", "is_active": True},
        )
        cash, _ = Account.objects.update_or_create(
            code="31009000",
            defaults={"name": "TSA Cash (CI advances)", "account_type": "Asset", "is_active": True},
        )
        return {"recon": recon.id, "cash": cash.id}

    def _ensure_open_period(self) -> None:
        """An open monthly period covering today: the ledger refuses to post into a date with none."""
        import calendar
        from django.utils import timezone
        from accounting.models import FiscalPeriod
        today = timezone.localdate()
        month_end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        FiscalPeriod.objects.get_or_create(
            fiscal_year=today.year, period_number=today.month, period_type="Monthly",
            defaults={"start_date": today.replace(day=1), "end_date": month_end, "status": "Open", "is_closed": False},
        )

    def _ensure_vendor(self, fy_id) -> int:
        from accounting.models import Account
        from procurement.models import Vendor, VendorCategory
        # A vendor category must point at an accounts-payable reconciliation account.
        payable, _ = Account.objects.get_or_create(
            code="21009000",
            defaults={"name": "Accounts Payable (CI)", "account_type": "Liability",
                      "reconciliation_type": "accounts_payable", "is_active": True},
        )
        cat, _ = VendorCategory.objects.get_or_create(
            name="LOCAL supplier/Contractors",
            defaults={"code": "CI-LOCAL", "reconciliation_account": payable},
        )
        v, _ = Vendor.objects.get_or_create(
            code="CI-V-001",
            defaults={
                "name": "CI Test Vendor",
                "category": cat,
                "email": "vendor@example.com",
                "is_active": True,
                "registration_fiscal_year_id": fy_id,
                "registration_date": date.today(),
                "expiry_date": date(date.today().year + 1, 12, 31),
            },
        )
        return v.id
