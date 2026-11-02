"""Sealed bids: the contents of a bid are encrypted when it is submitted and read back only after the recorded opening.

Each tender has its own key, derived from a master secret, so one tender's bids cannot be read with another's key and a
leaked ciphertext is useless without the server's secret. The ciphertext is also bound to its tender and bidder, so a sealed
bid cannot be moved to another tender or passed off as another bidder's.

What this does and does not guarantee: bids are unreadable at rest and the application refuses to decrypt one before the
opening is recorded. It is not a cryptographic time lock; someone with the server's master secret and database access could
decrypt earlier, which is why opening is an approver's recorded act and every opening is audited.
"""
from __future__ import annotations

import hashlib
import json
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.db import connection

NONCE_BYTES = 12


class SealedError(Exception):
    """A bid cannot be read: it is still sealed, or it has been tampered with."""


def _master_secret() -> bytes:
    raw = getattr(settings, 'EGP_BID_KEK_HEX', None) or os.getenv('EGP_BID_KEK_HEX')
    if raw:
        return bytes.fromhex(raw)
    return str(settings.SECRET_KEY).encode()                 # a deployment sets its own key; this keeps development working


def _key(tender_id: int) -> bytes:
    info = f'egp-bid:{connection.schema_name}:{tender_id}'.encode()
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(_master_secret())


def _aad(tender_id: int, bidder_id: int) -> bytes:
    return f'tender={tender_id};bidder={bidder_id}'.encode()


def seal(tender_id: int, bidder_id: int, contents: dict) -> tuple[bytes, str]:
    """Encrypt a bid's contents; returns the ciphertext and a hash of it for the receipt."""
    nonce = os.urandom(NONCE_BYTES)
    body = json.dumps(contents, sort_keys=True, default=str).encode()
    blob = nonce + AESGCM(_key(tender_id)).encrypt(nonce, body, _aad(tender_id, bidder_id))
    return blob, hashlib.sha256(blob).hexdigest()


def unseal(tender_id: int, bidder_id: int, blob: bytes) -> dict:
    """Decrypt a bid's contents. The caller has already checked that the tender has been opened."""
    blob = bytes(blob or b'')
    if len(blob) <= NONCE_BYTES:
        raise SealedError('This bid has no sealed contents.')
    try:
        body = AESGCM(_key(tender_id)).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], _aad(tender_id, bidder_id))
    except Exception as exc:  # noqa: BLE001 - any failure means the bid is not what was sealed
        raise SealedError('This bid could not be read: it has been altered or moved.') from exc
    return json.loads(body)
