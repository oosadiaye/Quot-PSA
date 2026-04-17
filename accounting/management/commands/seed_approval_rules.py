"""
Seed baseline ApprovalRule + ApprovalLevel rows tying the six baseline
roles to the approval engine.

Binds the officer → manager workflow for every document type the
engine currently recognises:

    Document            Amount gate        Approver role
    ─────────────────── ───────────────── ──────────────────────
    Journal Entry (JE)  ≥ 0                accountant_general
    Vendor Invoice (VI) 0 – 5 M            procurement_manager
    Vendor Invoice (VI) > 5 M              procurement_manager  (level 1)
                                            + accountant_general (level 2)
    Customer Invoice    ≥ 0                accountant_general
    Payment             0 – 1 M            accountant_general
    Payment             > 1 M              accountant_general  (level 1)
                                            + accountant_general (level 2 — 2 approvers)
    Budget Amendment    ≥ 0                budget_manager
    Budget Transfer     ≥ 0                budget_manager

Usage
-----
    python manage.py tenant_command seed_approval_rules --schema=<name>
    python manage.py tenant_command seed_approval_rules --schema=<name> --clear

Idempotent: matches by (document_type, min_amount, max_amount). Rerunning
without ``--clear`` is safe.
"""
from __future__ import annotations

from decimal import Decimal
from django.core.management.base import BaseCommand


# ---------------------------------------------------------------------------
# Rule matrix. Each entry produces one ApprovalRule + N ApprovalLevel rows.
# ---------------------------------------------------------------------------
RULES: list[dict] = [
    # Journal Entry — always routed to Accountant General.
    {
        'document_type': 'JE',
        'min_amount':    Decimal('0'),
        'max_amount':    None,
        'levels': [
            {'level': 1, 'role_code': 'accountant_general', 'min_approvers': 1},
        ],
    },

    # Vendor Invoice — procurement approves <=5 M; above that requires
    # Accountant General co-sign.
    {
        'document_type': 'VI',
        'min_amount':    Decimal('0'),
        'max_amount':    Decimal('5000000'),
        'levels': [
            {'level': 1, 'role_code': 'procurement_manager', 'min_approvers': 1},
        ],
    },
    {
        'document_type': 'VI',
        'min_amount':    Decimal('5000000.01'),
        'max_amount':    None,
        'levels': [
            {'level': 1, 'role_code': 'procurement_manager', 'min_approvers': 1},
            {'level': 2, 'role_code': 'accountant_general',  'min_approvers': 1},
        ],
    },

    # Customer Invoice — Accountant General single-level.
    {
        'document_type': 'CI',
        'min_amount':    Decimal('0'),
        'max_amount':    None,
        'levels': [
            {'level': 1, 'role_code': 'accountant_general', 'min_approvers': 1},
        ],
    },

    # Payment — single approver under NGN 1 M; two approvers above that.
    {
        'document_type': 'PAY',
        'min_amount':    Decimal('0'),
        'max_amount':    Decimal('1000000'),
        'levels': [
            {'level': 1, 'role_code': 'accountant_general', 'min_approvers': 1},
        ],
    },
    {
        'document_type': 'PAY',
        'min_amount':    Decimal('1000000.01'),
        'max_amount':    None,
        'levels': [
            {'level': 1, 'role_code': 'accountant_general', 'min_approvers': 1},
            {'level': 2, 'role_code': 'accountant_general', 'min_approvers': 1},
        ],
    },

    # Budget Amendment — always Budget & Appropriation Manager.
    {
        'document_type': 'BGT',
        'min_amount':    Decimal('0'),
        'max_amount':    None,
        'levels': [
            {'level': 1, 'role_code': 'budget_manager', 'min_approvers': 1},
        ],
    },

    # Budget Transfer / virement — Budget Manager plus threshold escalation
    # to Accountant General for large transfers.
    {
        'document_type': 'TRF',
        'min_amount':    Decimal('0'),
        'max_amount':    Decimal('10000000'),
        'levels': [
            {'level': 1, 'role_code': 'budget_manager', 'min_approvers': 1},
        ],
    },
    {
        'document_type': 'TRF',
        'min_amount':    Decimal('10000000.01'),
        'max_amount':    None,
        'levels': [
            {'level': 1, 'role_code': 'budget_manager',     'min_approvers': 1},
            {'level': 2, 'role_code': 'accountant_general', 'min_approvers': 1},
        ],
    },
]


class Command(BaseCommand):
    help = 'Seed baseline ApprovalRule rows wiring roles to document workflows.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear', action='store_true',
            help='Delete all existing ApprovalRule rows before seeding.',
        )

    def handle(self, *args, **options):
        from accounting.models.audit import ApprovalRule, ApprovalLevel

        clear: bool = options['clear']

        if clear:
            existing = ApprovalRule.objects.count()
            # Cascade deletes levels via FK.
            ApprovalRule.objects.all().delete()
            self.stdout.write(self.style.WARNING(
                f'Cleared {existing} existing ApprovalRule rows.'
            ))

        created = updated = 0
        for spec in RULES:
            rule, was_created = ApprovalRule.objects.update_or_create(
                document_type=spec['document_type'],
                min_amount=spec['min_amount'],
                max_amount=spec['max_amount'],
                defaults={
                    'approval_levels':          [],  # use ApprovalLevel FK instead
                    'auto_approve_roles':       [],
                    'skip_approval_if_same_user': False,
                    'require_comment_on_reject': True,
                    'is_active':                True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
                # Rewrite the level list — safer than trying to diff.
                rule.levels.all().delete()

            for lvl_spec in spec['levels']:
                ApprovalLevel.objects.create(
                    rule=rule,
                    level=lvl_spec['level'],
                    approver_type='ROLE',
                    approver_value=lvl_spec['role_code'],
                    min_approvers=lvl_spec['min_approvers'],
                )

            max_str = (
                f'{spec["max_amount"]:,.0f}'
                if spec['max_amount'] is not None
                else '+inf'
            )
            bracket = f'{spec["min_amount"]:,.0f} -> {max_str}'
            level_summary = ' + '.join(
                f'L{lv["level"]}={lv["role_code"]}({lv["min_approvers"]}x)'
                for lv in spec['levels']
            )
            self.stdout.write(
                f'  {"[+]" if was_created else "[~]"} {spec["document_type"]:<4} '
                f'{bracket:<28}  {level_summary}'
            )

        self.stdout.write(self.style.SUCCESS(
            f'ApprovalRule seed — {created} created, {updated} updated, '
            f'{len(RULES)} total rules across {len({r["document_type"] for r in RULES})} document types.'
        ))
