"""Shared upload validation utilities — magic-byte file-type check.

Why this lives in ``core/``
---------------------------
Multiple apps need the same "is this *really* a PDF, or just a .pdf
renamed from an .exe?" check: tenant onboarding documents (tenants/
views.py), contract attachments (contracts/views/audit_views.py),
HRM employee files (hrm/views_portal.py), and any future upload
surface. Without a shared utility every app reimplements the magic-
byte table, the file-pointer reset, and the size/extension checks —
and they drift. A misalignment in one of those tables would let a
file slip past one entry point while being rejected at another.

The single source of truth lives here. Apps import the validator and
pass their own list of allowed extensions; the magic-byte table is
shared.

Why not python-magic / libmagic?
--------------------------------
``python-magic`` adds a native dependency (libmagic.so/.dll) and a
deployment surprise on Windows + Docker Alpine. The first-16-bytes
check is sufficient for the format catalogue this project uses
(office docs + PDF + common images). When the catalogue needs to
grow beyond that (e.g. video, archives), revisit.
"""
from __future__ import annotations

import os
from typing import Iterable, Optional


# ─── Magic-byte table ────────────────────────────────────────────────
#
# Office 2007+ formats (docx / xlsx) ARE zip files, so they share the
# 'PK\x03\x04' magic with any other zip. That's acceptable here —
# the size + extension gate constrains the misuse window.
MAGIC_SIGNATURES: dict[str, list[bytes]] = {
    '.pdf':  [b'%PDF-'],
    '.jpg':  [b'\xff\xd8\xff'],
    '.jpeg': [b'\xff\xd8\xff'],
    '.png':  [b'\x89PNG\r\n\x1a\n'],
    '.gif':  [b'GIF87a', b'GIF89a'],
    '.doc':  [b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'],   # OLE compound
    '.docx': [b'PK\x03\x04'],                          # zip
    '.xlsx': [b'PK\x03\x04'],                          # zip
    '.pptx': [b'PK\x03\x04'],                          # zip
    '.zip':  [b'PK\x03\x04'],
}


def file_signature_matches(uploaded_file, ext: str) -> bool:
    """Return True when ``uploaded_file``'s magic bytes match ``ext``.

    Reads the first 16 bytes and compares against the canonical
    signature table. **Resets the file pointer afterwards** so the
    caller's later ``.save()`` writes the full content.

    Unknown extensions return ``False`` — callers should reject before
    calling this so the failure mode is "extension not allowed", not
    "magic bytes don't match an unknown sig".
    """
    sigs = MAGIC_SIGNATURES.get(ext.lower())
    if not sigs:
        return False
    head = uploaded_file.read(16)
    uploaded_file.seek(0)
    return any(head.startswith(s) for s in sigs)


def validate_uploaded_file(
    uploaded_file,
    *,
    allowed_extensions: Iterable[str],
    max_bytes: Optional[int] = None,
) -> tuple[bool, str]:
    """End-to-end upload validation.

    Returns ``(is_valid, error_message)``. The empty error string only
    appears when ``is_valid`` is True.

    Args:
        uploaded_file: A Django/DRF uploaded-file object (``.name``,
            ``.size``, ``.read()``).
        allowed_extensions: Iterable of file extensions including the
            leading dot (e.g. ``('.pdf', '.docx')``). Comparison is
            case-insensitive. Extensions outside ``MAGIC_SIGNATURES``
            are still allowed but skip the magic-byte step (use with
            care — extension-only validation is trivially spoofable).
        max_bytes: Optional size ceiling. ``None`` disables the size
            check.

    Checks, in order:
      1. ``uploaded_file`` is non-empty.
      2. Extension is in ``allowed_extensions``.
      3. File size is under ``max_bytes`` (if supplied).
      4. Magic bytes match the extension (when the extension is in
         the magic-byte catalogue).
    """
    if uploaded_file is None or not getattr(uploaded_file, 'name', ''):
        return False, 'No file supplied.'

    ext = os.path.splitext(uploaded_file.name)[1].lower()
    allowed = {e.lower() for e in allowed_extensions}
    if ext not in allowed:
        return False, (
            f'File type {ext or "(none)"} is not allowed. '
            f'Allowed: {", ".join(sorted(allowed))}.'
        )

    if max_bytes is not None and getattr(uploaded_file, 'size', 0) > max_bytes:
        mb = max_bytes / (1024 * 1024)
        return False, f'File exceeds the {mb:.1f} MB size limit.'

    # Magic-byte check only when the extension is in the catalogue.
    # Extensions outside the catalogue (e.g. .csv, .txt) fall through
    # because they don't have a meaningful binary signature.
    if ext in MAGIC_SIGNATURES and not file_signature_matches(uploaded_file, ext):
        return False, (
            f'File content does not match the {ext} extension. '
            f'The file may be corrupted or renamed from a different '
            f'format — upload rejected.'
        )

    return True, ''
