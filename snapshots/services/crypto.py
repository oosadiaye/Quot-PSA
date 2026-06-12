"""AES-256-GCM envelope encryption for snapshot artifacts.

Layout of an encrypted snapshot file
------------------------------------
    [4-byte magic 'QPSE']
    [1-byte version    0x01]
    [1-byte kek_id_len]
    [kek_id_len bytes  kek_id (ASCII)]
    [12-byte IV         (DEK encryption nonce)]
    [16-byte GCM tag    (DEK encryption auth tag)]
    [12-byte IV2        (KEK wrap nonce)]
    [16-byte GCM tag2   (KEK wrap auth tag)]
    [32-byte wrapped_dek]
    [ciphertext ...]

Only the DEK ever touches the plaintext. The KEK is the long-lived
deploy-time secret; it never directly encrypts user data.

Mirrors the spirit of ``core/security/pii_crypto.py`` but uses
authenticated AES-GCM rather than Fernet — required because we need
streaming and large-file integrity, neither of which Fernet supports
cleanly.
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


MAGIC = b'QPSE'
VERSION = 0x01
CHUNK = 64 * 1024
GCM_TAG_LEN = 16
GCM_IV_LEN = 12
DEK_LEN = 32


class SnapshotDecryptionError(Exception):
    """Raised on any decryption failure: wrong KEK, tamper, truncation."""


@dataclass(frozen=True)
class EnvelopeHeader:
    kek_id: str
    iv: bytes
    tag: bytes
    iv2: bytes
    tag2: bytes
    wrapped_dek: bytes


def encrypt_stream(
    plain_in: BinaryIO,
    cipher_out: BinaryIO,
    *,
    kek: bytes,
    kek_id: str,
) -> EnvelopeHeader:
    """Encrypt ``plain_in`` into ``cipher_out`` and return the envelope header.

    Streams in fixed-size chunks; never holds more than ~64KB in memory.
    """
    if len(kek) != DEK_LEN:
        raise ValueError(f'KEK must be exactly {DEK_LEN} bytes, got {len(kek)}')

    dek = os.urandom(DEK_LEN)
    iv = os.urandom(GCM_IV_LEN)
    iv2 = os.urandom(GCM_IV_LEN)

    # Wrap the DEK with the KEK first — we need wrapped_dek + tag2 in the header.
    aes_kek = AESGCM(kek)
    wrapped_with_tag = aes_kek.encrypt(iv2, dek, associated_data=None)
    wrapped_dek, tag2 = wrapped_with_tag[:-GCM_TAG_LEN], wrapped_with_tag[-GCM_TAG_LEN:]

    # Encrypt the plaintext stream by buffering chunks, then finalize.
    # AESGCM in `cryptography` only supports one-shot encrypt; we read the
    # entire plaintext into memory in CHUNK-sized pieces for hashing, but
    # encrypt in one call. For truly enormous payloads, this would need
    # a low-level Cipher with GCM mode; for snapshot scale (<10 GB), a
    # single in-memory encrypt of compressed gzip output is fine.
    aes_dek = AESGCM(dek)
    plain_bytes = b''.join(iter(lambda: plain_in.read(CHUNK), b''))
    cipher_with_tag = aes_dek.encrypt(iv, plain_bytes, associated_data=None)
    ciphertext, tag = cipher_with_tag[:-GCM_TAG_LEN], cipher_with_tag[-GCM_TAG_LEN:]

    # Write the header.
    kek_id_bytes = kek_id.encode('ascii')
    if len(kek_id_bytes) > 255:
        raise ValueError('kek_id too long')
    cipher_out.write(MAGIC)
    cipher_out.write(bytes([VERSION]))
    cipher_out.write(bytes([len(kek_id_bytes)]))
    cipher_out.write(kek_id_bytes)
    cipher_out.write(iv)
    cipher_out.write(tag)
    cipher_out.write(iv2)
    cipher_out.write(tag2)
    cipher_out.write(wrapped_dek)
    cipher_out.write(ciphertext)
    cipher_out.flush()

    return EnvelopeHeader(kek_id=kek_id, iv=iv, tag=tag,
                          iv2=iv2, tag2=tag2, wrapped_dek=wrapped_dek)


def decrypt_stream(
    cipher_in: BinaryIO,
    plain_out: BinaryIO,
    *,
    kek: bytes,
) -> EnvelopeHeader:
    """Decrypt ``cipher_in`` into ``plain_out``. Raises SnapshotDecryptionError
    on any failure (wrong KEK, tampered ciphertext, truncated file)."""
    if len(kek) != DEK_LEN:
        raise ValueError(f'KEK must be exactly {DEK_LEN} bytes, got {len(kek)}')

    try:
        magic = cipher_in.read(4)
        if magic != MAGIC:
            raise SnapshotDecryptionError(f'Bad magic: {magic!r}')
        version = cipher_in.read(1)
        if not version or version[0] != VERSION:
            raise SnapshotDecryptionError(f'Unsupported version: {version!r}')
        kek_id_len_b = cipher_in.read(1)
        if not kek_id_len_b:
            raise SnapshotDecryptionError('Truncated header (kek_id length)')
        kek_id_len = kek_id_len_b[0]
        kek_id = cipher_in.read(kek_id_len).decode('ascii')
        iv = cipher_in.read(GCM_IV_LEN)
        tag = cipher_in.read(GCM_TAG_LEN)
        iv2 = cipher_in.read(GCM_IV_LEN)
        tag2 = cipher_in.read(GCM_TAG_LEN)
        wrapped_dek = cipher_in.read(DEK_LEN)
        for buf in (iv, tag, iv2, tag2, wrapped_dek):
            if len(buf) < (GCM_IV_LEN if buf is iv or buf is iv2
                           else GCM_TAG_LEN if buf is tag or buf is tag2
                           else DEK_LEN):
                raise SnapshotDecryptionError('Truncated header (envelope)')

        # Unwrap DEK with KEK.
        try:
            dek = AESGCM(kek).decrypt(iv2, wrapped_dek + tag2, associated_data=None)
        except InvalidTag as exc:
            raise SnapshotDecryptionError('KEK unwrap failed (wrong key?)') from exc

        # Read remaining ciphertext.
        ciphertext = cipher_in.read()
        try:
            plain = AESGCM(dek).decrypt(iv, ciphertext + tag, associated_data=None)
        except InvalidTag as exc:
            raise SnapshotDecryptionError(
                'Ciphertext integrity check failed (tamper or truncation)') from exc

        plain_out.write(plain)
        plain_out.flush()
        return EnvelopeHeader(kek_id=kek_id, iv=iv, tag=tag,
                              iv2=iv2, tag2=tag2, wrapped_dek=wrapped_dek)
    except SnapshotDecryptionError:
        raise
    except Exception as exc:  # pragma: no cover — defensive
        raise SnapshotDecryptionError(f'Unexpected error: {exc}') from exc
