"""
Encryption for payment-gateway credentials (Remita / Xpresspay …).

This is the sibling of :mod:`superadmin.ai_crypto` and follows the same
reasoning: a wallet of live PSP merchant secrets and API keys must not be
tied to ``SECRET_KEY``, because **rotating SECRET_KEY after a leak would
render every gateway credential undecryptable** — precisely when you can
least afford to also lose the ability to disburse or reconcile money.

So gateway credentials get their own 32-byte KEK supplied by the
deployment (``GATEWAY_KEK_HEX``), independent of SECRET_KEY, exactly like
``AI_KEK_HEX`` and ``SNAPSHOTS_KEK_HEX``.

Versioned envelopes
-------------------
Stored values carry their key version::

    gwv1:<fernet token>

``GATEWAY_KEK_HEX`` holds the current key, ``GATEWAY_KEK_HEX_OLD`` may hold
the previous one, and :func:`decrypt_gateway_secret` tries current-then-old
so rotation is a background re-wrap rather than an outage.

Failure mode
------------
No key configured is a hard error at *use*, never a silent fallback to
plaintext. A credential store that quietly stops encrypting is worse than
one that refuses to start.
"""
from __future__ import annotations

import base64
import binascii

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

#: Envelope prefix. Bump when the key derivation changes, not when a key is
#: rotated — rotation is handled by GATEWAY_KEK_HEX / GATEWAY_KEK_HEX_OLD.
CURRENT_VERSION = "gwv1"

_PREFIX = f"{CURRENT_VERSION}:"

#: A KEK is 32 bytes, written as 64 hex characters.
_KEK_BYTES = 32


class GatewayKeyNotConfigured(ImproperlyConfigured):
    """Raised when GATEWAY_KEK_HEX is missing or malformed at point of use."""


def _fernet_from_hex(raw: str | None, *, setting_name: str) -> Fernet | None:
    """Build a Fernet from a 64-char hex KEK, or None when unset."""
    if not raw:
        return None
    value = raw.strip()
    try:
        key_bytes = binascii.unhexlify(value)
    except (binascii.Error, ValueError) as exc:
        raise GatewayKeyNotConfigured(
            f"{setting_name} must be {_KEK_BYTES * 2} hexadecimal characters "
            f"({_KEK_BYTES} bytes); it is not valid hex."
        ) from exc
    if len(key_bytes) != _KEK_BYTES:
        raise GatewayKeyNotConfigured(
            f"{setting_name} must decode to exactly {_KEK_BYTES} bytes; "
            f"got {len(key_bytes)}."
        )
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def _current() -> Fernet:
    fernet = _fernet_from_hex(
        getattr(settings, "GATEWAY_KEK_HEX", None), setting_name="GATEWAY_KEK_HEX"
    )
    if fernet is None:
        raise GatewayKeyNotConfigured(
            "GATEWAY_KEK_HEX is not set, so payment-gateway credentials "
            "cannot be stored or read. Set it to a 64-character hex string "
            "(32 bytes). It is deliberately separate from SECRET_KEY so that "
            "rotating SECRET_KEY does not invalidate every gateway secret."
        )
    return fernet


def _previous() -> Fernet | None:
    return _fernet_from_hex(
        getattr(settings, "GATEWAY_KEK_HEX_OLD", None),
        setting_name="GATEWAY_KEK_HEX_OLD",
    )


def encrypt_gateway_secret(plaintext: str) -> str:
    """Return ``gwv1:<token>``. Empty input is returned unchanged.

    An empty string means "no credential set", a legitimate state for a
    gateway row created but not yet configured. Encrypting it would turn
    "unset" into a value that looks set.
    """
    if not plaintext:
        return plaintext
    token = _current().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{_PREFIX}{token}"


def decrypt_gateway_secret(stored: str) -> str:
    """Reverse :func:`encrypt_gateway_secret`, trying the previous key too."""
    if not stored:
        return stored
    if not stored.startswith(_PREFIX):
        raise InvalidToken(
            "Value is not a gateway credential envelope. Expected a "
            f"{CURRENT_VERSION!r} prefix; refusing to guess at its format."
        )
    token = stored[len(_PREFIX):].encode("ascii")

    try:
        return _current().decrypt(token).decode("utf-8")
    except InvalidToken:
        previous = _previous()
        if previous is None:
            raise
        # Written under the prior KEK and not yet re-wrapped.
        return previous.decrypt(token).decode("utf-8")


def is_encrypted(value: str) -> bool:
    """True when ``value`` is already an envelope this module wrote."""
    return bool(value) and value.startswith(_PREFIX)


def mask(plaintext: str, *, keep: int = 4) -> str:
    """Render a credential for display: ``...a1b2`` (tail only).

    Shows the last few characters so an operator can tell which key is
    loaded, without disclosing it; the leading characters would leak the
    key's account-identifying prefix.
    """
    if not plaintext:
        return ""
    if len(plaintext) <= keep:
        return "*" * len(plaintext)
    return f"...{plaintext[-keep:]}"
