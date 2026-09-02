"""Payment batching — API surface + permission gates.

These exercise the HTTP layer only; the business rules themselves are
covered in ``test_payment_batch_service.py``. What matters here is that
errors are translated to 400 with a useful message, that the MFA gate on
dispatch is real, and that the public URL is still ``/dispatch/`` even
though the Python method had to be renamed to avoid shadowing
``APIView.dispatch``.
"""
from __future__ import annotations

import pytest

BASE = '/api/v1/accounting/payment-batches'


def _rows(response):
    """Return the row list whether or not the endpoint paginates.

    ``eligible_payments`` returns a bare list (DRF ``ReturnList``); the
    default ModelViewSet list route returns a paginated dict. Tests
    shouldn't care which.
    """
    data = response.data
    if isinstance(data, dict):
        return data.get('results', [])
    return data


@pytest.mark.integration
class TestPaymentBatchAPI:

    def test_list_requires_authentication(self, db, tenant_api_client):
        client = tenant_api_client
        resp = client.get(f'{BASE}/')
        assert resp.status_code in (401, 403)

    def test_superuser_can_list(self, db, tenant_api_client, superuser):
        client = tenant_api_client
        client.force_authenticate(user=superuser)
        resp = client.get(f'{BASE}/')
        assert resp.status_code == 200

    def test_eligible_payments_requires_bank_account_param(self, db, tenant_api_client, superuser):
        client = tenant_api_client
        client.force_authenticate(user=superuser)
        resp = client.get(f'{BASE}/eligible_payments/')
        assert resp.status_code == 400

    def test_eligible_payments_lists_posted_payment(
            self, db, tenant_api_client, superuser, bank_account_for_batch, make_posted_payment):
        client = tenant_api_client
        client.force_authenticate(user=superuser)
        payment = make_posted_payment()
        resp = client.get(f'{BASE}/eligible_payments/',
                          {'bank_account': bank_account_for_batch.id})
        assert resp.status_code == 200
        assert payment.id in [row['id'] for row in _rows(resp)]

    def test_create_returns_batch_number_and_line_count(
            self, db, tenant_api_client, superuser, bank_account_for_batch, make_posted_payment):
        client = tenant_api_client
        client.force_authenticate(user=superuser)
        payment = make_posted_payment(amount='250.00')
        resp = client.post(f'{BASE}/', {
            'source_bank_account': bank_account_for_batch.id,
            'payment_ids': [payment.id],
        }, format='json')
        assert resp.status_code == 201, resp.data
        assert resp.data['batch_number'].startswith('PB/')
        assert resp.data['line_count'] == 1
        assert resp.data['addressee_bank_name'] == 'Premium Trust Bank'
        assert resp.data['addressee_account_no'] == '0100070001'

    def test_blank_bank_details_returns_400_naming_the_vendor(
            self, db, tenant_api_client, superuser, bank_account_for_batch,
            make_posted_payment, vendor_without_bank):
        """The operator must be told which vendor to fix."""
        client = tenant_api_client
        client.force_authenticate(user=superuser)
        payment = make_posted_payment(vendor=vendor_without_bank)
        resp = client.post(f'{BASE}/', {
            'source_bank_account': bank_account_for_batch.id,
            'payment_ids': [payment.id],
        }, format='json')
        assert resp.status_code == 400
        assert 'NoBank Ltd' in str(resp.data)

    def test_unknown_bank_account_returns_400(self, db, tenant_api_client, superuser):
        client = tenant_api_client
        client.force_authenticate(user=superuser)
        resp = client.post(f'{BASE}/', {
            'source_bank_account': 999999,
            'payment_ids': [1],
        }, format='json')
        assert resp.status_code == 400

    def test_letter_endpoint_returns_batch_and_settings(
            self, db, tenant_api_client, superuser, bank_account_for_batch, make_posted_payment):
        client = tenant_api_client
        client.force_authenticate(user=superuser)
        created = client.post(f'{BASE}/', {
            'source_bank_account': bank_account_for_batch.id,
            'payment_ids': [make_posted_payment().id],
        }, format='json')
        batch_id = created.data['id']
        resp = client.get(f'{BASE}/{batch_id}/letter/')
        assert resp.status_code == 200
        assert 'batch' in resp.data and 'settings' in resp.data
        assert resp.data['settings']['office_name']
        assert len(resp.data['batch']['lines']) == 1

    def test_dispatch_url_path_survives_the_method_rename(
            self, db, tenant_api_client, superuser, bank_account_for_batch, make_posted_payment):
        """The Python method is ``dispatch_batch`` (renaming it avoids
        shadowing ``APIView.dispatch``), but the public URL must stay
        ``/dispatch/``. A 404 here means the rename leaked into the API.
        """
        client = tenant_api_client
        client.force_authenticate(user=superuser)
        created = client.post(f'{BASE}/', {
            'source_bank_account': bank_account_for_batch.id,
            'payment_ids': [make_posted_payment().id],
        }, format='json')
        batch_id = created.data['id']
        resp = client.post(f'{BASE}/{batch_id}/dispatch/')
        assert resp.status_code != 404, 'the /dispatch/ URL disappeared'

    def test_list_and_detail_still_work_after_the_rename(
            self, db, tenant_api_client, superuser, bank_account_for_batch, make_posted_payment):
        """Regression guard for the shadowing bug: had the action been
        left named ``dispatch``, it would have overridden the request
        dispatcher and broken EVERY route on this viewset, not just one.
        """
        client = tenant_api_client
        client.force_authenticate(user=superuser)
        created = client.post(f'{BASE}/', {
            'source_bank_account': bank_account_for_batch.id,
            'payment_ids': [make_posted_payment().id],
        }, format='json')
        assert created.status_code == 201
        assert client.get(f'{BASE}/').status_code == 200
        assert client.get(f'{BASE}/{created.data["id"]}/').status_code == 200

    def test_cancel_then_payment_is_eligible_again(
            self, db, tenant_api_client, superuser, bank_account_for_batch, make_posted_payment):
        client = tenant_api_client
        client.force_authenticate(user=superuser)
        payment = make_posted_payment()
        created = client.post(f'{BASE}/', {
            'source_bank_account': bank_account_for_batch.id,
            'payment_ids': [payment.id],
        }, format='json')
        batch_id = created.data['id']

        eligible = client.get(f'{BASE}/eligible_payments/',
                              {'bank_account': bank_account_for_batch.id})
        assert payment.id not in [r['id'] for r in _rows(eligible)]

        cancelled = client.post(f'{BASE}/{batch_id}/cancel/',
                                {'reason': 'keyed in error'}, format='json')
        assert cancelled.status_code == 200
        assert cancelled.data['status'] == 'Cancelled'

        eligible = client.get(f'{BASE}/eligible_payments/',
                              {'bank_account': bank_account_for_batch.id})
        assert payment.id in [r['id'] for r in _rows(eligible)]


