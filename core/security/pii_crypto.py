"""Symmetric encryption + HMAC hashing helpers for PII at rest.

HR PII (NIN, TIN, SSN, BVN, bank account/routing) is high-value: a DB
dump alone exposes it. This module wraps each value in Fernet
(AES-128-CBC + HMAC) so backups, replicas, and read replicas are no
longer sufficient to leak it. For fields that still need exact-match
lookup (NIN, TIN, bank_account) we additionally store an HMAC-SHA256
hash keyed off ``SECRET_KEY`` — search by hashing the query value and
filtering on the indexed ``<field>_hash`` column.

This mirrors :mod:`core.security.mfa_crypto`: same key derivation, same
dependency surface, same rotation story. If/when the deployment wants
true key separation, swap :func:`_derive_key` to read a dedicated
env var or KMS-backed key — call sites do not change.

Notes
-----
* Salary is **not** encrypted (carve-out): it needs to be queryable for
  payroll computation, budget vs actuals, and headcount reporting. It
  stays masked at the serializer layer instead.
* :func:`pii_hash` lowercases + strips its input so ``'AB-123'`` and
  ``'ab123'`` collide on lookup. If you need stricter matching, do not
  use the hash column.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _derive_key() -> bytes:
    """Derive a 32-byte urlsafe-base64 Fernet key from ``SECRET_KEY``."""
    digest = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    return Fernet(_derive_key())


def _normalise_for_hash(plain: str) -> str:
    """Normalise input prior to HMAC so ``'AB-123'`` == ``'ab123'``."""
    if not plain:
        return ''
    return ''.join(ch for ch in plain.lower() if ch.isalnum())


def encrypt_pii(plain: str) -> str:
    """Encrypt a plaintext PII value. Empty input returns empty string."""
    if plain is None or plain == '':
        return ''
    if not isinstance(plain, str):
        plain = str(plain)
    token = _fernet().encrypt(plain.encode('utf-8'))
    return token.decode('utf-8')


def decrypt_pii(token: str) -> str:
    """Decrypt a previously encrypted PII value. Empty input → empty.

    Raises :class:`cryptography.fernet.InvalidToken` if the ciphertext is
    tampered with or was encrypted under a different ``SECRET_KEY``.
    """
    if not token:
        return ''
    plain = _fernet().decrypt(token.encode('utf-8'))
    return plain.decode('utf-8')


def pii_hash(plain: str) -> str:
    """HMAC-SHA256 hex digest of *plain* (normalised) keyed off ``SECRET_KEY``.

    Use for exact-match lookup of encrypted columns. Empty input → empty
    string (so blank PII does not collide on a single sentinel hash).
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
