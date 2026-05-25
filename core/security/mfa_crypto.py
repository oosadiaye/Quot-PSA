"""Symmetric encryption helpers for MFA secrets at rest.

The TOTP shared secret used for MFA is high-value: anyone with the
secret can mint valid 6-digit codes for that user. We previously stored
it as a plaintext ``CharField`` on ``UserMFA``; this module wraps it in
Fernet (AES-128-CBC + HMAC) so a database dump alone is no longer
sufficient to bypass MFA.

Key derivation
--------------
We deterministically derive the Fernet key from ``settings.SECRET_KEY``
via SHA-256 → urlsafe base64. This avoids introducing a new secret
material rotation surface, and it keeps the change dependency-free
(``cryptography`` is already a transitive Django dep).

If/when the deployment wants real key separation, swap
``_derive_key()`` to read from a dedicated ``MFA_FERNET_KEY`` env var
(or KMS) — the call sites do not change.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _derive_key() -> bytes:
    """Derive a 32-byte urlsafe-base64 Fernet key from ``SECRET_KEY``."""
    digest = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    return Fernet(_derive_key())


def encrypt_secret(plain: str) -> str:
    """Encrypt a plaintext MFA secret. Returns urlsafe base64 ciphertext."""
    if plain is None:
        plain = ''
    token = _fernet().encrypt(plain.encode('utf-8'))
    return token.decode('utf-8')


def decrypt_secret(token: str) -> str:
    """Decrypt a previously encrypted MFA secret. Raises ``InvalidToken``
    if the ciphertext is tampered with or was encrypted under a
    different ``SECRET_KEY``.
    """
    if not token:
        return ''
    plain = _fernet().decrypt(token.encode('utf-8'))
    return plain.decode('utf-8')


__all__ = ['encrypt_secret', 'decrypt_secret', 'InvalidToken']
