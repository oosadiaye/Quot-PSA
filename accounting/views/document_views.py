"""
Document Print Views — Quot PSE
Renders Payment Voucher and Revenue Receipt as printable HTML documents.
Users print via browser (Ctrl+P / Print to PDF).
"""
import base64
import mimetypes

from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.conf import settings
from django.db import connection
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication, SessionAuthentication

from accounting.models.treasury import PaymentVoucherGov
from accounting.models.revenue import RevenueCollection


def tenant_branding_context():
    """Branding (name, contact, logo) for the current tenant's letterhead.

    The logo is embedded as a base64 data URI so the printed HTML is fully
    self-contained — the SPA opens the print response as a blob URL, where a
    relative /media/ image (and its Token auth) would not resolve.
    """
    tenant = getattr(connection, 'tenant', None)
    if tenant is None:
        return {}

    logo_data_uri = ''
    logo = getattr(tenant, 'logo', None)
    if logo:
        try:
            logo.open('rb')
            raw = logo.read()
            logo.close()
            mime = mimetypes.guess_type(logo.name)[0] or 'image/png'
            logo_data_uri = 'data:%s;base64,%s' % (
                mime, base64.b64encode(raw).decode('ascii'),
            )
        except Exception:
            # A missing/unreadable logo file must never break the printout.
            logo_data_uri = ''

    addr_parts = [p for p in (
        getattr(tenant, 'address', ''), getattr(tenant, 'city', ''),
        getattr(tenant, 'state', ''), getattr(tenant, 'country', ''),
        getattr(tenant, 'postal_code', ''),
    ) if p]
    contact_parts = [p for p in (
        getattr(tenant, 'phone', ''), getattr(tenant, 'email', ''),
        getattr(tenant, 'website', ''),
    ) if p]

    return {
        'name': getattr(tenant, 'name', '') or '',
        'tagline': getattr(tenant, 'tagline', '') or '',
        'address_line': ', '.join(addr_parts),
        'contact_line': '  •  '.join(contact_parts),
        'logo_data_uri': logo_data_uri,
    }


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def payment_voucher_print(request, pk):
    """Render Payment Voucher as printable HTML.

    DRF-authenticated so the SPA can fetch this with its
    ``Authorization: Token …`` header (the same one used by
    ``apiClient``). Returns ``text/html`` for browser printing —
    the SPA opens the response body as a blob URL in a new tab.
    """
    pv = get_object_or_404(
        PaymentVoucherGov.objects.select_related(
            'ncoa_code__administrative',
            'ncoa_code__economic',
            'ncoa_code__functional',
            'ncoa_code__programme',
            'ncoa_code__fund',
            'ncoa_code__geographic',
            'tsa_account',
            'appropriation__administrative',
            'appropriation__economic',
            'warrant',
        ),
        pk=pk,
    )

    state_name = getattr(settings, 'PROJECT_NAME', 'State Government')

    html = render_to_string('accounting/payment_voucher_print.html', {
        'pv': pv,
        'state_name': state_name,
        'branding': tenant_branding_context(),
    }, request=request)
    return HttpResponse(html, content_type='text/html; charset=utf-8')


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def revenue_receipt_print(request, pk):
    """Render Revenue Receipt as printable HTML."""
    collection = get_object_or_404(
        RevenueCollection.objects.select_related(
            'revenue_head__economic_segment',
            'ncoa_code__administrative',
            'ncoa_code__economic',
            'ncoa_code__fund',
            'ncoa_code__geographic',
            'tsa_account',
            'collecting_mda',
        ),
        pk=pk,
    )

    state_name = getattr(settings, 'PROJECT_NAME', 'State Government')

    html = render_to_string('accounting/revenue_receipt_print.html', {
        'collection': collection,
        'state_name': state_name,
    }, request=request)
    return HttpResponse(html, content_type='text/html; charset=utf-8')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_voucher_pdf_data(request, pk):
    """API endpoint returning PV data for client-side PDF generation."""
    pv = get_object_or_404(
        PaymentVoucherGov.objects.select_related(
            'ncoa_code__administrative',
            'ncoa_code__economic',
            'ncoa_code__functional',
            'ncoa_code__programme',
            'ncoa_code__fund',
            'ncoa_code__geographic',
            'tsa_account',
            'appropriation',
            'warrant',
        ),
        pk=pk,
    )

    ncoa = None
    if pv.ncoa_code:
        ncoa = {
            'full_code': pv.ncoa_code.full_code,
            'administrative': {'code': pv.ncoa_code.administrative.code, 'name': pv.ncoa_code.administrative.name},
            'economic': {'code': pv.ncoa_code.economic.code, 'name': pv.ncoa_code.economic.name},
            'functional': {'code': pv.ncoa_code.functional.code, 'name': pv.ncoa_code.functional.name},
            'programme': {'code': pv.ncoa_code.programme.code, 'name': pv.ncoa_code.programme.name},
            'fund': {'code': pv.ncoa_code.fund.code, 'name': pv.ncoa_code.fund.name},
            'geographic': {'code': pv.ncoa_code.geographic.code, 'name': pv.ncoa_code.geographic.name},
        }

    return Response({
        'voucher_number': pv.voucher_number,
        'payment_type': pv.payment_type,
        'payee_name': pv.payee_name,
        'payee_bank': pv.payee_bank,
        'payee_account': pv.payee_account,
        'gross_amount': str(pv.gross_amount),
        'wht_amount': str(pv.wht_amount),
        'net_amount': str(pv.net_amount),
        'narration': pv.narration,
        'status': pv.status,
        'tsa_account': pv.tsa_account.account_number if pv.tsa_account else None,
        'source_document': pv.source_document,
        'invoice_number': pv.invoice_number,
        'ncoa': ncoa,
        'appropriation': str(pv.appropriation) if pv.appropriation else None,
        'created_at': pv.created_at.isoformat() if pv.created_at else None,
    })
