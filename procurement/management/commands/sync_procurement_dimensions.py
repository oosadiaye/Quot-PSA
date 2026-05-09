"""Sync legacy GL dimension tables from NCoA segments.

Background
----------
``Appropriation`` (budget side) references the new NCoA segment models:
``AdministrativeSegment``, ``FundSegment``, ``FunctionalSegment``,
``ProgrammeSegment``, ``GeographicSegment``, ``EconomicSegment``.

``PurchaseRequest`` / ``PurchaseOrder`` / ``GoodsReceivedNote`` (procurement
side) reference the legacy flat dimension tables defined in
``accounting.models.gl``: ``MDA``, ``Fund``, ``Function``, ``Program``,
``Geo``.

Both sets carry a ``code`` field and the legacy tables exist in the same
schema as the segments — they are simply not kept in sync. Tenants that
populate appropriations through the budget UI end up with no records in
the legacy tables, which means procurement requests against the same
vote fail with ``Invalid pk - object does not exist``.

This command performs a one-way ``upsert`` from segments to legacy
tables, matching by ``code``. It is idempotent: existing rows are
updated to mirror the segment ``name`` / ``description``; missing rows
are created.

Usage::

    ./manage.py sync_procurement_dimensions
    ./manage.py sync_procurement_dimensions --schema=<tenant_schema>
    ./manage.py sync_procurement_dimensions --dry-run
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection, transaction


class Command(BaseCommand):
    help = (
        "Mirror legacy procurement dimension tables (MDA/Fund/Function/Program/Geo) "
        "from the NCoA segment tables. Idempotent."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--schema",
            help="Run against a specific django-tenants schema. Defaults to the "
                 "schema set on the connection.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be created/updated without writing.",
        )

    def handle(self, *args, **options) -> None:
        schema = options.get("schema")
        dry_run = options.get("dry_run", False)

        if schema:
            connection.set_schema(schema)
            self.stdout.write(self.style.NOTICE(f"Targeting schema: {schema}"))

        # Late imports — these models are tenant-scoped, so the tenant
        # schema must be active before the cursor sees them.
        from accounting.models.gl import MDA, Fund, Function, Program, Geo
        from accounting.models.ncoa import (
            AdministrativeSegment, FundSegment, FunctionalSegment,
            ProgrammeSegment, GeographicSegment,
        )

        pairs = [
            ("MDA", AdministrativeSegment, MDA, ("code", "name")),
            ("Fund", FundSegment, Fund, ("code", "name")),
            ("Function", FunctionalSegment, Function, ("code", "name")),
            ("Program", ProgrammeSegment, Program, ("code", "name")),
            ("Geo", GeographicSegment, Geo, ("code", "name")),
        ]

        with transaction.atomic():
            sp = transaction.savepoint()
            try:
                for label, src_model, dst_model, fields in pairs:
                    self._sync_pair(label, src_model, dst_model, fields, dry_run)
                if dry_run:
                    transaction.savepoint_rollback(sp)
                    self.stdout.write(self.style.WARNING("[dry-run] all changes rolled back"))
                else:
                    transaction.savepoint_commit(sp)
            except Exception:
                transaction.savepoint_rollback(sp)
                raise

    def _sync_pair(self, label, src_model, dst_model, fields, dry_run) -> None:
        created = 0
        updated = 0
        unchanged = 0
        for src in src_model.objects.all():
            code = getattr(src, "code", None)
            name = getattr(src, "name", "")
            if not code:
                continue
            existing = dst_model.objects.filter(code=code).first()
            if existing is None:
                if not dry_run:
                    dst_model.objects.create(code=code, name=name)
                created += 1
            else:
                stale_name = existing.name != name
                if stale_name:
                    if not dry_run:
                        existing.name = name
                        existing.save(update_fields=["name"])
                    updated += 1
                else:
                    unchanged += 1
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            f"{prefix}{label}: +{created} created, ~{updated} updated, ={unchanged} unchanged"
        )
