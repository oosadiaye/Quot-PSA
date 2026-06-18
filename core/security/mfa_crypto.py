"""Symmetric encryption helpers for MFA secrets at rest.

The TOTP shared secret used for MFA is high-value: anyone with the
secret can mint valid 6-digit codes for that user. We previously stored
it as a plaintext ``CharField`` on ``UserMFA``; this module wraps it in
Fernet (AES-128-CBC + HMAC) so a database dump alone is no longer
sufficient to bypass MFA.

Key derivation — dual format
----------------------------
Two envelope formats are supported:

* **v1** (legacy): raw Fernet token (starts with ``gAAAAA``). Key is
  ``urlsafe_b64encode(sha256(SECRET_KEY))``. No salt, no KDF cost, no
  domain separation. Kept only for transparent reads of pre-migration
  rows.
* **v2** (current): ``v2:<base64-salt>:<base64-fernet-token>``. Key is
  derived with HKDF-SHA256 from ``SECRET_KEY``, a per-row 16-byte salt,
  and the domain-separation label ``b'mfa-encryption-v1'``. Each row
  gets its own salt, so a SECRET_KEY compromise no longer cracks every
  row in one step.

All **new** writes go through the v2 path. Reads peek at the prefix and
route to the appropriate key derivation. The one-time migration
``core.0015_re_encrypt_mfa_secrets_v2`` rewrites v1 rows as v2.

If/when the deployment wants real key separation, swap the SECRET_KEY
source for a dedicated ``MFA_FERNET_KEY`` env var (or KMS) — the call
sites do not change.
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings


# Envelope format constants.
_V2_PREFIX = 'v2:'
_V2_SALT_BYTES = 16
_V2_INFO = b'mfa-encryption-v1'  # Domain separation label.


def _secret_key_bytes() -> bytes:
    return settings.SECRET_KEY.encode('utf-8')


def _derive_key_v1() -> bytes:
    """Legacy v1 key: ``urlsafe_b64encode(sha256(SECRET_KEY))``.

    Used only for reading pre-v2 rows. Do not use for new writes.
    """
    digest = hashlib.sha256(_secret_key_bytes()).digest()
    return base64.urlsafe_b64encode(digest)


def _derive_key_v2(secret_key: bytes, salt: bytes, info: bytes) -> bytes:
    """HKDF-SHA256 derived 32-byte urlsafe-base64 Fernet key."""
    raw = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=info,
    ).derive(secret_key)
    return base64.urlsafe_b64encode(raw)


def _encrypt_v2(plain: str) -> str:
    """Produce a ``v2:<salt>:<ct>`` envelope with a fresh random salt."""
    salt = os.urandom(_V2_SALT_BYTES)
    key = _derive_key_v2(_secret_key_bytes(), salt, _V2_INFO)
    ciphertext = Fernet(key).encrypt(plain.encode('utf-8'))
    salt_b64 = base64.urlsafe_b64encode(salt).decode('ascii')
    return f'{_V2_PREFIX}{salt_b64}:{ciphertext.decode("ascii")}'


def _decrypt_v2(token: str) -> str:
    """Decrypt a ``v2:<salt>:<ct>`` envelope. Raises ``InvalidToken`` on
    malformed envelopes or tampered ciphertext.
    """
    # Strip the prefix, then split on the *first* colon to isolate salt.
    body = token[len(_V2_PREFIX):]
    salt_b64, _, ct = body.partition(':')
    if not salt_b64 or not ct:
        raise InvalidToken('Malformed v2 envelope')
    try:
        salt = base64.urlsafe_b64decode(salt_b64.encode('ascii'))
    except (ValueError, TypeError) as exc:
        raise InvalidToken('v2 envelope has invalid salt') from exc
    key = _derive_key_v2(_secret_key_bytes(), salt, _V2_INFO)
    plain = Fernet(key).decrypt(ct.encode('ascii'))
    return plain.decode('utf-8')


def _decrypt_v1(token: str) -> str:
    """Decrypt a legacy bare-Fernet token under the v1 SHA-256 key."""
    plain = Fernet(_derive_key_v1()).decrypt(token.encode('utf-8'))
    return plain.decode('utf-8')


def encrypt_secret(plain: str) -> str:
    """Encrypt a plaintext MFA secret. Always returns a v2 envelope."""
    if plain is None:
        plain = ''
    return _encrypt_v2(plain)


def decrypt_secret(token: str) -> str:
    """Decrypt a previously encrypted MFA secret.

    Transparently handles both v2 envelopes (``v2:salt:ct``) and legacy
    v1 raw Fernet tokens (``gAAAAA...``). Raises
    :class:`cryptography.fernet.InvalidToken` on tampering or wrong key.
    """
    if not token:
        return ''
    if token.startswith(_V2_PREFIX):
        return _decrypt_v2(token)
    return _decrypt_v1(token)


__all__ = ['encrypt_secret', 'decrypt_secret', 'InvalidToken']