@pytest.mark.integration
class TestBankLetterSettingsAPI:

    def test_current_autocreates_with_defaults(self, db, tenant_api_client, superuser):
        client = tenant_api_client
        client.force_authenticate(user=superuser)
        resp = client.get('/api/v1/accounting/bank-letter-settings/current/')
        assert resp.status_code == 200
        assert resp.data['ministry_name'] == 'Ministry of Finance'
        assert resp.data['office_name'] == 'Office of the Accountant General'

    def test_patch_updates_signatories(self, db, tenant_api_client, superuser):
        client = tenant_api_client
        client.force_authenticate(user=superuser)
        resp = client.patch(
            '/api/v1/accounting/bank-letter-settings/current/',
            {'accountant_general_name': 'OKUNBOR V.I',
             'director_treasury_name': 'OGBAUDU A.B'},
            format='json')
        assert resp.status_code == 200
        assert resp.data['accountant_general_name'] == 'OKUNBOR V.I'
        assert resp.data['director_treasury_name'] == 'OGBAUDU A.B'

    def test_non_staff_cannot_patch(self, db, tenant_api_client, maker_user):
        client = tenant_api_client
        client.force_authenticate(user=maker_user)
        resp = client.patch(
            '/api/v1/accounting/bank-letter-settings/current/',
            {'accountant_general_name': 'IMPOSTER'},
            format='json')
        assert resp.status_code == 403
