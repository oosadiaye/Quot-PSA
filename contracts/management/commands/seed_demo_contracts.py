"""
Seed three sample Delta State government contracts for the D8 demo
fixture suite.

Contracts seeded
----------------
1. DSG/WORKS/2026/001 — Construction of Warri-Sapele Road (Section A)
   Ministry of Works, ₦450,000,000 — ACTIVATED.

2. DSG/CONSULTANCY/2026/002 — Delta State M&E Framework Consultancy
   Ministry of Economic Planning, ₦45,000,000 — ACTIVATED.

3. DSG/GOODS/2026/003 — Medical Equipment Supply (Delta State Univ. TH)
   Ministry of Health, ₦120,000,000 — DRAFT (awaiting BPP no-objection).

Usage
-----
    python manage.py tenant_command seed_demo_contracts --schema=<name>
    python manage.py tenant_command seed_demo_contracts --schema=<name> --clear
    python manage.py tenant_command seed_demo_contracts --schema=<name> --dry-run

The ``contract_number`` field is the idempotency key — re-running the
command will ``update_or_create`` rather than create duplicates. Every
seeded row carries the ``DEMO-CON`` marker in its ``reference`` field so
``--clear`` can reliably find previous seeds without over-matching real
data.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction


_TAG = "DEMO-CON"

# Stable contract_numbers double as the idempotency key.
_CONTRACT_SPECS: list[dict[str, Any]] = [
    {
        "contract_number": "DSG/WORKS/2026/001",
        "title": "Construction of Warri-Sapele Road (Section A)",
        "contract_type": "WORKS",
        "procurement_method": "OPEN_TENDER",
        "mda_name": "Ministry of Works",
        "vendor_code": "DSG-V-001",
        "vendor_name": "Delta Infrastructure & Construction Ltd",
        "original_sum": Decimal("450000000.00"),
        "mobilization_rate": Decimal("15.00"),
        "retention_rate": Decimal("5.00"),
        "bpp_no_objection_ref": "BPP/DSG/WORKS/2026/0087",
        "due_process_certificate": "DPB/DSG/2026/014",
        "signed_date": date(2026, 1, 20),
        "contract_start_date": date(2026, 2, 1),
        "contract_end_date": date(2026, 11, 30),
        "activate": True,
        "description": (
            "Reconstruction of the Warri–Sapele expressway, Section A "
            "(km 0 – km 22). Scope: subgrade, base course, asphalt "
            "wearing course, drainage, road furniture."
        ),
    },
    {
        "contract_number": "DSG/CONSULTANCY/2026/002",
        "title": "Delta State M&E Framework Consultancy",
        "contract_type": "CONSULTANCY",
        "procurement_method": "RESTRICTED",
        "mda_name": "Ministry of Economic Planning",
        "vendor_code": "DSG-V-002",
        "vendor_name": "Niger Delta Advisory Partners",
        "original_sum": Decimal("45000000.00"),
        "mobilization_rate": Decimal("20.00"),
        "retention_rate": Decimal("0.00"),
        "bpp_no_objection_ref": "BPP/DSG/CONS/2026/0019",
        "due_process_certificate": "DPB/DSG/2026/009",
        "signed_date": date(2026, 1, 10),
        "contract_start_date": date(2026, 1, 15),
        "contract_end_date": date(2026, 12, 31),
        "activate": True,
        "description": (
            "Design and roll-out of the state-wide Monitoring & "
            "Evaluation framework for capital projects, including "
            "dashboards, field protocols, and staff training."
        ),
    },
    {
        "contract_number": "DSG/GOODS/2026/003",
        "title": "Medical Equipment Supply — Delta State Univ. Teaching Hospital",
        "contract_type": "GOODS",
        "procurement_method": "OPEN_TENDER",
        "mda_name": "Ministry of Health",
        "vendor_code": "DSG-V-003",
        "vendor_name": "MedEquip Nigeria Ltd",
        "original_sum": Decimal("120000000.00"),
        "mobilization_rate": Decimal("10.00"),
        "retention_rate": Decimal("5.00"),
        "bpp_no_objection_ref": "",  # still pending — keeps row in DRAFT
        "due_process_certificate": "",
        "signed_date": None,
        "contract_start_date": None,
        "contract_end_date": None,
        "activate": False,
        "description": (
            "Supply and installation of diagnostic imaging and "
            "intensive-care equipment for DELSUTH. Awaiting BPP "
            "Certificate of No Objection."
        ),
    },
]


class Command(BaseCommand):
    help = "Seed 3 sample Delta State government contracts (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear", action="store_true",
            help="Delete existing DEMO-CON contracts before re-seeding.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would happen without writing.",
        )

    def handle(self, *args, **options):
        clear: bool = options["clear"]
        dry: bool = options["dry_run"]

        self.stdout.write(self.style.NOTICE(
            f"Seeding demo contracts (clear={clear}, dry_run={dry})"
        ))

        prereq = self._resolve_prerequisites(dry)
        if prereq is None:
            return

        if clear and not dry:
            self._clear()

        if dry:
            self.stdout.write(
                f"  Would seed {len(_CONTRACT_SPECS)} contracts "
                f"({sum(1 for s in _CONTRACT_SPECS if s['activate'])} activated)."
            )
            return

        with transaction.atomic():
            created, updated, activated = self._seed(prereq)

        self.stdout.write(self.style.SUCCESS(
            f"Contract seed complete: {created} created, "
            f"{updated} updated, {activated} activated."
        ))

    # -----------------------------------------------------------------
    # Prerequisite resolution
    # -----------------------------------------------------------------
    def _resolve_prerequisites(self, dry: bool) -> dict | None:
        """Resolve shared FKs. Returns None + warning if any are missing."""
        from accounting.models import (
            AdministrativeSegment, NCoACode, FiscalYear,
        )

        fy = FiscalYear.objects.filter(year=2026).first()
        if fy is None:
            fy, _ = (FiscalYear.objects.get_or_create(
                year=2026,
                defaults={
                    "name": "FY 2026",
                    "start_date": date(2026, 1, 1),
                    "end_date": date(2026, 12, 31),
                    "is_active": True,
                    "status": "Open",
                },
            ) if not dry else (None, False))
            if dry and fy is None:
                self.stdout.write("  (dry) Would create FY 2026.")

        ncoa = NCoACode.objects.filter(is_active=True).first()
        if ncoa is None:
            self.stdout.write(self.style.WARNING(
                "  No active NCoACode rows — run seed_ncoa_segments first. "
                "Skipping contract seed."
            ))
            return None

        # Use the first active MDA as a fallback for any mda_name that
        # can't be found; in a fresh DB we get_or_create a stub.
        default_mda = AdministrativeSegment.objects.filter(is_active=True, is_mda=True).first()
        if default_mda is None:
            self.stdout.write(self.style.WARNING(
                "  No active MDA AdministrativeSegment rows — "
                "run seed_administrative_segments first. Skipping."
            ))
            return None

        creator = self._get_or_create_system_user("demo_contract_drafter")
        activator = self._get_or_create_system_user("demo_contract_activator")

        return {
            "fiscal_year": fy,
            "ncoa_code": ncoa,
            "default_mda": default_mda,
            "creator": creator,
            "activator": activator,
        }

    @staticmethod
    def _get_or_create_system_user(username: str):
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={
                "email": f"{username}@demo.local",
                "first_name": "Demo",
                "last_name": username.replace("_", " ").title(),
                "is_active": True,
            },
        )
        return user

    # -----------------------------------------------------------------
    # Clear
    # -----------------------------------------------------------------
    def _clear(self) -> None:
        from contracts.models import Contract
        qs = Contract.objects.filter(reference__startswith=_TAG)
        n = qs.count()
        # Related ContractBalance cascades on contract delete.
        qs.delete()
        self.stdout.write(self.style.WARNING(
            f"  Cleared: {n} demo contracts."
        ))

    # -----------------------------------------------------------------
    # Seed
    # -----------------------------------------------------------------
    def _seed(self, prereq: dict) -> tuple[int, int, int]:
        from accounting.models import AdministrativeSegment
        from contracts.models import Contract, ContractStatus
        from contracts.services.contract_activation import ContractActivationService
        from procurement.models import Vendor

        created = 0
        updated = 0
        activated = 0

        for spec in _CONTRACT_SPECS:
            mda = AdministrativeSegment.objects.filter(
                name__iexact=spec["mda_name"], is_active=True,
            ).first() or prereq["default_mda"]

            vendor, _ = Vendor.objects.get_or_create(
                code=spec["vendor_code"],
                defaults={"name": spec["vendor_name"], "is_active": True},
            )

            reference = f"{_TAG}/{spec['contract_number']}"
            defaults = {
                "title":                spec["title"],
                "description":          spec["description"],
                "reference":            reference,
                "contract_type":        spec["contract_type"],
                "procurement_method":   spec["procurement_method"],
                "vendor":               vendor,
                "mda":                  mda,
                "ncoa_code":            prereq["ncoa_code"],
                "fiscal_year":          prereq["fiscal_year"],
                "original_sum":         spec["original_sum"],
                "mobilization_rate":    spec["mobilization_rate"],
                "retention_rate":       spec["retention_rate"],
                "bpp_no_objection_ref": spec["bpp_no_objection_ref"],
                "due_process_certificate": spec["due_process_certificate"],
                "signed_date":          spec["signed_date"],
                "contract_start_date":  spec["contract_start_date"],
                "contract_end_date":    spec["contract_end_date"],
                "created_by":           prereq["creator"],
                "updated_by":           prereq["creator"],
            }

            contract = Contract.objects.filter(
                contract_number=spec["contract_number"],
            ).first()
            if contract is None:
                contract = Contract.objects.create(
                    contract_number=spec["contract_number"],
                    status=ContractStatus.DRAFT,
                    **defaults,
                )
                created += 1
            else:
                for field, value in defaults.items():
                    setattr(contract, field, value)
                contract.save()
                updated += 1

            # Activate if requested and still in DRAFT.
            if spec["activate"] and contract.status == ContractStatus.DRAFT:
                try:
                    ContractActivationService.activate(
                        contract=contract,
                        actor=prereq["activator"],
                        notes="Seeded demo activation.",
                    )
                    activated += 1
                except Exception as exc:  # pragma: no cover — diagnostic only
                    self.stdout.write(self.style.WARNING(
                        f"  Could not activate {spec['contract_number']}: {exc}"
                    ))

        return created, updated, activated
