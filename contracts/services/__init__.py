"""
contracts.services — public service-layer re-exports.

The service layer is the ONLY place where state-changing business logic
for contracts lives.  API views, Celery tasks, management commands and
tests should always call a service classmethod rather than mutating
model fields directly.
"""
from contracts.services.exceptions import (  # noqa: F401
    CeilingBreachError,
    CoherenceError,
    ConcurrencyError,
    ContractServiceError,
    DuplicateIPCError,
    FiscalYearBoundaryError,
    InvalidTransitionError,
    MobilizationRecoveryError,
    MonotonicityError,
    RetentionCapError,
    SegregationOfDutiesError,
    ThreeWayMatchError,
    VariationApprovalError,
)
from contracts.services.contract_activation import ContractActivationService  # noqa: F401
from contracts.services.contract_closure_service import ContractClosureService  # noqa: F401
from contracts.services.ipc_service import IPCService  # noqa: F401
from contracts.services.mobilization_service import MobilizationService  # noqa: F401
from contracts.services.numbering import (  # noqa: F401
    next_contract_number,
    next_ipc_number,
    next_measurement_book_number,
    next_variation_number,
)
from contracts.services.retention_service import RetentionService  # noqa: F401
from contracts.services.variation_service import VariationService  # noqa: F401

__all__ = [
    # Services
    "ContractActivationService",
    "ContractClosureService",
    "IPCService",
    "MobilizationService",
    "RetentionService",
    "VariationService",
    # Numbering helpers
    "next_contract_number",
    "next_ipc_number",
    "next_measurement_book_number",
    "next_variation_number",
    # Exceptions
    "ContractServiceError",
    "CeilingBreachError",
    "CoherenceError",
    "ConcurrencyError",
    "DuplicateIPCError",
    "FiscalYearBoundaryError",
    "InvalidTransitionError",
    "MobilizationRecoveryError",
    "MonotonicityError",
    "RetentionCapError",
    "SegregationOfDutiesError",
    "ThreeWayMatchError",
    "VariationApprovalError",
]
