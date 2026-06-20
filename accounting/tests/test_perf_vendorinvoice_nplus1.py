"""
Performance regression: VendorInvoice list endpoint must NOT issue one
``PaymentVoucherGov`` lookup per invoice row (N+1).

Background
----------
``VendorInvoiceSerializer`` exposes three SerializerMethodFields —
``payment_voucher_id`` / ``payment_voucher_number`` /
``payment_voucher_status`` — all backed by ``_linked_pv(obj)``, which
runs::

    PaymentVoucherGov.objects.filter(invoice_number=obj.invoice_number)
                             .order_by('-id').first()

once per invoice (memoised on ``obj._linked_pv_cache``). On the LIST
endpoint that is one query per row → N+1.

``VendorInvoiceViewSet.list()`` now pre-seeds each row's
``_linked_pv_cache`` from a SINGLE batch query before serialization, so
the serializer finds the cache populated and skips its per-row lookup.

These tests assert two things:

1. **Constant PV query count** — the number of queries that touch the
   ``accounting_paymentvouchergov`` table does not scale with the number
   of invoices on the page (same count for 2 rows and for 6 rows). One
   batch query is allowed; per-row lookups are not.
2. **Behaviour is unchanged** — the ``payment_voucher_number`` (and id /
   status) values returned for each invoice are exactly the LATEST PV
   matched by ``invoice_number`` (highest id), and ``None`` when no PV
   exists — identical to the pre-fix serializer output.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.test import APIRequestFactory, force_authenticate

# The DB table behind PaymentVoucherGov. We count queries that hit this
# table specifically, so unrelated query-count drift (prefetch of lines,
# pagination COUNT(*), select_related joins) cannot make the assertion
# flaky — only the N+1 we are fixing moves this number.
PV_TABLE = 'accounting_paymentvouchergov'


# ---------------------------------------------------------------------------
# Lightweight builders for the NCoA scaffolding a PaymentVoucherGov needs
# (ncoa_code + tsa_account are non-null PROTECT FKs).
# ---------------------------------------------------------------------------

def _build_ncoa_code():
    """Create the minimal 6-segment NCoACode a PV must reference.

    Each segment is created at its posting-level minimum: a unique code
    plus the one or two required choice fields. We bypass ``full_clean``
    (direct ``.create``) so the segment validators that enforce exact
    digit widths don't fire — the values chosen here are already valid.
    """
    from accounting.models.ncoa import (
        AdministrativeSegment, EconomicSegment, FunctionalSegment,
        ProgrammeSegment, FundSegment, GeographicSegment, NCoACode,
    )

    admin = AdministrativeSegment.objects.create(
        code='050200000000', name='Test MDA',
        level='UNIT', sector_code='05',
    )
    econ = EconomicSegment.objects.create(
        code='22100100', name='Test Expense', account_type_code='2',
    )
    func = FunctionalSegment.objects.create(
        code='70100', name='General Services', division_code='701',
    )
    prog = ProgrammeSegment.objects.create(
        code='01010000000000', name='Test Programme',
        policy_code='01', programme_code='01',
    )
    fund = FundSegment.objects.create(
        code='01000', name='Consolidated Fund', main_fund_code='01',
    )
    geo = GeographicSegment.objects.create(
        code='51000000', name='Test State', zone_code='5',
    )
    return NCoACode.objects.create(
        administrative=admin, economic=econ, functional=func,
        programme=prog, fund=fund, geographic=geo, is_active=True,
    )


def _build_tsa():
    from accounting.models.treasury import TreasuryAccount
    return TreasuryAccount.objects.create(
        account_number='0011223344',
        account_name='Test TSA',
        bank='CBN',
        account_type='MAIN_TSA',
    )


def _make_pv(*, invoice_number, voucher_number, status, ncoa, tsa):
    """Create one PaymentVoucherGov linked to an invoice by number."""
    from accounting.models.treasury import PaymentVoucherGov
    return PaymentVoucherGov.objects.create(
        voucher_number=voucher_number,
        payment_type='VENDOR',
        ncoa_code=ncoa,
        payee_name='Test Payee',
        payee_account='0011223344',
        payee_bank='Test Bank',
        gross_amount=Decimal('1000.00'),
        narration=f'PV for {invoice_number}',
        tsa_account=tsa,
        invoice_number=invoice_number,
        status=status,
    )


def _make_invoices(vendor, count, *, start=1):
    """Create ``count`` VendorInvoices with deterministic invoice_numbers.

    Returns the list of created invoices (invoice_number is explicit so
    we can link PVs to a subset).
    """
    from accounting.models import VendorInvoice
    invoices = []
    for i in range(start, start + count):
        inv = VendorInvoice.objects.create(
            invoice_number=f'VINV-TEST-{i:04d}',
            vendor=vendor,
            total_amount=Decimal('1000.00'),
            status='Posted',
        )
        invoices.append(inv)
    return invoices


def _build_vendor():
    from procurement.models import Vendor
    return Vendor.objects.create(name='Acme Supplies Ltd', code='V-NPLUS1')


def _list_via_viewset(user):
    """Drive ``VendorInvoiceViewSet.list()`` through a real DRF request.

    Mirrors the action-invocation pattern used by the Sprint-1 period
    tests: build the viewset, attach a DRF Request, and call the bound
    ``list`` method so the new ``list()`` override + serializer run
    end-to-end. Returns the DRF Response.
    """
    from accounting.views.payables import VendorInvoiceViewSet

    factory = APIRequestFactory()
    request = factory.get('/api/accounting/vendor-invoices/')
    force_authenticate(request, user=user)

    view = VendorInvoiceViewSet.as_view({'get': 'list'})
    return view(request)


def _count_pv_queries(captured) -> int:
    """Number of executed queries that touch the PaymentVoucherGov table."""
    return sum(1 for q in captured.captured_queries if PV_TABLE in q['sql'])


@pytest.mark.django_db(transaction=True)
class TestVendorInvoiceListPvLookupIsNotNPlus1:

    def test_pv_query_count_is_constant_regardless_of_row_count(self, superuser):
        """The PV-table query count must be identical for 2 rows and 6 rows.

        If the per-invoice ``_linked_pv`` lookup were still firing, the
        6-row page would issue ~3x as many PV queries as the 2-row page.
        With the batch pre-seed it is a single PV query either way.
        """
        ncoa = _build_ncoa_code()
        tsa = _build_tsa()
        vendor = _build_vendor()

        # --- small page: 2 invoices, both with a linked PV ---
        small = _make_invoices(vendor, 2, start=1)
        for idx, inv in enumerate(small, start=1):
            _make_pv(
                invoice_number=inv.invoice_number,
                voucher_number=f'PV-S-{idx:04d}',
                status='APPROVED', ncoa=ncoa, tsa=tsa,
            )

        with CaptureQueriesContext(connection) as ctx_small:
            resp_small = _list_via_viewset(superuser)
        assert resp_small.status_code == 200
        pv_queries_small = _count_pv_queries(ctx_small)

        # --- larger page: 4 more invoices (6 total), each with a PV ---
        large_extra = _make_invoices(vendor, 4, start=3)
        for idx, inv in enumerate(large_extra, start=3):
            _make_pv(
                invoice_number=inv.invoice_number,
                voucher_number=f'PV-L-{idx:04d}',
                status='APPROVED', ncoa=ncoa, tsa=tsa,
            )

        with CaptureQueriesContext(connection) as ctx_large:
            resp_large = _list_via_viewset(superuser)
        assert resp_large.status_code == 200
        pv_queries_large = _count_pv_queries(ctx_large)

        # Core assertion: PV lookups do NOT scale with the number of rows.
        assert pv_queries_small == pv_queries_large, (
            f'PV lookups scaled with row count: {pv_queries_small} query/queries '
            f'for 2 rows vs {pv_queries_large} for 6 rows — the N+1 is back.'
        )
        # And the batch is genuinely a single query (not zero, not per-row).
        assert pv_queries_large <= 1, (
            f'Expected at most ONE batched PV query, got {pv_queries_large}.'
        )

    def test_payment_voucher_values_are_unchanged(self, superuser):
        """Behaviour preservation: each row reports the LATEST PV by
        invoice_number (highest id), and None when no PV exists."""
        ncoa = _build_ncoa_code()
        tsa = _build_tsa()
        vendor = _build_vendor()

        invoices = _make_invoices(vendor, 3, start=1)
        inv_with_one_pv = invoices[0]
        inv_with_two_pvs = invoices[1]
        inv_without_pv = invoices[2]  # no PV — must serialize as None

        # Single PV on the first invoice.
        _make_pv(
            invoice_number=inv_with_one_pv.invoice_number,
            voucher_number='PV-ONE-0001',
            status='CHECKED', ncoa=ncoa, tsa=tsa,
        )

        # TWO PVs on the second invoice — the serializer (and our seed)
        # must surface the LATEST (highest id == created last).
        _make_pv(
            invoice_number=inv_with_two_pvs.invoice_number,
            voucher_number='PV-OLD-0002',
            status='CANCELLED', ncoa=ncoa, tsa=tsa,
        )
        latest_pv = _make_pv(
            invoice_number=inv_with_two_pvs.invoice_number,
            voucher_number='PV-NEW-0002',
            status='APPROVED', ncoa=ncoa, tsa=tsa,
        )

        resp = _list_via_viewset(superuser)
        assert resp.status_code == 200

        # DRF list response may be paginated ({'results': [...]}) or a bare
        # list — normalise to the row list.
        body = resp.data
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        by_number = {r['invoice_number']: r for r in rows}

        # Invoice with a single PV → that PV's number/status.
        row_one = by_number[inv_with_one_pv.invoice_number]
        assert row_one['payment_voucher_number'] == 'PV-ONE-0001'
        assert row_one['payment_voucher_status'] == 'CHECKED'
        assert row_one['payment_voucher_id'] is not None

        # Invoice with two PVs → the LATEST (highest id) wins.
        row_two = by_number[inv_with_two_pvs.invoice_number]
        assert row_two['payment_voucher_number'] == 'PV-NEW-0002'
        assert row_two['payment_voucher_status'] == 'APPROVED'
        assert row_two['payment_voucher_id'] == latest_pv.pk

        # Invoice with no PV → all three fields None.
        row_none = by_number[inv_without_pv.invoice_number]
        assert row_none['payment_voucher_id'] is None
        assert row_none['payment_voucher_number'] is None
        assert row_none['payment_voucher_status'] is None
