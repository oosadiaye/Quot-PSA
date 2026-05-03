"""Centralised error formatter for every posting endpoint.

Every posting path (journal, AP invoice, PV, PO approve, asset
acquisition, payroll post) can raise one of a handful of exception
types — DRF ValidationError, Django core ValidationError, the budget
services' ``BudgetExceededError``, or a generic exception. The
frontend wants ONE consistent response shape so a toast / error
banner always knows where to look:

    {
        "error":   "<human-readable headline>",
        "detail":  "<long explanation>",
        "code":    "<stable machine code the UI can switch on>",
        "errors":  {...structured field-level errors (DRF convention)...},
        "budget_violations": [...when the block came from BudgetCheckRule...],
    }

``code`` values the UI can map to icons / colours:
  * ``BUDGET_NO_APPROPRIATION``  — no Appropriation for this (MDA,Econ,Fund)
  * ``BUDGET_STRICT_BLOCK``       — STRICT rule blocked the post
  * ``BUDGET_BALANCE_EXCEEDED``   — would exceed available_balance
  * ``BUDGET_WARRANT_EXCEEDED``   — would exceed released warrant ceiling
  * ``PERIOD_CLOSED``             — fiscal period is closed / locked
  * ``VALIDATION``                — generic serializer validation error
  * ``DUPLICATE``                 — unique-constraint clash
  * ``INTERNAL``                  — catch-all, str(exception)
"""
from __future__ import annotations

import re
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError


def _stringify_detail(detail: Any) -> str:
    """Best-effort convert DRF/Django error detail into a plain string."""
    if detail is None:
        return ''
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        return '; '.join(_stringify_detail(d) for d in detail if d)
    if isinstance(detail, dict):
        parts = []
        for k, v in detail.items():
            if k in ('budget_violations', 'existing_appropriation_id'):
                continue
            sv = _stringify_detail(v)
            parts.append(f'{k}: {sv}' if k != 'non_field_errors' else sv)
        return '; '.join(p for p in parts if p)
    return str(detail)


def _classify_message(message: str) -> str:
    """Heuristic to attach a machine code to an otherwise plain message.

    Order matters: more specific phrases beat more generic ones so an
    "exceeds appropriation balance" message inside a STRICT reason
    lands on BALANCE_EXCEEDED (which triggers the "raise virement" UI
    hint) instead of the generic STRICT_BLOCK.
    """
    m = message.lower()
    if 'no active appropriation' in m or 'no appropriation' in m:
        return 'BUDGET_NO_APPROPRIATION'
    # Warrant ceiling check BEFORE the generic balance / STRICT checks
    if 'warrant ceiling' in m or ('warrant' in m and 'exceed' in m):
        return 'BUDGET_WARRANT_EXCEEDED'
    # Balance checks BEFORE the STRICT catch-all — "exceeds appropriation
    # available balance" is more specific than "strict budget control".
    if 'insufficient appropriation balance' in m or 'exceeds appropriation' in m:
        return 'BUDGET_BALANCE_EXCEEDED'
    if 'strict budget control' in m:
        return 'BUDGET_STRICT_BLOCK'
    if 'period' in m and ('closed' in m or 'locked' in m):
        return 'PERIOD_CLOSED'
    if 'duplicate' in m or 'unique constraint' in m or 'already exists' in m:
        return 'DUPLICATE'
    return 'VALIDATION'


