"""AES-256-GCM envelope encryption — round-trip + tamper + key-mismatch."""
from __future__ import annotations

import io
import os

import pytest

from snapshots.services.crypto import (
    EnvelopeHeader,
    SnapshotDecryptionError,
    decrypt_stream,
    encrypt_stream,
)


KEK_GOOD = bytes.fromhex('aa' * 32)
KEK_BAD  = bytes.fromhex('bb' * 32)


def _encrypted_bytes(plaintext: bytes, kek: bytes = KEK_GOOD,
                     kek_id: str = 'kek-v1') -> tuple[bytes, EnvelopeHeader]:
    plain_stream = io.BytesIO(plaintext)
    cipher_stream = io.BytesIO()
    header = encrypt_stream(plain_stream, cipher_stream, kek=kek, kek_id=kek_id)
    return cipher_stream.getvalue(), header


@pytest.mark.unit
def test_round_trip_small_payload():
    pt = b'hello quot pse'
    ct, _ = _encrypted_bytes(pt)
    out = io.BytesIO()
    decrypt_stream(io.BytesIO(ct), out, kek=KEK_GOOD)
    assert out.getvalue() == pt


@pytest.mark.unit
def test_round_trip_streaming_10mb():
    pt = os.urandom(10 * 1024 * 1024)
    ct, _ = _encrypted_bytes(pt)
    out = io.BytesIO()
    decrypt_stream(io.BytesIO(ct), out, kek=KEK_GOOD)
    assert out.getvalue() == pt


@pytest.mark.unit
def test_wrong_kek_raises_decryption_error():
    ct, _ = _encrypted_bytes(b'secret')
    with pytest.raises(SnapshotDecryptionError):
        decrypt_stream(io.BytesIO(ct), io.BytesIO(), kek=KEK_BAD)


@pytest.mark.unit
def test_tampered_ciphertext_raises_decryption_error():
    ct, _ = _encrypted_bytes(b'A' * 1024)
    tampered = bytearray(ct)
    flip_at = len(ct) - 50
    tampered[flip_at] ^= 0xFF
    with pytest.raises(SnapshotDecryptionError):
        decrypt_stream(io.BytesIO(bytes(tampered)), io.BytesIO(), kek=KEK_GOOD)


@pytest.mark.unit
def test_truncated_ciphertext_raises_decryption_error():
    ct, _ = _encrypted_bytes(b'A' * 1024)
    truncated = ct[:-20]
    with pytest.raises(SnapshotDecryptionError):
        decrypt_stream(io.BytesIO(truncated), io.BytesIO(), kek=KEK_GOOD)


@pytest.mark.unit
def test_header_records_kek_id():
    _, header = _encrypted_bytes(b'x', kek_id='kek-v2')
    assert header.kek_id == 'kek-v2'


@pytest.mark.unit
def test_header_magic_bytes_present():
    ct, _ = _encrypted_bytes(b'x')
    assert ct.startswith(b'QPSE')


@pytest.mark.unit
def test_header_version_byte_is_1():
    ct, _ = _encrypted_bytes(b'x')
    assert ct[4] == 0x01


@pytest.mark.unit
def test_truncated_header_kek_id_raises_decryption_error():
    """Stream cut off mid-kek_id field — must raise without leaking InvalidTag."""
    ct, _ = _encrypted_bytes(b'x', kek_id='kek-v1')
    # MAGIC(4) + VERSION(1) + kek_id_len(1) = 6; keep only 1 byte of kek_id.
    truncated = ct[:7]
    with pytest.raises(SnapshotDecryptionError):
        decrypt_stream(io.BytesIO(truncated), io.BytesIO(), kek=KEK_GOOD)


@pytest.mark.unit
def test_tampered_wrapped_dek_raises_decryption_error():
    """Flipping a byte inside the wrapped DEK must trigger the KEK-unwrap
    failure path (distinct from ciphertext tamper)."""
    ct, _ = _encrypted_bytes(b'payload', kek_id='kek-v1')
    # Header layout: MAGIC(4) + VERSION(1) + kek_id_len(1) + kek_id('kek-v1' = 6)
    #              + IV(12) + TAG(16) + IV2(12) + TAG2(16) + WRAPPED_DEK(32) ...
    # wrapped_dek starts at offset 4+1+1+6+12+16+12+16 = 68.
    wrapped_dek_offset = 4 + 1 + 1 + 6 + 12 + 16 + 12 + 16
    tampered = bytearray(ct)
    tampered[wrapped_dek_offset + 5] ^= 0xFF
    with pytest.raises(SnapshotDecryptionError):
        decrypt_stream(io.BytesIO(bytes(tampered)), io.BytesIO(), kek=KEK_GOOD)
