"""
Structured exceptions for the contracts service layer.

Each class corresponds to one of the 10 structural overpayment-prevention
controls.  API handlers catch the common base class and map to an
appropriate HTTP 4xx response; internal code can catch the specific
subclass to react to one particular violation.
"""
from __future__ import annotations


class ContractServiceError(Exception):
    """Base class for all contract-service errors."""

    code: str = "CONTRACT_SERVICE_ERROR"

    def __init__(self, message: str, *, context: dict | None = None) -> None:
        super().__init__(message)
        self.context = context or {}

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": str(self),
            "context": self.context,
        }


# ── 1. Ceiling ────────────────────────────────────────────────────────
class CeilingBreachError(ContractServiceError):
    """Raised when a new IPC / variation would push the cumulative
    certified or committed amount over the contract ceiling."""

    code = "CONTRACT_CEILING_BREACH"


# ── 2. Progress-payment coherence ─────────────────────────────────────
class CoherenceError(ContractServiceError):
    """Raised when net payable on a single IPC does not reconcile with
    cumulative gross − prior deductions."""

    code = "CONTRACT_COHERENCE_ERROR"


# ── 3. Cumulative monotonicity ────────────────────────────────────────
class MonotonicityError(ContractServiceError):
    """Raised when an IPC's cumulative_work_done_to_date is less than
    the previous IPC's value (work-done can't go backwards)."""

    code = "CONTRACT_MONOTONICITY_ERROR"


# ── 4. Mobilization recovery ──────────────────────────────────────────
class MobilizationRecoveryError(ContractServiceError):
    """Raised when proposed mobilization recovery on an IPC is wrong
    (too little would understate recovery, too much would over-recover)."""

    code = "CONTRACT_MOBILIZATION_RECOVERY_ERROR"


# ── 5. Retention cap ──────────────────────────────────────────────────
class RetentionCapError(ContractServiceError):
    """Raised when retention_held would exceed retention_rate% of the
    cumulative certified value, or when a release would exceed held."""

    code = "CONTRACT_RETENTION_CAP_ERROR"


# ── 6. Variation approval tier ────────────────────────────────────────
class VariationApprovalError(ContractServiceError):
    """Raised when a variation is being approved without the required
    authority for its tier (LOCAL / BOARD / BPP_REQUIRED)."""

    code = "CONTRACT_VARIATION_APPROVAL_ERROR"


# ── 7. Duplicate IPC ──────────────────────────────────────────────────
class DuplicateIPCError(ContractServiceError):
    """Raised when an IPC's integrity_hash collides with an existing
    non-rejected IPC (potential double-payment attack)."""

    code = "CONTRACT_DUPLICATE_IPC"


# ── 8. Fiscal-year boundary ───────────────────────────────────────────
class FiscalYearBoundaryError(ContractServiceError):
    """Raised when an IPC spans or falls outside the contract's fiscal
    year in a way that would break IPSAS accrual recognition."""

    code = "CONTRACT_FISCAL_YEAR_BOUNDARY"


# ── 9. Three-way match ────────────────────────────────────────────────
class ThreeWayMatchError(ContractServiceError):
    """Raised when IPC, MeasurementBook and PaymentVoucher values don't
    reconcile at voucher generation time."""

    code = "CONTRACT_THREE_WAY_MATCH_ERROR"


# ── 10. Segregation of Duties ─────────────────────────────────────────
class SegregationOfDutiesError(ContractServiceError):
    """Raised when the same user is trying to take two incompatible
    roles on the same document (e.g. submitter == approver)."""

    code = "CONTRACT_SOD_VIOLATION"


# ── Generic state/workflow errors ─────────────────────────────────────
class InvalidTransitionError(ContractServiceError):
    code = "CONTRACT_INVALID_TRANSITION"


class ConcurrencyError(ContractServiceError):
    """Raised when optimistic locking fails — client should retry."""

    code = "CONTRACT_CONCURRENCY_CONFLICT"
