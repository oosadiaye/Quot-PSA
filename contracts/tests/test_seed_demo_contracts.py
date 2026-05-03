"""
Structural (no-DB) tests for ``contracts.management.commands.seed_demo_contracts``.

These tests freeze the public shape of the seed command:

  * ``_TAG`` is stable — changing it silently orphans previously-seeded
    contract rows under ``--clear``.
  * ``_CONTRACT_SPECS`` has exactly 3 entries with the documented Delta
    State contract numbers.
  * The money amounts and mobilization / retention rates match what the
    D8 training fixture promises stakeholders.
  * Activation flags line up with the documented status outcome
    (two ACTIVATED, one DRAFT).

DB-backed integration coverage lives alongside the other contracts
integration suite and is exercised via ``tenant_command`` invocation
in the smoke workflow, not here.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal


class TestTagConstant:

    def test_tag(self):
        from contracts.management.commands import seed_demo_contracts
        assert seed_demo_contracts._TAG == "DEMO-CON"


class TestSpecsShape:

    def test_exactly_three_specs(self):
        from contracts.management.commands.seed_demo_contracts import _CONTRACT_SPECS
        assert len(_CONTRACT_SPECS) == 3

    def test_contract_numbers(self):
        from contracts.management.commands.seed_demo_contracts import _CONTRACT_SPECS
        numbers = [s["contract_number"] for s in _CONTRACT_SPECS]
        assert numbers == [
            "DSG/WORKS/2026/001",
            "DSG/CONSULTANCY/2026/002",
            "DSG/GOODS/2026/003",
        ]

    def test_contract_numbers_unique(self):
        from contracts.management.commands.seed_demo_contracts import _CONTRACT_SPECS
        numbers = [s["contract_number"] for s in _CONTRACT_SPECS]
        assert len(numbers) == len(set(numbers))

    def test_required_keys_present(self):
        from contracts.management.commands.seed_demo_contracts import _CONTRACT_SPECS
        required = {
            "contract_number", "title", "contract_type", "procurement_method",
            "mda_name", "vendor_code", "vendor_name",
            "original_sum", "mobilization_rate", "retention_rate",
            "bpp_no_objection_ref", "due_process_certificate",
            "signed_date", "contract_start_date", "contract_end_date",
            "activate", "description",
        }
        for spec in _CONTRACT_SPECS:
            missing = required - set(spec.keys())
            assert not missing, f"{spec['contract_number']} missing {missing}"


class TestFinancialAmounts:

    def test_total_ceiling_matches_fixture(self):
        """All three contracts sum to ₦615M — the headline figure in
        training materials. Lock it so an accidental edit can't drift."""
        from contracts.management.commands.seed_demo_contracts import _CONTRACT_SPECS
        total = sum((s["original_sum"] for s in _CONTRACT_SPECS), Decimal("0"))
        assert total == Decimal("615000000.00")

    def test_mobilization_rate_within_legal_cap(self):
        """Contract model CheckConstraint enforces 0..30 %. Any spec that
        violates would fail at save() with IntegrityError — catch here
        before hitting the DB."""
        from contracts.management.commands.seed_demo_contracts import _CONTRACT_SPECS
        for spec in _CONTRACT_SPECS:
            rate = spec["mobilization_rate"]
            assert Decimal("0") <= rate <= Decimal("30"), spec["contract_number"]

    def test_retention_rate_within_legal_cap(self):
        from contracts.management.commands.seed_demo_contracts import _CONTRACT_SPECS
        for spec in _CONTRACT_SPECS:
            rate = spec["retention_rate"]
            assert Decimal("0") <= rate <= Decimal("20"), spec["contract_number"]

    def test_original_sum_positive(self):
        """Contract model CheckConstraint: original_sum > 0."""
        from contracts.management.commands.seed_demo_contracts import _CONTRACT_SPECS
        for spec in _CONTRACT_SPECS:
            assert spec["original_sum"] > Decimal("0"), spec["contract_number"]


class TestActivationSchedule:

    def test_two_activated_one_draft(self):
        """Training deck says: two activated (works + consultancy), one
        DRAFT (goods — awaiting BPP no-objection). Lock it."""
        from contracts.management.commands.seed_demo_contracts import _CONTRACT_SPECS
        activated = [s for s in _CONTRACT_SPECS if s["activate"]]
        drafts = [s for s in _CONTRACT_SPECS if not s["activate"]]
        assert len(activated) == 2
        assert len(drafts) == 1

    def test_draft_has_no_bpp_ref(self):
        """The DRAFT contract is DRAFT *because* its BPP ref is empty —
        activation service requires signed_date/start/end which are also
        blank on the DRAFT spec. Both signals must agree."""
        from contracts.management.commands.seed_demo_contracts import _CONTRACT_SPECS
        drafts = [s for s in _CONTRACT_SPECS if not s["activate"]]
        assert len(drafts) == 1
        draft = drafts[0]
        assert draft["bpp_no_objection_ref"] == ""
        assert draft["signed_date"] is None
        assert draft["contract_start_date"] is None
        assert draft["contract_end_date"] is None

    def test_activated_have_required_activation_fields(self):
        """Activation service raises ValidationError if signed_date /
        contract_start_date / contract_end_date are missing. Make sure
        each activated spec has them populated."""
        from contracts.management.commands.seed_demo_contracts import _CONTRACT_SPECS
        for spec in _CONTRACT_SPECS:
            if not spec["activate"]:
                continue
            assert isinstance(spec["signed_date"], date), spec["contract_number"]
            assert isinstance(spec["contract_start_date"], date), spec["contract_number"]
            assert isinstance(spec["contract_end_date"], date), spec["contract_number"]
            assert spec["contract_start_date"] <= spec["contract_end_date"], spec["contract_number"]


class TestContractTypeCoverage:
    """The demo fixture is meant to showcase every contract_type the
    module handles. Lock the coverage so a future edit doesn't collapse
    the demo to just WORKS."""

    def test_types_cover_works_goods_consultancy(self):
        from contracts.management.commands.seed_demo_contracts import _CONTRACT_SPECS
        types = {s["contract_type"] for s in _CONTRACT_SPECS}
        assert types == {"WORKS", "CONSULTANCY", "GOODS"}


class TestCommandSurface:
    """The public CLI flags --clear and --dry-run must not regress — any
    runbook or training script that invokes the command relies on them."""

    def test_command_class_has_help(self):
        from contracts.management.commands.seed_demo_contracts import Command
        assert Command.help
        assert "Delta" in Command.help or "contract" in Command.help.lower()

    def test_command_declares_clear_and_dry_run(self):
        import argparse
        from contracts.management.commands.seed_demo_contracts import Command
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        flags = {action.dest for action in parser._actions}
        assert "clear" in flags
        assert "dry_run" in flags
