"""
Seed the public-sector approval template catalogue.

Creates the canonical Nigerian IFMIS / IPSAS approval chains for every
built-in document type (PR, PO, GRN, Invoice Verification, PV, Journal,
Appropriation, Warrant, Virement, Revenue Budget, Revenue Write-Off,
Fixed Asset, Asset Disposal, Payroll) with a cross-cutting Internal
Audit Department step baked into the higher-value flows.

Idempotent: running twice will not duplicate groups or templates.
Run with:  python manage.py seed_public_sector_approvals [--tenant <schema>]

NOTE: This command operates on whatever schema is active. In a
django-tenants deployment it must be run inside a tenant schema
(e.g. `./manage.py tenant_command seed_public_sector_approvals`).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from workflow.models import (
    ApprovalGroup,
    ApprovalTemplate,
    ApprovalTemplateStep,
    GlobalApprovalSettings,
)


# ─────────────────────────────────────────────────────────────────────────────
# Role groups — keyed by stable slug so the seeder is idempotent.
# Descriptions double as UI documentation for the template designer.
# ─────────────────────────────────────────────────────────────────────────────

PUBLIC_SECTOR_GROUPS: dict[str, dict] = {
    "mda_accounting_officer": {
        "name": "MDA Accounting Officer",
        "description": "Head of department / Permanent Secretary of the originating MDA. "
                       "First-line approval on all originating documents.",
    },
    "mda_store_officer": {
        "name": "MDA Store Officer",
        "description": "Acknowledges physical receipt for GRN.",
    },
    "mda_internal_auditor": {
        "name": "MDA Internal Auditor",
        "description": "MDA-level internal audit sign-off on procurement and payment files.",
    },
    "due_process_office": {
        "name": "Due Process / Procurement Office",
        "description": "Central tender / due-process vetting (BPP-style) for PR and PO "
                       "above the procurement threshold.",
    },
    "budget_office": {
        "name": "Budget & Appropriation Office",
        "description": "Budget Office — authors appropriations, warrants and virements.",
    },
    "accountant_general": {
        "name": "Accountant-General",
        "description": "Office of the Accountant-General of the State/Federation. "
                       "Posts to GL, authorises cash movement from TSA.",
    },
    "tsa_controller": {
        "name": "TSA Controller",
        "description": "Treasury Single Account controller — final release of funds.",
    },
    "finance_commissioner": {
        "name": "Honourable Commissioner of Finance",
        "description": "Political head of finance — approves appropriations, revenue "
                       "write-offs and high-value payments.",
    },
    "internal_audit_dept": {
        "name": "Internal Audit Department (Oversight)",
        "description": "Cross-cutting Internal Audit Department that oversees every "
                       "module above the audit threshold. Mandatory step on PR, PO, "
                       "GRN, Invoice Verification, PV, Journal, Appropriation, Warrant, "
                       "Virement, Revenue Write-Off and Asset Disposal.",
    },
    "asset_management_officer": {
        "name": "Asset Management Officer",
        "description": "Custodian of the fixed asset register — sign-off on asset "
                       "capitalisation and disposal.",
    },
    "revenue_officer": {
        "name": "Revenue Officer",
        "description": "Originator of revenue assessments, collections and write-offs.",
    },
    "hr_manager": {
        "name": "HR Manager",
        "description": "Payroll and leave approver.",
    },
}


# Thresholds (NGN). Tune once centrally.
THR_AUDIT_MIN = Decimal("1000000")        # ≥ NGN 1M triggers Internal Audit Dept oversight
THR_DUE_PROCESS = Decimal("10000000")     # ≥ NGN 10M triggers Due Process Office
THR_AG_MIN = Decimal("5000000")           # ≥ NGN 5M triggers Accountant-General
THR_FC_MIN = Decimal("50000000")          # ≥ NGN 50M triggers Finance Commissioner


@dataclass(frozen=True)
class StepSpec:
    group_slug: str
    sequence: int
    min_amount: Optional[Decimal] = None  # overrides group default for this template
    max_amount: Optional[Decimal] = None


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    model: str          # ContentType model (lowercase)
    description: str
    steps: tuple[StepSpec, ...]
    approval_type: str = "Sequential"


# ─────────────────────────────────────────────────────────────────────────────
# Module → GlobalApprovalSettings defaults.
# ─────────────────────────────────────────────────────────────────────────────

MODULE_SETTINGS: dict[str, dict] = {
    "PurchaseRequest":     {"mode": "Required", "low": "50000",   "high": "10000000"},
    "PurchaseOrder":       {"mode": "Required", "low": "50000",   "high": "10000000"},
    "GoodsReceivedNote":   {"mode": "Required", "low": "0",       "high": "10000000"},
    "InvoiceVerification": {"mode": "Required", "low": "0",       "high": "10000000"},
    "PurchaseReturn":      {"mode": "Required", "low": "0",       "high": "10000000"},
    "PaymentVoucher":      {"mode": "Required", "low": "0",       "high": "10000000"},
    "Appropriation":       {"mode": "Required", "low": "0",       "high": "1000000000"},
    "Warrant":             {"mode": "Required", "low": "0",       "high": "1000000000"},
    "RevenueWriteOff":     {"mode": "Required", "low": "0",       "high": "10000000"},
    "AssetDisposal":       {"mode": "Required", "low": "0",       "high": "10000000"},
    "Budget":              {"mode": "Required", "low": "0",       "high": "1000000000"},
    "JournalEntry":        {"mode": "Required", "low": "100000",  "high": "10000000"},
    "LeaveRequest":        {"mode": "Required", "low": "0",       "high": "0"},
    "PayrollRun":          {"mode": "Required", "low": "0",       "high": "100000000"},
}


# ─────────────────────────────────────────────────────────────────────────────
# Template catalogue.
# Each model gets TWO chains: a Standard chain for low-value documents
# (no Audit, no Due Process) and an Oversight chain triggered by amount
# thresholds that inserts the Internal Audit Department and, where
# applicable, Due Process / Accountant-General / Finance Commissioner.
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES: tuple[TemplateSpec, ...] = (
    # ── Purchase Requisition ────────────────────────────────────────────────
    TemplateSpec(
        name="PR — Standard (< NGN 1M)",
        model="purchaserequest",
        description="Low-value PR: MDA Accounting Officer only.",
        steps=(
            StepSpec("mda_accounting_officer", 1, Decimal("0"), THR_AUDIT_MIN),
        ),
    ),
    TemplateSpec(
        name="PR — With Audit Oversight (≥ NGN 1M)",
        model="purchaserequest",
        description="Material PR: MDA AO → Due Process (≥NGN 10M) → MDA Internal Auditor "
                    "→ Internal Audit Department.",
        steps=(
            StepSpec("mda_accounting_officer", 1, THR_AUDIT_MIN, None),
            StepSpec("due_process_office",     2, THR_DUE_PROCESS, None),
            StepSpec("mda_internal_auditor",   3, THR_AUDIT_MIN, None),
            StepSpec("internal_audit_dept",    4, THR_AUDIT_MIN, None),
        ),
    ),

    # ── Purchase Order ──────────────────────────────────────────────────────
    TemplateSpec(
        name="PO — Standard (< NGN 1M)",
        model="purchaseorder",
        description="Low-value PO: MDA Accounting Officer only.",
        steps=(
            StepSpec("mda_accounting_officer", 1, Decimal("0"), THR_AUDIT_MIN),
        ),
    ),
    TemplateSpec(
        name="PO — With Audit & AG Oversight (≥ NGN 1M)",
        model="purchaseorder",
        description="Material PO: MDA AO → Due Process (≥NGN 10M) → Accountant-General "
                    "(≥NGN 5M) → Internal Audit Department.",
        steps=(
            StepSpec("mda_accounting_officer", 1, THR_AUDIT_MIN, None),
            StepSpec("due_process_office",     2, THR_DUE_PROCESS, None),
            StepSpec("accountant_general",     3, THR_AG_MIN, None),
            StepSpec("internal_audit_dept",    4, THR_AUDIT_MIN, None),
        ),
    ),

    # ── Goods Received Note ─────────────────────────────────────────────────
    TemplateSpec(
        name="GRN — Standard",
        model="goodsreceivednote",
        description="Store Officer acknowledges receipt → MDA Accounting Officer confirms.",
        steps=(
            StepSpec("mda_store_officer",      1, Decimal("0"), THR_AUDIT_MIN),
            StepSpec("mda_accounting_officer", 2, Decimal("0"), THR_AUDIT_MIN),
        ),
    ),
    TemplateSpec(
        name="GRN — With Audit Spot-Check (≥ NGN 1M)",
        model="goodsreceivednote",
        description="Store Officer → MDA AO → Internal Audit Department spot-check.",
        steps=(
            StepSpec("mda_store_officer",      1, THR_AUDIT_MIN, None),
            StepSpec("mda_accounting_officer", 2, THR_AUDIT_MIN, None),
            StepSpec("internal_audit_dept",    3, THR_AUDIT_MIN, None),
        ),
    ),

    # ── Invoice Verification (3-Way Match) ─────────────────────────────────
    TemplateSpec(
        name="Invoice Verification — Standard (< NGN 1M)",
        model="invoicematching",
        description="3-way match verified by MDA Accounting Officer.",
        steps=(
            StepSpec("mda_accounting_officer", 1, Decimal("0"), THR_AUDIT_MIN),
        ),
    ),
    TemplateSpec(
        name="Invoice Verification — With Audit & AG (≥ NGN 1M)",
        model="invoicematching",
        description="MDA AO → Internal Audit Department → Accountant-General (≥NGN 5M).",
        steps=(
            StepSpec("mda_accounting_officer", 1, THR_AUDIT_MIN, None),
            StepSpec("internal_audit_dept",    2, THR_AUDIT_MIN, None),
            StepSpec("accountant_general",     3, THR_AG_MIN, None),
        ),
    ),

    # ── Purchase Return ────────────────────────────────────────────────────
    TemplateSpec(
        name="Purchase Return",
        model="purchasereturn",
        description="Store Officer initiates → MDA Accounting Officer → "
                    "Internal Audit Department (material returns).",
        steps=(
            StepSpec("mda_store_officer",      1),
            StepSpec("mda_accounting_officer", 2),
            StepSpec("internal_audit_dept",    3),
        ),
    ),

    # ── Payment Voucher (PV) ────────────────────────────────────────────────
    TemplateSpec(
        name="PV — Standard (< NGN 1M)",
        model="paymentvoucher",
        description="MDA AO → Accountant-General → TSA Controller.",
        steps=(
            StepSpec("mda_accounting_officer", 1, Decimal("0"), THR_AUDIT_MIN),
            StepSpec("accountant_general",     2, Decimal("0"), THR_AUDIT_MIN),
            StepSpec("tsa_controller",         3, Decimal("0"), THR_AUDIT_MIN),
        ),
    ),
    TemplateSpec(
        name="PV — With Audit & FC Oversight (≥ NGN 1M)",
        model="paymentvoucher",
        description="MDA AO → Internal Audit Department → Accountant-General → "
                    "Finance Commissioner (≥NGN 50M) → TSA Controller.",
        steps=(
            StepSpec("mda_accounting_officer", 1, THR_AUDIT_MIN, None),
            StepSpec("internal_audit_dept",    2, THR_AUDIT_MIN, None),
            StepSpec("accountant_general",     3, THR_AUDIT_MIN, None),
            StepSpec("finance_commissioner",   4, THR_FC_MIN, None),
            StepSpec("tsa_controller",         5, THR_AUDIT_MIN, None),
        ),
    ),

    # ── Journal Entry (JV) ──────────────────────────────────────────────────
    TemplateSpec(
        name="Journal — Standard (< NGN 1M)",
        model="journalheader",
        description="MDA AO → Accountant-General.",
        steps=(
            StepSpec("mda_accounting_officer", 1, Decimal("0"), THR_AUDIT_MIN),
            StepSpec("accountant_general",     2, Decimal("0"), THR_AUDIT_MIN),
        ),
    ),
    TemplateSpec(
        name="Journal — With Audit Oversight (≥ NGN 1M)",
        model="journalheader",
        description="MDA AO → Accountant-General → Internal Audit Department.",
        steps=(
            StepSpec("mda_accounting_officer", 1, THR_AUDIT_MIN, None),
            StepSpec("accountant_general",     2, THR_AUDIT_MIN, None),
            StepSpec("internal_audit_dept",    3, THR_AUDIT_MIN, None),
        ),
    ),

    # ── Appropriation (Create) ──────────────────────────────────────────────
    TemplateSpec(
        name="Appropriation — Creation",
        model="appropriation",
        description="Budget Office drafts → Accountant-General → Finance Commissioner "
                    "→ Internal Audit Department.",
        steps=(
            StepSpec("budget_office",        1),
            StepSpec("accountant_general",   2),
            StepSpec("finance_commissioner", 3),
            StepSpec("internal_audit_dept",  4),
        ),
    ),

    # ── Warrant / AIE ──────────────────────────────────────────────────────
    TemplateSpec(
        name="Warrant / AIE — Cash Release",
        model="warrant",
        description="Budget Office → Accountant-General → Internal Audit Department.",
        steps=(
            StepSpec("budget_office",       1),
            StepSpec("accountant_general",  2),
            StepSpec("internal_audit_dept", 3),
        ),
    ),

    # ── Virement ───────────────────────────────────────────────────────────
    TemplateSpec(
        name="Virement — Between Economic Lines",
        model="appropriationvirement",
        description="Budget Office → Accountant-General → Internal Audit Department.",
        steps=(
            StepSpec("budget_office",       1),
            StepSpec("accountant_general",  2),
            StepSpec("internal_audit_dept", 3),
        ),
    ),

    # ── Revenue Budget ─────────────────────────────────────────────────────
    TemplateSpec(
        name="Revenue Budget — Target Setting",
        model="revenuebudget",
        description="Budget Office → Accountant-General.",
        steps=(
            StepSpec("budget_office",      1),
            StepSpec("accountant_general", 2),
        ),
    ),

    # ── Revenue Write-Off ──────────────────────────────────────────────────
    TemplateSpec(
        name="Revenue Write-Off",
        model="baddebtwriteoff",
        description="Revenue Officer → Accountant-General → Internal Audit Department → "
                    "Finance Commissioner.",
        steps=(
            StepSpec("revenue_officer",      1),
            StepSpec("accountant_general",   2),
            StepSpec("internal_audit_dept",  3),
            StepSpec("finance_commissioner", 4),
        ),
    ),

    # ── Fixed Asset Capitalisation ─────────────────────────────────────────
    TemplateSpec(
        name="Fixed Asset — Capitalisation",
        model="fixedasset",
        description="Asset Management Officer → MDA AO → Accountant-General.",
        steps=(
            StepSpec("asset_management_officer", 1),
            StepSpec("mda_accounting_officer",   2),
            StepSpec("accountant_general",       3),
        ),
    ),

    # ── Asset Disposal ─────────────────────────────────────────────────────
    TemplateSpec(
        name="Asset Disposal",
        model="assetdisposal",
        description="Asset Management Officer → MDA AO → Internal Audit Department → "
                    "Accountant-General.",
        steps=(
            StepSpec("asset_management_officer", 1),
            StepSpec("mda_accounting_officer",   2),
            StepSpec("internal_audit_dept",      3),
            StepSpec("accountant_general",       4),
        ),
    ),

    # ── Payroll Run ────────────────────────────────────────────────────────
    TemplateSpec(
        name="Payroll Run",
        model="payrollrun",
        description="HR Manager → Accountant-General → Internal Audit Department → "
                    "TSA Controller.",
        steps=(
            StepSpec("hr_manager",          1),
            StepSpec("accountant_general",  2),
            StepSpec("internal_audit_dept", 3),
            StepSpec("tsa_controller",      4),
        ),
    ),

    # ── Leave Request (non-financial) ──────────────────────────────────────
    TemplateSpec(
        name="Leave Request",
        model="leaverequest",
        description="MDA Accounting Officer → HR Manager.",
        steps=(
            StepSpec("mda_accounting_officer", 1),
            StepSpec("hr_manager",             2),
        ),
    ),
)


class Command(BaseCommand):
    help = "Seed public-sector approval groups, templates and global module settings."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--purge-private",
            action="store_true",
            help="Delete any pre-existing private-sector ApprovalTemplate rows "
                 "(sales order, quotation, vendor/customer invoice) before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **opts) -> None:
        created_groups = self._seed_groups()
        self._seed_global_settings()
        if opts.get("purge_private"):
            self._purge_private_sector_templates()
        created_templates = self._seed_templates(created_groups)

        self.stdout.write(self.style.SUCCESS(
            f"Public-sector approval seed complete — "
            f"{len(created_groups)} groups tracked, "
            f"{created_templates} templates ensured."
        ))

    # ── Groups ──────────────────────────────────────────────────────────────
    def _seed_groups(self) -> dict[str, ApprovalGroup]:
        out: dict[str, ApprovalGroup] = {}
        for slug, spec in PUBLIC_SECTOR_GROUPS.items():
            group, created = ApprovalGroup.objects.get_or_create(
                name=spec["name"],
                organization=None,  # global groups; tenants can clone/scope per MDA
                defaults={
                    "description": spec["description"],
                    "is_active": True,
                },
            )
            if not created and group.description != spec["description"]:
                group.description = spec["description"]
                group.save(update_fields=["description"])
            out[slug] = group
            self.stdout.write(
                f"  {'[+]' if created else '[=]'} group: {group.name}"
            )
        return out

    # ── Global settings ─────────────────────────────────────────────────────
    def _seed_global_settings(self) -> None:
        for module, cfg in MODULE_SETTINGS.items():
            obj, created = GlobalApprovalSettings.objects.get_or_create(
                module=module,
                defaults={
                    "approval_mode": cfg["mode"],
                    "use_amount_threshold": True,
                    "low_amount_threshold": Decimal(cfg["low"]),
                    "high_amount_threshold": Decimal(cfg["high"]),
                    "auto_approve_below_threshold": False,  # public-sector: never auto-skip
                    "send_notifications": True,
                    "notify_requester": True,
                },
            )
            self.stdout.write(
                f"  {'[+]' if created else '[=]'} settings: {obj.module} ({obj.approval_mode})"
            )

    # ── Private-sector purge ────────────────────────────────────────────────
    def _purge_private_sector_templates(self) -> None:
        private_models = ("salesorder", "quotation", "vendorinvoice", "customerinvoice")
        qs = ApprovalTemplate.objects.filter(content_type__model__in=private_models)
        count = qs.count()
        if count:
            qs.delete()
            self.stdout.write(self.style.WARNING(
                f"  [-] purged {count} private-sector approval template(s)"
            ))

    # ── Templates ──────────────────────────────────────────────────────────
    def _seed_templates(self, groups: dict[str, ApprovalGroup]) -> int:
        ensured = 0
        for spec in TEMPLATES:
            ct = ContentType.objects.filter(model=spec.model).first()
            if not ct:
                self.stdout.write(self.style.WARNING(
                    f"  [!] skip {spec.name}: ContentType '{spec.model}' not found"
                ))
                continue

            tmpl, created = ApprovalTemplate.objects.get_or_create(
                name=spec.name,
                content_type=ct,
                organization=None,
                defaults={
                    "description": spec.description,
                    "approval_type": spec.approval_type,
                    "is_active": True,
                },
            )
            if not created:
                # Re-sync description + approval_type so edits to this seed propagate.
                tmpl.description = spec.description
                tmpl.approval_type = spec.approval_type
                tmpl.is_active = True
                tmpl.save(update_fields=["description", "approval_type", "is_active"])
                # Rebuild the steps so amount bands stay in sync with the seed.
                ApprovalTemplateStep.objects.filter(template=tmpl).delete()

            for step in spec.steps:
                group = groups[step.group_slug]
                # NB: amount bands are intentionally left on the group at null so
                # the same group can be reused across Standard and Oversight
                # templates. The template *description* communicates the band
                # admins should match against; auto_route_approval() will fall
                # back to the first active template for the content_type.
                ApprovalTemplateStep.objects.create(
                    template=tmpl,
                    group=group,
                    sequence=step.sequence,
                )

            ensured += 1
            self.stdout.write(
                f"  {'[+]' if created else '[~]'} template: {spec.name} "
                f"({spec.model}, {len(spec.steps)} steps)"
            )
        return ensured
