"""
Microsoft Dynamics 365 Adapter
================================
Supports Dynamics 365 Business Central (BC) and Finance & Operations (F&O).

Dynamics 365 BC REST API base: /api/v2.0/companies({companyId})/...
Dynamics 365 F&O OData base  : /data/...

Auth: OAuth 2.0 Client Credentials (Azure AD / Entra ID)
Token endpoint: https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token
Scope for BC : https://api.businesscentral.dynamics.com/.default
Scope for F&O : https://{env}.operations.dynamics.com/.default
"""
import logging
from datetime import datetime, timedelta, timezone

from .base import AdapterError, BaseERPAdapter

logger = logging.getLogger('integrations.dynamics')


class Dynamics365BCAdapter(BaseERPAdapter):
    """Adapter for Microsoft Dynamics 365 Business Central REST API v2.0."""

    def __init__(self, config):
        super().__init__(config)
        self._access_token = None
        self._token_expiry = None
        self._company_id = None

    def _get_oauth_token(self) -> str:
        """Fetch or refresh OAuth 2.0 client credentials token."""
        import requests as req_lib

        # Return cached token if still valid
        now = datetime.now(timezone.utc)
        if self._access_token and self._token_expiry and now < self._token_expiry:
            return self._access_token

        # Also check persisted cache
        cache = self.config.token_cache or {}
        if cache.get('access_token') and cache.get('expires_at'):
            from datetime import datetime as dt, timezone as tz
            try:
                expiry = dt.fromisoformat(cache['expires_at'])
                # Make expiry timezone-aware if it isn't
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=tz.utc)
                if dt.now(tz.utc) < expiry - timedelta(seconds=60):
                    self._access_token = cache['access_token']
                    self._token_expiry = expiry
                    return self._access_token
            except (ValueError, TypeError) as exc:
                logger.debug(
                    "dynamics: stale/malformed token cache entry discarded: %s", exc,
                )

        creds = self.config.credentials or {}
        tenant_id = self.config.dynamics_tenant_id or creds.get('tenant_id', '')
        client_id = creds.get('client_id', '')
        client_secret = creds.get('client_secret', '')
        scope = creds.get('scope', 'https://api.businesscentral.dynamics.com/.default')

        token_url = f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token'
        data = {
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret,
            'scope': scope,
        }
        try:
            resp = req_lib.post(token_url, data=data, timeout=30)
            if not resp.ok:
                raise AdapterError(
                    f'Dynamics token request failed: {resp.status_code}',
                    resp.status_code, resp.text,
                )
            token_data = resp.json()
            self._access_token = token_data['access_token']
            expires_in = int(token_data.get('expires_in', 3600))
            self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)
            # Persist to config
            self.config.token_cache = {
                'access_token': self._access_token,
                'expires_at': self._token_expiry.isoformat(),
            }
            self.config.save(update_fields=['token_cache'])
            return self._access_token
        except req_lib.exceptions.RequestException as exc:
            raise AdapterError(f'Cannot reach token endpoint: {exc}') from exc

    def _get_headers(self) -> dict:
        token = self._get_oauth_token()
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

    def _get_company_id(self) -> str:
        if not self._company_id:
            companies = self.get('api/v2.0/companies')
            items = companies.get('value', [])
            if not items:
                raise AdapterError('No Dynamics 365 companies found')
            # Use the first company or match by name
            target = self.config.dynamics_environment
            for c in items:
                if not target or c.get('name') == target or c.get('id') == target:
                    self._company_id = c['id']
                    break
            if not self._company_id:
                self._company_id = items[0]['id']
        return self._company_id

    def _company_path(self, endpoint: str) -> str:
        company_id = self._get_company_id()
        return f"api/v2.0/companies({company_id})/{endpoint.lstrip('/')}"

    # ---- Connection Test ----

    def test_connection(self) -> bool:
        try:
            self._get_oauth_token()
            self._get_company_id()
            return True
        except AdapterError:
            return False

    # ---- Chart of Accounts ----

    def get_accounts(self) -> list:
        data = self.get(self._company_path('accounts'), params={'$top': 2000})
        results = data.get('value', [])
        return [{
            'code': str(row.get('number', '')),
            'name': row.get('displayName', ''),
            'account_type': self._map_d365_account_type(row.get('category', '')),
            'is_blocked': row.get('blocked', False),
            'remote_id': row.get('id', ''),
            'remote_system': 'dynamics_365_bc',
        } for row in results]

    def push_journal_entry(self, header: dict, lines: list) -> dict:
        """Post journal lines to Dynamics 365 BC via generalJournalLines."""
        company_id = self._get_company_id()
        batch_url = self._company_path('generalJournalBatches')
        # 1. Find or create a journal batch
        batches = self.get(batch_url, params={'$filter': "displayName eq 'DTSG-ERP'"})
        batch_items = batches.get('value', [])
        if batch_items:
            batch_id = batch_items[0]['id']
        else:
            batch = self.post(batch_url, data={'displayName': 'DTSG-ERP', 'code': 'DTSG'})
            batch_id = batch.get('id', '')

        # 2. Post each line
        for line in lines:
            line_data = {
                'journalDisplayName': 'DTSG-ERP',
                'lineNumber': line.get('line_number', 10000),
                'accountType': 'G/L Account',
                'accountId': line.get('account_id', ''),
                'accountNumber': str(line.get('account_code', '')),
                'postingDate': header.get('date', ''),
                'documentNumber': str(header.get('reference', ''))[:20],
                'description': line.get('description', '')[:50],
                'debitAmount': float(line.get('debit', 0)),
                'creditAmount': float(line.get('credit', 0)),
            }
            self.post(self._company_path('generalJournalLines'), data=line_data)

        return {'status': 'posted', 'batch_id': batch_id}

    # ---- Vendors ----

    def get_vendors(self) -> list:
        data = self.get(self._company_path('vendors'), params={'$top': 2000})
        return [{
            'name': row.get('displayName', ''),
            'code': row.get('number', ''),
            'email': row.get('email', ''),
            'phone': row.get('phoneNumber', ''),
            'remote_id': row.get('id', ''),
            'remote_system': 'dynamics_365_bc',
        } for row in data.get('value', [])]

    def push_vendor(self, vendor_data: dict) -> dict:
        return self.post(self._company_path('vendors'), data={
            'displayName': vendor_data.get('name', ''),
            'number': vendor_data.get('code', ''),
            'email': vendor_data.get('email', ''),
        })

    # ---- Customers ----

    def get_customers(self) -> list:
        data = self.get(self._company_path('customers'), params={'$top': 2000})
        return [{
            'name': row.get('displayName', ''),
            'code': row.get('number', ''),
            'email': row.get('email', ''),
            'credit_limit': float(row.get('creditLimit', 0) or 0),
            'balance': float(row.get('balance', 0) or 0),
            'remote_id': row.get('id', ''),
            'remote_system': 'dynamics_365_bc',
        } for row in data.get('value', [])]

    # ---- Items ----

    def get_items(self) -> list:
        data = self.get(self._company_path('items'), params={'$top': 2000})
        return [{
            'code': row.get('number', ''),
            'name': row.get('displayName', ''),
            'uom': row.get('baseUnitOfMeasureCode', ''),
            'unit_price': float(row.get('unitPrice', 0) or 0),
            'unit_cost': float(row.get('unitCost', 0) or 0),
            'remote_id': row.get('id', ''),
            'remote_system': 'dynamics_365_bc',
        } for row in data.get('value', [])]

    # ---- Purchase Orders ----

    def get_purchase_orders(self) -> list:
        data = self.get(
            self._company_path('purchaseOrders'),
            params={'$expand': 'purchaseOrderLines', '$top': 1000},
        )
        results = data.get('value', [])
        return [{
            'po_number': row.get('number', ''),
            'vendor_code': row.get('vendorNumber', ''),
            'document_date': row.get('orderDate', ''),
            'status': row.get('status', ''),
            'lines': [
                {
                    'item_code': l.get('lineObjectNumber', ''),
                    'quantity': float(l.get('quantity', 0) or 0),
                    'unit_price': float(l.get('directUnitCost', 0) or 0),
                }
                for l in row.get('purchaseOrderLines', {}).get('value', [])
            ],
            'remote_id': row.get('id', ''),
            'remote_system': 'dynamics_365_bc',
        } for row in results]

    def push_purchase_order(self, po: dict) -> dict:
        """Create Purchase Order in Dynamics 365 BC."""
        payload = {
            'vendorNumber': po.get('vendor_code', ''),
            'orderDate': po.get('order_date', ''),
            'requestedReceiptDate': po.get('delivery_date', ''),
        }
        result = self.post(self._company_path('purchaseOrders'), data=payload)
        po_id = result.get('id', '')
        # Post lines
        for line in po.get('lines', []):
            self.post(self._company_path('purchaseOrderLines'), data={
                'documentId': po_id,
                'lineType': 'Item',
                'lineObjectNumber': line.get('item_code', ''),
                'quantity': float(line.get('quantity', 1)),
                'directUnitCost': float(line.get('unit_price', 0)),
            })
        return result

    # ---- Sales Orders ----

    def get_sales_orders(self) -> list:
        data = self.get(
            self._company_path('salesOrders'),
            params={'$expand': 'salesOrderLines', '$top': 1000},
        )
        return [{
            'so_number': row.get('number', ''),
            'customer_code': row.get('customerNumber', ''),
            'document_date': row.get('orderDate', ''),
            'status': row.get('status', ''),
            'remote_id': row.get('id', ''),
            'remote_system': 'dynamics_365_bc',
        } for row in data.get('value', [])]

    def push_sales_invoice(self, invoice: dict) -> dict:
        """Push a DTSG customer invoice to Dynamics 365 BC as a salesInvoice."""
        payload = {
            'customerNumber': invoice.get('customer_code', ''),
            'invoiceDate': invoice.get('invoice_date', ''),
            'dueDate': invoice.get('due_date', ''),
            'externalDocumentNumber': str(invoice.get('reference', ''))[:20],
        }
        result = self.post(self._company_path('salesInvoices'), data=payload)
        invoice_id = result.get('id', '')
        for line in invoice.get('lines', []):
            self.post(self._company_path('salesInvoiceLines'), data={
                'documentId': invoice_id,
                'lineType': 'Item',
                'lineObjectNumber': line.get('item_code', ''),
                'quantity': float(line.get('quantity', 1)),
                'unitPrice': float(line.get('unit_price', 0)),
            })
        return result

    # ---- Helpers ----

    @staticmethod
    def _map_d365_account_type(category: str) -> str:
        mapping = {
            'Assets': 'asset',
            'Liabilities': 'liability',
            'Equity': 'equity',
            'Income': 'revenue',
            'Cost of Goods Sold': 'expense',
            'Expense': 'expense',
        }
        return mapping.get(category, 'asset')
