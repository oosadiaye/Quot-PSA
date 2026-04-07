"""
Generic REST / Webhook Adapters
================================
Used for: QuickBooks, Xero, NetSuite, Shopify, Stripe, Paystack, Flutterwave,
Salesforce, HubSpot, and any custom REST endpoint.
"""
import hashlib
import hmac
import logging

from .base import AdapterError, BaseERPAdapter

logger = logging.getLogger('integrations.generic')


class QuickBooksAdapter(BaseERPAdapter):
    """
    QuickBooks Online (QBO) adapter via Intuit REST API v3.
    Base URL: https://quickbooks.api.intuit.com/v3/company/{realmId}/
    Auth: OAuth 2.0 Authorization Code (user grants access via Intuit consent screen).
    Credentials: {"realm_id": "...", "access_token": "...", "refresh_token": "..."}
    """

    def _get_headers(self) -> dict:
        creds = self.config.credentials or {}
        return {
            'Authorization': f'Bearer {creds.get("access_token", "")}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

    def test_connection(self) -> bool:
        try:
            creds = self.config.credentials or {}
            realm_id = creds.get('realm_id', '')
            self.get(f'v3/company/{realm_id}/companyinfo/{realm_id}')
            return True
        except AdapterError:
            return False

    def get_accounts(self) -> list:
        creds = self.config.credentials or {}
        realm_id = creds.get('realm_id', '')
        data = self.get(
            f'v3/company/{realm_id}/query',
            params={'query': 'SELECT * FROM Account MAXRESULTS 1000'},
        )
        return [{
            'code': str(row.get('AcctNum', row.get('Id', ''))),
            'name': row.get('Name', ''),
            'account_type': row.get('AccountType', ''),
            'remote_id': row.get('Id', ''),
            'remote_system': 'quickbooks',
        } for row in data.get('QueryResponse', {}).get('Account', [])]

    def push_invoice(self, invoice: dict) -> dict:
        creds = self.config.credentials or {}
        realm_id = creds.get('realm_id', '')
        payload = {
            'CustomerRef': {'value': invoice.get('customer_remote_id', '')},
            'TxnDate': invoice.get('invoice_date', ''),
            'DueDate': invoice.get('due_date', ''),
            'Line': [
                {
                    'DetailType': 'SalesItemLineDetail',
                    'Amount': float(line.get('total', 0)),
                    'SalesItemLineDetail': {
                        'ItemRef': {'value': line.get('item_remote_id', '')},
                        'Qty': float(line.get('quantity', 1)),
                        'UnitPrice': float(line.get('unit_price', 0)),
                    },
                }
                for line in invoice.get('lines', [])
            ],
        }
        return self.post(f'v3/company/{realm_id}/invoice', data=payload)


class XeroAdapter(BaseERPAdapter):
    """
    Xero API adapter.
    Base URL: https://api.xero.com/api.xro/2.0/
    Auth: OAuth 2.0 Client Credentials or Authorization Code.
    """

    def _get_headers(self) -> dict:
        creds = self.config.credentials or {}
        tenant_id = creds.get('tenant_id', '')
        return {
            'Authorization': f'Bearer {creds.get("access_token", "")}',
            'Xero-Tenant-Id': tenant_id,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

    def test_connection(self) -> bool:
        try:
            self.get('api.xro/2.0/Organisation')
            return True
        except AdapterError:
            return False

    def get_accounts(self) -> list:
        data = self.get('api.xro/2.0/Accounts')
        return [{
            'code': row.get('Code', ''),
            'name': row.get('Name', ''),
            'account_type': row.get('Type', '').lower(),
            'remote_id': row.get('AccountID', ''),
            'remote_system': 'xero',
        } for row in data.get('Accounts', [])]

    def get_contacts(self, is_supplier: bool = False, is_customer: bool = False) -> list:
        params = {}
        if is_supplier:
            params['IsSupplier'] = 'true'
        if is_customer:
            params['IsCustomer'] = 'true'
        data = self.get('api.xro/2.0/Contacts', params=params)
        return [{
            'name': row.get('Name', ''),
            'email': row.get('EmailAddress', ''),
            'code': row.get('AccountNumber', ''),
            'remote_id': row.get('ContactID', ''),
            'remote_system': 'xero',
        } for row in data.get('Contacts', [])]

    def push_invoice(self, invoice: dict) -> dict:
        payload = {
            'Type': 'ACCREC',
            'Contact': {'ContactID': invoice.get('customer_remote_id', '')},
            'Date': invoice.get('invoice_date', ''),
            'DueDate': invoice.get('due_date', ''),
            'Reference': invoice.get('reference', ''),
            'LineItems': [
                {
                    'Description': line.get('description', ''),
                    'Quantity': float(line.get('quantity', 1)),
                    'UnitAmount': float(line.get('unit_price', 0)),
                    'AccountCode': line.get('account_code', ''),
                    'TaxType': line.get('tax_type', 'NONE'),
                }
                for line in invoice.get('lines', [])
            ],
        }
        return self.post('api.xro/2.0/Invoices', data={'Invoices': [payload]})


class ShopifyAdapter(BaseERPAdapter):
    """
    Shopify REST Admin API adapter.
    Base URL: https://{shop}.myshopify.com/admin/api/2024-01/
    Auth: API Key header (X-Shopify-Access-Token)
    """

    def _get_headers(self) -> dict:
        creds = self.config.credentials or {}
        return {
            'X-Shopify-Access-Token': creds.get('access_token', ''),
            'Content-Type': 'application/json',
        }

    def test_connection(self) -> bool:
        try:
            self.get('shop.json')
            return True
        except AdapterError:
            return False

    def get_products(self, limit: int = 250) -> list:
        data = self.get('products.json', params={'limit': limit, 'fields': 'id,title,variants,status'})
        results = []
        for product in data.get('products', []):
            for variant in product.get('variants', []):
                results.append({
                    'code': variant.get('sku', ''),
                    'name': product.get('title', ''),
                    'variant_title': variant.get('title', ''),
                    'price': float(variant.get('price', 0)),
                    'inventory_quantity': variant.get('inventory_quantity', 0),
                    'remote_id': str(variant.get('id', '')),
                    'remote_system': 'shopify',
                })
        return results

    def get_orders(self, status: str = 'open', limit: int = 250) -> list:
        data = self.get('orders.json', params={'status': status, 'limit': limit})
        return [{
            'order_number': row.get('name', ''),
            'customer_email': row.get('customer', {}).get('email', ''),
            'total_price': float(row.get('total_price', 0)),
            'currency': row.get('currency', ''),
            'status': row.get('financial_status', ''),
            'created_at': row.get('created_at', ''),
            'remote_id': str(row.get('id', '')),
            'remote_system': 'shopify',
        } for row in data.get('orders', [])]

    def verify_webhook(self, raw_body: bytes, hmac_header: str) -> bool:
        """Verify Shopify HMAC-SHA256 webhook signature."""
        creds = self.config.credentials or {}
        secret = creds.get('webhook_secret', self.config.webhook_secret)
        if not secret:
            return False
        import base64
        computed = base64.b64encode(
            hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha256).digest()
        ).decode()
        return hmac.compare_digest(computed, hmac_header)


class StripeAdapter(BaseERPAdapter):
    """
    Stripe API adapter.
    Base URL: https://api.stripe.com/v1/
    Auth: Basic with secret key as username (RFC 7617)
    """

    def _get_headers(self) -> dict:
        creds = self.config.credentials or {}
        import base64
        key = creds.get('secret_key', '')
        encoded = base64.b64encode(f'{key}:'.encode()).decode()
        return {
            'Authorization': f'Basic {encoded}',
            'Content-Type': 'application/x-www-form-urlencoded',
        }

    def test_connection(self) -> bool:
        try:
            self.get('v1/balance')
            return True
        except AdapterError:
            return False

    def get_payments(self, limit: int = 100) -> list:
        data = self.get('v1/payment_intents', params={'limit': limit})
        return [{
            'stripe_id': row.get('id', ''),
            'amount': row.get('amount', 0) / 100.0,
            'currency': row.get('currency', '').upper(),
            'status': row.get('status', ''),
            'customer_id': row.get('customer', ''),
            'created_at': row.get('created', ''),
            'remote_id': row.get('id', ''),
            'remote_system': 'stripe',
        } for row in data.get('data', [])]

    def verify_webhook(self, raw_body: bytes, sig_header: str) -> bool:
        """
        Verify Stripe webhook signature (Stripe-Signature header).
        Format: t=timestamp,v1=signature,...
        """
        creds = self.config.credentials or {}
        secret = creds.get('webhook_secret', self.config.webhook_secret)
        if not secret:
            return False
        import time
        parts = {p.split('=', 1)[0]: p.split('=', 1)[1] for p in sig_header.split(',') if '=' in p}
        timestamp = parts.get('t', '')
        sig = parts.get('v1', '')
        payload = f'{timestamp}.{raw_body.decode()}'
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        try:
            # Reject if older than 5 minutes
            if abs(time.time() - int(timestamp)) > 300:
                return False
            return hmac.compare_digest(expected, sig)
        except (ValueError, TypeError):
            return False


class PaystackAdapter(BaseERPAdapter):
    """Paystack payment gateway adapter (popular in West Africa)."""

    def _get_headers(self) -> dict:
        creds = self.config.credentials or {}
        return {
            'Authorization': f'Bearer {creds.get("secret_key", "")}',
            'Content-Type': 'application/json',
        }

    def test_connection(self) -> bool:
        try:
            self.get('transaction')
            return True
        except AdapterError:
            return False

    def get_transactions(self, per_page: int = 50) -> list:
        data = self.get('transaction', params={'perPage': per_page})
        return [{
            'reference': row.get('reference', ''),
            'amount': float(row.get('amount', 0)) / 100.0,
            'currency': row.get('currency', ''),
            'status': row.get('status', ''),
            'customer_email': row.get('customer', {}).get('email', ''),
            'paid_at': row.get('paid_at', ''),
            'remote_id': str(row.get('id', '')),
            'remote_system': 'paystack',
        } for row in data.get('data', [])]

    def verify_webhook(self, raw_body: bytes, signature_header: str) -> bool:
        creds = self.config.credentials or {}
        secret = creds.get('secret_key', self.config.webhook_secret)
        if not secret:
            return False
        computed = hmac.new(secret.encode(), raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(computed, signature_header)


class FlutterwaveAdapter(BaseERPAdapter):
    """Flutterwave payment gateway adapter."""

    def _get_headers(self) -> dict:
        creds = self.config.credentials or {}
        return {
            'Authorization': f'Bearer {creds.get("secret_key", "")}',
            'Content-Type': 'application/json',
        }

    def test_connection(self) -> bool:
        try:
            self.get('v3/transactions?page=1&per_page=1')
            return True
        except AdapterError:
            return False

    def get_transactions(self, page: int = 1, per_page: int = 50) -> list:
        data = self.get('v3/transactions', params={'page': page, 'per_page': per_page})
        return [{
            'tx_ref': row.get('tx_ref', ''),
            'amount': float(row.get('amount', 0)),
            'currency': row.get('currency', ''),
            'status': row.get('status', ''),
            'customer_email': row.get('customer', {}).get('email', ''),
            'remote_id': str(row.get('id', '')),
            'remote_system': 'flutterwave',
        } for row in data.get('data', [])]

    def verify_webhook(self, raw_body: bytes, signature_header: str) -> bool:
        creds = self.config.credentials or {}
        secret_hash = creds.get('secret_hash', self.config.webhook_secret)
        return hmac.compare_digest(signature_header, secret_hash) if secret_hash else False


class GenericRESTAdapter(BaseERPAdapter):
    """
    Catch-all adapter for any REST API.
    Field mapping is entirely driven by FieldMapping records in the DB.
    """

    def test_connection(self) -> bool:
        try:
            self.get('')
            return True
        except AdapterError:
            return False

    def sync_entity(self, endpoint: str, module: str, transformer=None) -> list:
        """
        Fetch all records from `endpoint` and apply field mappings for `module`.
        :param transformer: optional callable(row) -> dict for custom transforms
        """
        data = self.get(endpoint)
        # Support both list responses and {data: [...]} / {results: [...]} wrappers
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get('data') or data.get('results') or data.get('value') or []
        else:
            rows = []
        result = []
        for row in rows:
            if transformer:
                row = transformer(row)
            mapped = self.apply_field_mappings(module, row, direction='inbound')
            result.append(mapped)
        return result
