"""
Structural tests for the Circular AG/CIR/54/C/Vol.10/1/134 wiring.

Two surfaces are tested here without a DB:

1. ``VendorStatusVerification`` model metadata — unique constraint on
   (vendor, year) + non-negative fee CheckConstraint. These are what
   make the model safe to call with ``get_or_create`` idempotently.

2. ``IPCService.deductions_for_ipc`` surface — method exists, is a
   classmethod, and accepts an IPC argument. The computation layer
   itself is covered by ``accounting/tests/test_contract_deductions.py``;
   here we just freeze the integration point.
"""
from __future__ import annotations

import inspect


# ── Model metadata ────────────────────────────────────────────────────

class TestVendorStatusVerificationMeta:

    def test_model_importable(self):
        from contracts.models import VendorStatusVerification
        assert VendorStatusVerification.__name__ == "VendorStatusVerification"

    def test_unique_vendor_year_constraint(self):
        """Guarantees the (vendor, year) idempotency key we rely on in
        ``IPCService.record_status_verification_paid``."""
        from contracts.models import VendorStatusVerification
        names = [c.name for c in VendorStatusVerification._meta.constraints]
        assert "contracts_vendorsv_unique_per_vendor_year" in names

    def test_non_negative_fee_constraint(self):
        from contracts.models import VendorStatusVerification
        names = [c.name for c in VendorStatusVerification._meta.constraints]
        assert "contracts_vendorsv_fee_non_negative" in names

    def test_default_fee_matches_circular(self):
        from decimal import Decimal
        from contracts.models import VendorStatusVerification
        field = VendorStatusVerification._meta.get_field("fee_amount")
        assert field.default == Decimal("40000.00")

    def test_circular_reference_default(self):
        from contracts.models import VendorStatusVerification
        field = VendorStatusVerification._meta.get_field("circular_reference")
        assert field.default == "AG/CIR/54/C/Vol.10/1/134"


# ── IPCService surface ────────────────────────────────────────────────

class TestIPCServiceDeductionsSurface:

    def test_deductions_for_ipc_is_classmethod(self):
        from contracts.services.ipc_service import IPCService
        method = inspect.getattr_static(IPCService, "deductions_for_ipc")
        assert isinstance(method, classmethod)

    def test_deductions_for_ipc_accepts_ipc_argument(self):
        from contracts.services.ipc_service import IPCService
        sig = inspect.signature(IPCService.deductions_for_ipc)
        # classmethod signature drops cls — first parameter is the IPC.
        params = list(sig.parameters.keys())
        assert params == ["ipc"]

    def test_record_status_verification_is_classmethod(self):
        from contracts.services.ipc_service import IPCService
        method = inspect.getattr_static(
            IPCService, "record_status_verification_paid",
        )
        assert isinstance(method, classmethod)

    def test_record_status_verification_required_kwargs(self):
        """Must accept vendor_id, year, payment_voucher_id, actor as
        keyword-only — catches accidental signature drift."""
        from contracts.services.ipc_service import IPCService
        sig = inspect.signature(IPCService.record_status_verification_paid)
        params = sig.parameters
        for name in ("vendor_id", "year", "payment_voucher_id", "actor"):
            assert name in params, name
            assert params[name].kind == inspect.Parameter.KEYWORD_ONLY, name


# ── Migration presence ────────────────────────────────────────────────

class TestMigrationPresence:
    """The deductions model requires migration 0003. Lock its filename
    so a rename that breaks production migration ordering is caught."""

    def test_migration_file_exists(self):
        import pathlib
        p = pathlib.Path(__file__).parent.parent / "migrations" / "0003_vendor_status_verification.py"
        assert p.exists(), f"Expected migration at {p}"
