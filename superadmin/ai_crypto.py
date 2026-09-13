"""
Encryption for AI provider credentials.

Why not reuse ``superadmin/encryption.py``
------------------------------------------
That module derives its Fernet key from ``SHA-256(settings.SECRET_KEY)``.
For the handful of SMTP passwords it holds that is adequate. For a wallet
of live Anthropic / OpenAI / Gemini / OpenRouter keys it is not, because
**rotating SECRET_KEY renders every stored credential undecryptable** —
and rotating SECRET_KEY is exactly what you must do after a leak, which
is exactly when you can least afford to also lose every provider key.

So AI credentials get their own key, on the pattern ``snapshots`` already
uses (``SNAPSHOTS_KEK_HEX``): a dedicated 32-byte KEK supplied by the
deployment, independent of SECRET_KEY.

Versioned envelopes
-------------------
Stored values carry their key version::

    aiv1:<fernet token>

A version prefix costs nothing today and is what makes rotation possible
later: ``AI_KEK_HEX`` holds the current key, ``AI_KEK_HEX_OLD`` may hold
the previous one, and :func:`decrypt_ai_secret` tries current-then-old.
Re-wrapping is then a management command that reads with either and
writes with the current — rather than a migration nobody can run because
the old key is gone.

Failure mode
------------
No key configured is a hard error at *use*, never a silent fallback to
plaintext. A credential store that quietly stops encrypting is worse than
one that refuses to start: the first is discovered by an attacker, the
second by an operator.
"""
from __future__ import annotations

import base64
import binascii

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

#: Envelope prefix. Bump when the key derivation changes, not when a key
#: is rotated — rotation is handled by AI_KEK_HEX / AI_KEK_HEX_OLD.
CURRENT_VERSION = "aiv1"

_PREFIX = f"{CURRENT_VERSION}:"

#: A KEK is 32 bytes, written as 64 hex characters.
_KEK_BYTES = 32


class AIKeyNotConfigured(ImproperlyConfigured):
    """Raised when AI_KEK_HEX is missing or malformed at point of use."""


def _fernet_from_hex(raw: str | None, *, setting_name: str) -> Fernet | None:
    """Build a Fernet from a 64-char hex KEK, or None when unset."""
    if not raw:
        return None
    value = raw.strip()
    try:
        key_bytes = binascii.unhexlify(value)
    except (binascii.Error, ValueError) as exc:
        raise AIKeyNotConfigured(
            f"{setting_name} must be {_KEK_BYTES * 2} hexadecimal characters "
            f"({_KEK_BYTES} bytes); it is not valid hex."
        ) from exc
    if len(key_bytes) != _KEK_BYTES:
        raise AIKeyNotConfigured(
            f"{setting_name} must decode to exactly {_KEK_BYTES} bytes; "
            f"got {len(key_bytes)}."
        )
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def _current() -> Fernet:
    fernet = _fernet_from_hex(
        getattr(settings, "AI_KEK_HEX", None), setting_name="AI_KEK_HEX"
    )
    if fernet is None:
        raise AIKeyNotConfigured(
            "AI_KEK_HEX is not set, so AI provider credentials cannot be "
            "stored or read. Set it to a 64-character hex string (32 bytes). "
            "It is deliberately separate from SECRET_KEY so that rotating "
            "SECRET_KEY does not invalidate every provider key."
        )
    return fernet


def _previous() -> Fernet | None:
    return _fernet_from_hex(
        getattr(settings, "AI_KEK_HEX_OLD", None), setting_name="AI_KEK_HEX_OLD"
    )


def encrypt_ai_secret(plaintext: str) -> str:
    """Return ``aiv1:<token>``. Empty input is returned unchanged.

    An empty string means "no credential set", which is a legitimate state
    for a provider row that has been created but not yet configured.
    Encrypting it would turn "unset" into a value that looks set.
    """
    if not plaintext:
        return plaintext
    token = _current().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{_PREFIX}{token}"


def decrypt_ai_secret(stored: str) -> str:
    """Reverse :func:`encrypt_ai_secret`, trying the previous key too.

    Accepting the old key is what makes rotation a background task rather
    than an outage: deploy the new key alongside the old, re-wrap at
    leisure, then drop the old one.
    """
    if not stored:
        return stored
    if not stored.startswith(_PREFIX):
        raise InvalidToken(
            "Value is not an AI credential envelope. Expected a "
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
    """Render a credential for display: ``...a1b2``.

    Provider keys have to be shown *somehow* in an admin UI so an operator
    can tell which key is loaded. Showing the last few characters
    identifies it without disclosing it; showing the first characters
    would leak the provider's key prefix, which is the part that is
    guessable anyway and the part that identifies the account.
    """
    if not plaintext:
        return ""
    if len(plaintext) <= keep:
        return "*" * len(plaintext)
    return f"...{plaintext[-keep:]}"