def format_post_error(exc: Exception, context: str = 'transaction') -> dict:
    """Produce the standard error envelope for posting-path failures.

    ``context`` is a user-facing label ('journal entry', 'AP invoice',
    'payment voucher', 'purchase order', etc.) woven into the headline.
    """
    # 1) BudgetExceededError — always a clear, user-facing message.
    try:
        from budget.services import BudgetExceededError
    except Exception:  # pragma: no cover — budget app always importable
        BudgetExceededError = ()  # type: ignore

    if isinstance(exc, BudgetExceededError):
        msg = str(exc)
        return {
            'error':  f'Cannot post {context}: budget check failed.',
            'detail': msg,
            'code':   _classify_message(msg),
        }

    # 2) DRF ValidationError — preserve structured payloads
    if isinstance(exc, DRFValidationError):
        detail = exc.detail
        payload: dict = {
            'error':  f'Cannot post {context}: {_validation_headline(detail, context)}',
            'detail': _stringify_detail(detail),
            'code':   _classify_validation(detail),
        }
        if isinstance(detail, dict):
            if 'budget_violations' in detail:
                payload['budget_violations'] = detail['budget_violations']
                payload['code'] = 'BUDGET_STRICT_BLOCK'
            if 'existing_appropriation_id' in detail:
                payload['existing_appropriation_id'] = detail['existing_appropriation_id']
            # Keep field-level errors so the UI can highlight inputs
            payload['errors'] = {
                k: v for k, v in detail.items()
                if k not in ('budget_violations', 'existing_appropriation_id')
            }
        return payload

    # 3) Django core ValidationError — prefer the structured payload we
    # passed into it (message_dict / params) over the flattened
    # ``.messages`` list so headlines come from our own 'message' /
    # 'detail' keys, not from the first value of a nested dict.
    if isinstance(exc, DjangoValidationError):
        payload: dict = {}
        headline = ''
        detail_str = ''
        violations: list = []

        # Django stores the original dict under .message_dict when the
        # ValidationError was constructed with a dict argument.
        msg_dict = getattr(exc, 'message_dict', None)
        if isinstance(msg_dict, dict) and msg_dict:
            # Our own keys take priority; field-name keys are last resort.
            for key in ('message', 'detail'):
                if msg_dict.get(key):
                    v = msg_dict[key]
                    s = v[0] if isinstance(v, list) and v else str(v)
                    if not headline:
                        headline = s
                    if key == 'detail' and not detail_str:
                        detail_str = s
            bv = msg_dict.get('budget_violations')
            if bv:
                # budget_violations may be a list-of-dicts (our own shape)
                # OR Django may have flattened it into list-of-strings.
                # We want the list-of-dicts shape for the UI.
                original = exc.args[0] if exc.args else None
                if isinstance(original, dict) and isinstance(original.get('budget_violations'), list):
                    violations = original['budget_violations']
                else:
                    violations = bv if isinstance(bv, list) else [bv]
            if not headline:
                # Fall back to the first non-budget key's first message
                for k, v in msg_dict.items():
                    if k in ('budget_violations', 'existing_appropriation_id'):
                        continue
                    s = v[0] if isinstance(v, list) and v else str(v)
                    if s:
                        headline = s
                        break

        # If no dict payload, fall back to .messages list
        if not headline:
            msgs = list(getattr(exc, 'messages', []) or [])
            headline = msgs[0] if msgs else str(exc)
            detail_str = '; '.join(msgs) or str(exc)

        if not detail_str:
            detail_str = headline

        payload = {
            'error':  f'Cannot post {context}: {headline}',
            'detail': detail_str,
            'code':   _classify_message(headline + ' ' + detail_str),
        }
        if violations:
            payload['budget_violations'] = violations
            # Re-classify against the first violation's message so
            # "exceeds appropriation balance" → BUDGET_BALANCE_EXCEEDED
            # beats the generic BUDGET_STRICT_BLOCK for overdraw cases.
            first_msg = ''
            if violations and isinstance(violations[0], dict):
                first_msg = str(violations[0].get('message', ''))
            specific = _classify_message(first_msg) if first_msg else 'VALIDATION'
            if specific in (
                'BUDGET_NO_APPROPRIATION', 'BUDGET_BALANCE_EXCEEDED',
                'BUDGET_WARRANT_EXCEEDED',
            ):
                payload['code'] = specific
            else:
                payload['code'] = 'BUDGET_STRICT_BLOCK'
        return payload

    # 4) IntegrityError with a readable cue
    from django.db.utils import IntegrityError
    if isinstance(exc, IntegrityError):
        raw = str(exc)
        friendly = 'A row with the same key already exists.' if 'unique constraint' in raw.lower() else raw
        return {
            'error':  f'Cannot post {context}: data integrity error.',
            'detail': friendly,
            'code':   'DUPLICATE' if 'unique' in raw.lower() else 'INTERNAL',
        }

    # 5) Last-resort fallback — always return SOMETHING for the UI to show
    raw = str(exc).strip() or exc.__class__.__name__
    # Collapse nested DRF-style ErrorDetail spam (ErrorDetail(string='...'))
    cleaned = re.sub(r"ErrorDetail\(string='([^']*)'[^)]*\)", r'\1', raw)
    return {
        'error':  f'Cannot post {context}: an unexpected error occurred.',
        'detail': cleaned,
        'code':   'INTERNAL',
    }


def _validation_headline(detail: Any, context: str) -> str:
    """Pick the most useful human-readable sentence out of a DRF error.

    Priority order (first non-empty wins):
      1. explicit ``message`` field we set when raising
      2. explicit ``detail`` field we set when raising
      3. first ``budget_violations[].message`` (DRF wraps dicts in
         ErrorDetail, so we pull the string out via stringify)
      4. ``non_field_errors`` — standard serializer validation key
      5. any remaining field error (last resort, so field names like
         ``account_code`` don't end up as the headline)
    """
    if isinstance(detail, dict):
        for key in ('message', 'detail'):
            if detail.get(key):
                s = _stringify_detail(detail[key])
                if s:
                    return s
        bv = detail.get('budget_violations')
        if bv:
            # budget_violations may be a list of dicts, or DRF may have
            # wrapped it — stringify it to extract the embedded message.
            s = _stringify_detail(bv)
            if s:
                return s
        if detail.get('non_field_errors'):
            return _stringify_detail(detail['non_field_errors'])
        # Last resort — skip DRF-wrapped metadata keys that aren't
        # real messages so we don't end up with "account_code"
        # as the headline.
        for k, v in detail.items():
            if k in ('budget_violations', 'existing_appropriation_id'):
                continue
            s = _stringify_detail(v)
            if s:
                return s
    if isinstance(detail, list) and detail:
        return _stringify_detail(detail[0])
    return _stringify_detail(detail) or 'validation failed'


def _classify_validation(detail: Any) -> str:
    if isinstance(detail, dict) and detail.get('budget_violations'):
        return 'BUDGET_STRICT_BLOCK'
    return _classify_message(_stringify_detail(detail))
