"""
HTTP endpoint for MDA bulk data import.

``POST /api/v1/accounting/mda-imports/preview/``
    Parses the uploaded CSV/XLSX using a spec keyed by ``data_type``
    and returns the structured rows + errors WITHOUT persisting.
    Used by the OAGF preview page — the AG user reviews the parse,
    catches issues, and either re-uploads or proceeds to consolidate.

Supported data types
--------------------
Each ``data_type`` maps to an :class:`~accounting.services.mda_data_import.ImportSpec`
describing the expected columns. The catalogue is declared in the
module below so new types can be added with a single entry.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounting.services.mda_data_import import ImportSpec, MDAImporter


# ── Spec catalogue ─────────────────────────────────────────────────────

IMPORT_SPECS: dict[str, ImportSpec] = {
    # Journal summary — monthly aggregate of each MDA's postings.
    'journal_summary': ImportSpec(
        required_columns=['mda_code', 'account_code', 'debit', 'credit'],
        optional_columns=['narration', 'fund_code', 'function_code', 'program_code'],
        numeric_columns=['debit', 'credit'],
    ),
    # Revenue collection schedule — MDA-side IGR captures.
    'revenue_collection': ImportSpec(
        required_columns=[
            'collection_date', 'revenue_head_code',
            'payer_name', 'amount', 'payment_reference',
        ],
        optional_columns=['payer_tin', 'rrr', 'narration'],
        numeric_columns=['amount'],
        date_columns=['collection_date'],
    ),
    # Payroll summary — MDA-side totals for AG consolidation.
    'payroll_summary': ImportSpec(
        required_columns=[
            'period', 'mda_code', 'headcount',
            'gross_pay', 'paye', 'pension', 'nhia', 'net_pay',
        ],
        numeric_columns=[
            'headcount', 'gross_pay', 'paye', 'pension', 'nhia', 'net_pay',
        ],
    ),
    # Provision register — IPSAS 19 items an MDA reports upward.
    'provisions': ImportSpec(
        required_columns=[
            'reference', 'category', 'title', 'amount',
            'recognition_date', 'likelihood',
        ],
        optional_columns=[
            'description', 'undiscounted_amount',
            'expected_settlement_date', 'mda_code',
        ],
        numeric_columns=['amount', 'undiscounted_amount'],
        date_columns=['recognition_date', 'expected_settlement_date'],
    ),
}


class MDAImportPreviewView(APIView):
    """``POST /api/v1/accounting/mda-imports/preview/``.

    Multipart form body:
      * ``data_type``: one of the keys in :data:`IMPORT_SPECS`.
      * ``file``:      the uploaded CSV/XLSX.

    Returns ``{rows, errors, columns, total_rows, accepted_rows, rejected_rows}``.
    Does NOT persist anything — this is the preview/validation phase.
    A follow-up ticket will add a ``commit/`` endpoint that takes the
    same parse result and materialises the rows into the appropriate
    domain tables under a wrapping transaction.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        data_type = (request.data.get('data_type') or '').strip()
        upload = request.FILES.get('file')

        if not data_type:
            return Response(
                {'error': 'data_type is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not upload:
            return Response(
                {'error': 'file is required (multipart form field).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        spec = IMPORT_SPECS.get(data_type)
        if spec is None:
            return Response(
                {
                    'error': f'Unknown data_type {data_type!r}.',
                    'supported_types': sorted(IMPORT_SPECS.keys()),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Size guard — reject > 10MB at the view layer before parsing.
        size = getattr(upload, 'size', 0) or 0
        if size > 10 * 1024 * 1024:
            return Response(
                {
                    'error': (
                        f'File is {size/1024/1024:.1f} MB — exceeds 10 MB '
                        f'limit. Split into smaller files.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = MDAImporter.parse(upload, spec)
        return Response({
            'data_type':     data_type,
            'is_valid':      result.is_valid(),
            'columns':       result.columns,
            'total_rows':    result.total_rows,
            'accepted_rows': result.accepted_rows,
            'rejected_rows': result.rejected_rows,
            'rows':          result.rows,
            'errors':        result.errors,
        })


class MDAImportCatalogueView(APIView):
    """``GET /api/v1/accounting/mda-imports/catalogue/``."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'data_types': [
                {
                    'key':               key,
                    'required_columns':  spec.required_columns,
                    'optional_columns':  spec.optional_columns,
                    'numeric_columns':   spec.numeric_columns,
                    'date_columns':      spec.date_columns,
                    'max_rows':          spec.max_rows,
                }
                for key, spec in IMPORT_SPECS.items()
            ],
        })


class MDAImportCommitView(APIView):
    """``POST /api/v1/accounting/mda-imports/commit/`` — materialise a
    previewed / pre-parsed import into domain tables under a
    transaction.

    Body (JSON or multipart):
      * ``data_type`` — required; one of the keys in :data:`IMPORT_SPECS`.
      * ``rows`` — optional list of pre-parsed row dicts (typical
        flow: preview first, then commit the returned rows).
      * ``file`` — optional multipart upload (one-shot flow: parse
        and commit in a single call).
      * ``idempotency_key`` — optional explicit key; otherwise the
        service derives one from the row content.
      * ``notes`` — optional audit annotation persisted on the import
        log.

    Either ``rows`` or ``file`` must be supplied.

    Returns 201 with ``{data_type, created_count, created_ids,
    idempotency_key}`` on success. Re-commits of the same key
    short-circuit (no duplicates; same result returned as 201).

    On row-level mapping failure the endpoint returns 400 with per-row
    diagnostics; no rows are persisted (the service rolls back the
    whole transaction on any error).
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        from accounting.services.mda_data_commit import (
            MDAImportCommitService, CommitError,
        )

        data_type = (request.data.get('data_type') or '').strip()
        if not data_type:
            return Response(
                {'error': 'data_type is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rows = request.data.get('rows')
        upload = request.FILES.get('file')
        if rows is None and upload is None:
            return Response(
                {
                    'error': (
                        'Provide either "rows" (from a preview) or "file" '
                        '(to parse and commit in one step).'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # One-shot path: parse the uploaded file first.
        if rows is None:
            spec = IMPORT_SPECS.get(data_type)
            if spec is None:
                return Response(
                    {
                        'error': f'Unknown data_type {data_type!r}.',
                        'supported_types': sorted(IMPORT_SPECS.keys()),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            parse_result = MDAImporter.parse(upload, spec)
            if not parse_result.is_valid():
                return Response(
                    {
                        'error': 'Parse failed. Fix the errors and retry.',
                        'parse_errors': parse_result.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            rows = parse_result.rows

        if not isinstance(rows, list):
            return Response(
                {'error': 'rows must be a JSON array of objects.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        idempotency_key = request.data.get('idempotency_key') or None
        notes = (request.data.get('notes') or '').strip()

        try:
            result = MDAImportCommitService.commit(
                data_type=data_type,
                rows=rows,
                user=request.user,
                notes=notes,
                idempotency_key=idempotency_key,
            )
        except CommitError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not result.is_success():
            return Response(
                {
                    'data_type':       result.data_type,
                    'created_count':   result.created_count,
                    'updated_count':   result.updated_count,
                    'errors':          result.errors,
                    'idempotency_key': result.idempotency_key,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            'data_type':       result.data_type,
            'created_count':   result.created_count,
            'updated_count':   result.updated_count,
            'created_ids':     result.created_ids,
            'idempotency_key': result.idempotency_key,
            'message': (
                f'Committed {result.created_count} row(s) to {data_type!r}.'
            ),
        }, status=status.HTTP_201_CREATED)
