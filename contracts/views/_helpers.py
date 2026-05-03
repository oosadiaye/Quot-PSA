"""
Shared view helpers — exception-to-HTTP translation.

The contracts service layer raises structured ``ContractServiceError``
subclasses for every structural-control violation. This helper turns
them into a consistent 400/409 response envelope so the frontend can
show a code-specific toast:

    {
        "code":    "CONTRACT_CEILING_BREACH",
        "message": "Projected committed spend exceeds ceiling.",
        "context": {"projected": "11000000.00", "ceiling": "10000000.00"}
    }
"""
from __future__ import annotations

from contextlib import contextmanager

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from contracts.services.exceptions import (
    ConcurrencyError,
    ContractServiceError,
    InvalidTransitionError,
)


class ContractAPIException(APIException):
    """DRF-native wrapper around a ContractServiceError."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Contract service error."
    default_code = "contract_service_error"

    def __init__(self, err: ContractServiceError, http_status: int = 400) -> None:
        self.status_code = http_status
        super().__init__(detail=err.to_dict(), code=err.code)


def service_error_response(err: Exception) -> Response:
    """Translate an exception into a DRF ``Response``.

    Policy:
      * ``ConcurrencyError``      → 409 (optimistic-lock conflict)
      * ``InvalidTransitionError``→ 409 (state conflict)
      * other ``ContractServiceError`` → 400 (business-rule violation)
      * ``DjangoValidationError`` → 400 (form-level validation)
      * anything else bubbles back to the caller.
    """
    if isinstance(err, ConcurrencyError):
        return Response(err.to_dict(), status=status.HTTP_409_CONFLICT)
    if isinstance(err, InvalidTransitionError):
        return Response(err.to_dict(), status=status.HTTP_409_CONFLICT)
    if isinstance(err, ContractServiceError):
        return Response(err.to_dict(), status=status.HTTP_400_BAD_REQUEST)
    if isinstance(err, DjangoValidationError):
        return Response(
            {
                "code": "VALIDATION_ERROR",
                "message": "Validation failed.",
                "context": {"errors": err.message_dict
                            if hasattr(err, "message_dict") else err.messages},
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    raise err


@contextmanager
def translate_service_errors():
    """Context manager: wrap a service call so any control violation
    becomes a ``ContractAPIException`` that DRF renders as JSON.

    Usage::

        with translate_service_errors():
            ipc = IPCService.submit_ipc(...)
    """
    try:
        yield
    except ConcurrencyError as exc:
        raise ContractAPIException(exc, http_status=status.HTTP_409_CONFLICT) from exc
    except InvalidTransitionError as exc:
        raise ContractAPIException(exc, http_status=status.HTTP_409_CONFLICT) from exc
    except ContractServiceError as exc:
        raise ContractAPIException(exc, http_status=status.HTTP_400_BAD_REQUEST) from exc
