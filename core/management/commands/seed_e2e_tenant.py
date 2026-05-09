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
        client, _ = Client.objects.get_or_create(
            schema_name=schema,
            defaults={"name": tenant_name},
        )
        Domain.objects.get_or_create(
            domain=domain,
            defaults={"tenant": client, "is_primary": True},
        )

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

            output = {
                "schema": schema,
                "domain": domain,
                "tenant_id": client.id,
                "user_id": user_id,
                "username": username,
                "fiscal_year_id": fiscal_year_id,
                "appropriation_id": appropriation_id,
                "vendor_id": vendor_id,
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
        return u.id

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
        from accounting.models.ncoa import (
            AdministrativeSegment, EconomicSegment, FunctionalSegment,
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
        econ, _ = EconomicSegment.objects.get_or_create(
            code="22020306",
            defaults={
                "name": "Printing of Security Documents",
                "account_type_code": "2",
                "is_posting_level": True,
                "normal_balance": "DEBIT",
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

    def _ensure_vendor(self, fy_id) -> int:
        from procurement.models import Vendor, VendorCategory
        cat, _ = VendorCategory.objects.get_or_create(
            name="LOCAL supplier/Contractors",
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
