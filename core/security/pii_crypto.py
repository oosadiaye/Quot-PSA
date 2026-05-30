"""Symmetric encryption + HMAC hashing helpers for PII at rest.

HR PII (NIN, TIN, SSN, BVN, bank account/routing) is high-value: a DB
dump alone exposes it. This module wraps each value in Fernet
(AES-128-CBC + HMAC) so backups, replicas, and read replicas are no
longer sufficient to leak it. For fields that still need exact-match
lookup (NIN, TIN, bank_account) we additionally store an HMAC-SHA256
hash keyed off ``SECRET_KEY`` — search by hashing the query value and
filtering on the indexed ``<field>_hash`` column.

This mirrors :mod:`core.security.mfa_crypto`: same dual-format envelope,
same dependency surface, same rotation story. If/when the deployment
wants true key separation, swap the SECRET_KEY source for a dedicated
env var or KMS-backed key — call sites do not change.

Envelope format — dual read
---------------------------
* **v1** (legacy): raw Fernet token (starts with ``gAAAAA``). Key derived
  via ``urlsafe_b64encode(sha256(SECRET_KEY))``. Read-only.
* **v2** (current): ``v2:<base64-salt>:<base64-fernet-token>``. Key
  derived via HKDF-SHA256 over (SECRET_KEY, per-row salt, info=
  ``b'pii-encryption-v1'``). All new writes use v2; the
  ``hrm.0020_re_encrypt_pii_v2`` migration rewrites v1 rows in place.

Notes
-----
* Salary is **not** encrypted (carve-out): it needs to be queryable for
  payroll computation, budget vs actuals, and headcount reporting. It
  stays masked at the serializer layer instead.
* :func:`pii_hash` lowercases + strips its input so ``'AB-123'`` and
  ``'ab123'`` collide on lookup. If you need stricter matching, do not
  use the hash column.
* The HMAC ``pii_hash`` is independent of the v1/v2 envelope split —
  search-by-hash continues to work across the migration boundary
  without a re-hash pass.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings


# Envelope format constants.
_V2_PREFIX = 'v2:'
_V2_SALT_BYTES = 16
_V2_INFO = b'pii-encryption-v1'  # Domain separation label.


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


def _normalise_for_hash(plain: str) -> str:
    """Normalise input prior to HMAC so ``'AB-123'`` == ``'ab123'``."""
    if not plain:
        return ''
    return ''.join(ch for ch in plain.lower() if ch.isalnum())


def encrypt_pii(plain: str) -> str:
    """Encrypt a plaintext PII value. Empty input returns empty string.

    Always produces a v2 envelope (``v2:<salt>:<ct>``).
    """
    if plain is None or plain == '':
        return ''
    if not isinstance(plain, str):
        plain = str(plain)
    return _encrypt_v2(plain)


def decrypt_pii(token: str) -> str:
    """Decrypt a previously encrypted PII value. Empty input → empty.

    Transparently handles both v2 envelopes (``v2:salt:ct``) and legacy
    v1 raw Fernet tokens (``gAAAAA...``). Raises
    :class:`cryptography.fernet.InvalidToken` if the ciphertext is
    tampered with or was encrypted under a different ``SECRET_KEY``.
    """
    if not token:
        return ''
    if token.startswith(_V2_PREFIX):
        return _decrypt_v2(token)
    return _decrypt_v1(token)


def pii_hash(plain: str) -> str:
    """HMAC-SHA256 hex digest of *plain* (normalised) keyed off ``SECRET_KEY``.

    Use for exact-match lookup of encrypted columns. Empty input → empty
    string (so blank PII does not collide on a single sentinel hash).

    Note: the hash is independent of the v1/v2 envelope split — the
    HMAC key and normalisation rules have not changed, so existing
    ``<field>_hash`` columns remain valid across the re-encrypt migration.
    """
    normalised = _normalise_for_hash(plain)
    if not normalised:
        return ''
    digest = hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        normalised.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    return digest


__all__ = ['encrypt_pii', 'decrypt_pii', 'pii_hash', 'InvalidToken']
