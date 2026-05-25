"""Tests for ``core.file_validation`` — the shared magic-byte +
extension + size validator used by every upload surface.

The big risk this catches: a renamed binary ('malware.exe' → 'invoice.pdf')
sneaking past extension-only validation. Browser-supplied Content-Type
is also trivially spoofable, so neither of those is sufficient on its
own; the validator combines both with a magic-byte check.
"""
from __future__ import annotations

import io


class _FakeUpload:
    """Minimal stand-in for a Django UploadedFile.

    Implements ``.name``, ``.size``, ``.read``, ``.seek`` — that's all
    the validator touches. Avoids the django-tenants conftest setup
    overhead because we're testing pure-Python logic.
    """

    def __init__(self, name: str, content: bytes):
        self.name = name
        self._buf = io.BytesIO(content)
        self.size = len(content)

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)

    def seek(self, pos: int) -> None:
        self._buf.seek(pos)


# ─────────────────────────────────────────────────────────────────────
# Magic-byte signature matching
# ─────────────────────────────────────────────────────────────────────

class TestSignatureMatching:

    def test_pdf_signature_matches(self):
        from core.file_validation import file_signature_matches
        f = _FakeUpload('report.pdf', b'%PDF-1.4\n%anything afterward')
        assert file_signature_matches(f, '.pdf')

    def test_pdf_signature_rejects_non_pdf_body(self):
        # Browser-supplied .pdf extension, body is actually a .exe.
        from core.file_validation import file_signature_matches
        f = _FakeUpload('malware.pdf', b'MZ\x90\x00\x03\x00\x00\x00')  # PE header
        assert not file_signature_matches(f, '.pdf')

    def test_png_signature_matches(self):
        from core.file_validation import file_signature_matches
        f = _FakeUpload('logo.png', b'\x89PNG\r\n\x1a\nfollowed by IHDR...')
        assert file_signature_matches(f, '.png')

    def test_docx_zip_magic_accepted(self):
        from core.file_validation import file_signature_matches
        f = _FakeUpload('contract.docx', b'PK\x03\x04\x14\x00\x06\x00')
        assert file_signature_matches(f, '.docx')

    def test_jpeg_signature_matches(self):
        from core.file_validation import file_signature_matches
        f = _FakeUpload('scan.jpg', b'\xff\xd8\xff\xe0\x00\x10JFIF')
        assert file_signature_matches(f, '.jpg')

    def test_unknown_extension_returns_false(self):
        # The validator doesn't have a sig for .csv — callers should
        # have whitelisted before us, so returning False is correct.
        from core.file_validation import file_signature_matches
        f = _FakeUpload('export.csv', b'name,total\n')
        assert not file_signature_matches(f, '.csv')

    def test_file_pointer_reset_after_check(self):
        # Critical: after the magic-byte read, the file pointer MUST
        # be back at 0 so the caller's later ``.save()`` writes the
        # full content. Without this, every saved PDF would be missing
        # its first 16 bytes — silently corrupted.
        from core.file_validation import file_signature_matches
        body = b'%PDF-1.4\nactual content past byte 16 that must survive'
        f = _FakeUpload('report.pdf', body)
        file_signature_matches(f, '.pdf')
        # Pointer is back at 0 → reading now returns the full body.
        assert f.read() == body


# ─────────────────────────────────────────────────────────────────────
# End-to-end validate_uploaded_file
# ─────────────────────────────────────────────────────────────────────

class TestValidateUploadedFile:

    def test_happy_path(self):
        from core.file_validation import validate_uploaded_file
        f = _FakeUpload('report.pdf', b'%PDF-1.4\nbody')
        ok, err = validate_uploaded_file(
            f, allowed_extensions=('.pdf',), max_bytes=1024,
        )
        assert ok and err == ''

    def test_rejects_when_extension_not_in_allowed_list(self):
        from core.file_validation import validate_uploaded_file
        f = _FakeUpload('script.exe', b'MZ\x90\x00')
        ok, err = validate_uploaded_file(
            f, allowed_extensions=('.pdf', '.docx'),
        )
        assert not ok
        assert '.exe' in err

    def test_rejects_when_size_exceeds_max(self):
        from core.file_validation import validate_uploaded_file
        body = b'%PDF-1.4' + b'x' * 2000
        f = _FakeUpload('big.pdf', body)
        ok, err = validate_uploaded_file(
            f, allowed_extensions=('.pdf',), max_bytes=500,
        )
        assert not ok
        assert 'size limit' in err

    def test_rejects_when_magic_bytes_dont_match_extension(self):
        # The classic attack: rename malware.exe to invoice.pdf,
        # upload as Content-Type: application/pdf. Extension whitelist
        # alone says "yes"; the magic-byte check is the only thing
        # that catches it.
        from core.file_validation import validate_uploaded_file
        f = _FakeUpload('invoice.pdf', b'MZ\x90\x00fake PE binary')
        ok, err = validate_uploaded_file(
            f, allowed_extensions=('.pdf',),
        )
        assert not ok
        assert 'content does not match' in err.lower()

    def test_rejects_when_no_file_supplied(self):
        from core.file_validation import validate_uploaded_file
        ok, err = validate_uploaded_file(None, allowed_extensions=('.pdf',))
        assert not ok
        assert 'no file' in err.lower()

    def test_size_check_optional(self):
        # max_bytes=None means no size ceiling.
        from core.file_validation import validate_uploaded_file
        body = b'%PDF-1.4' + b'x' * 10_000_000
        f = _FakeUpload('huge.pdf', body)
        ok, _err = validate_uploaded_file(
            f, allowed_extensions=('.pdf',), max_bytes=None,
        )
        assert ok

    def test_extension_outside_magic_catalogue_passes_extension_check_only(self):
        # .csv is whitelisted but has no magic signature in the
        # catalogue — that's allowed (the doc-string warns it's
        # extension-only validation, which is appropriate for plain
        # text formats).
        from core.file_validation import validate_uploaded_file
        f = _FakeUpload('export.csv', b'name,total\n')
        ok, err = validate_uploaded_file(
            f, allowed_extensions=('.csv',),
        )
        assert ok and err == ''
