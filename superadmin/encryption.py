"""
superadmin/encryption.py
------------------------
Fernet-based at-rest encryption for sensitive model fields.

The encryption key is derived from settings.SECRET_KEY using SHA-256 so no
extra secret management is required.  Rotating Django's SECRET_KEY will
render all encrypted values unreadable — handle SECRET_KEY rotation with the
same care as any encryption-key rotation.

Usage in models:
    from superadmin.encryption import EncryptedCharField

    class MyModel(models.Model):
        secret = EncryptedCharField(blank=True)
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

_ENCRYPTED_PREFIX = 'fernet:'


def _get_fernet() -> Fernet:
    """Derive a stable Fernet key from Django's SECRET_KEY.

    Uses SHA-256 to produce a 32-byte key; Fernet requires exactly 32 bytes
    encoded as URL-safe base64.
    """
    raw = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def encrypt_value(plaintext: str) -> str:
    """Return 'fernet:<base64token>' for the given plaintext string."""
    if not plaintext:
        return plaintext
    token = _get_fernet().encrypt(plaintext.encode('utf-8')).decode('utf-8')
    return _ENCRYPTED_PREFIX + token


def decrypt_value(stored: str) -> str:
    """Decrypt a value previously produced by encrypt_value().

    If the stored value lacks the 'fernet:' prefix it is treated as a
    legacy plain-text value and returned as-is.  It will be encrypted the
    next time the record is saved.
    """
    if not stored:
        return stored
    if not stored.startswith(_ENCRYPTED_PREFIX):
        # Legacy plain-text — return unchanged; will be encrypted on next save
        return stored
    try:
        token = stored[len(_ENCRYPTED_PREFIX):]
        return _get_fernet().decrypt(token.encode('utf-8')).decode('utf-8')
    except (InvalidToken, Exception):
        # Decryption failure (e.g. wrong key after SECRET_KEY rotation) —
        # return as-is rather than raising; the caller should handle appropriately.
        return stored


class EncryptedCharField(models.TextField):
    """TextField that transparently encrypts/decrypts its value at rest.

    - Stored format: "fernet:<url-safe-base64-token>"
    - Legacy plain-text values are read transparently and re-encrypted on
      the next save — no bulk data migration required.
    - Uses TextField (no max_length) because Fernet output is ~137 % of
      the plaintext length after base64 encoding.

    The encryption key is derived from settings.SECRET_KEY.  Rotate with care.
    """

    def from_db_value(self, value, expression, connection):
        return decrypt_value(value) if value else value

    def to_python(self, value):
        return decrypt_value(value) if value else value

    def get_prep_value(self, value):
        if not value:
            return value
        # Avoid double-encrypting a value that was round-tripped through the ORM
        if str(value).startswith(_ENCRYPTED_PREFIX):
            return value
        return encrypt_value(str(value))
