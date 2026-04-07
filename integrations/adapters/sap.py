"""
SAP Adapter
===========
Supports SAP S/4HANA via OData v4 and SAP ECC via OData v2/RFC.

Key SAP APIs used:
  GL Accounts  : /sap/opu/odata/sap/API_GL_ACCOUNT_IN_CHART_OF_ACCOUNTS_SRV
  FI Documents : /sap/opu/odata/sap/API_JOURNALENTRYITEMBASIC_SRV
  Vendors      : /sap/opu/odata/sap/API_BUSINESS_PARTNER
  Customers    : /sap/opu/odata/sap/API_BUSINESS_PARTNER
  Purchase Orders : /sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV
  Sales Orders    : /sap/opu/odata/sap/API_SALES_ORDER_SRV
  Materials       : /sap/opu/odata/sap/API_MATERIAL_SRV
  Stock           : /sap/opu/odata/sap/API_MATERIAL_STOCK_SRV

SAP CSRF handshake:
  GET /sap/opu/odata/... with header X-CSRF-Token: Fetch
  Capture X-CSRF-Token from response header
  Use that token in subsequent POST/PUT/PATCH/DELETE requests
"""
import logging

from .base import AdapterError, BaseERPAdapter

logger = logging.getLogger('integrations.sap')


class SAPAdapter(BaseERPAdapter):
    """
    Adapter for SAP S/4HANA (OData) and SAP ECC (OData v2).
    Handles CSRF token negotiation transparently.
    """

    # OData service paths
    GL_ACCOUNTS_SRV = 'sap/opu/odata/sap/API_GL_ACCOUNT_IN_CHART_OF_ACCOUNTS_SRV'
    FI_ITEMS_SRV = 'sap/opu/odata/sap/API_JOURNALENTRYITEMBASIC_SRV'
    BUSINESS_PARTNER_SRV = 'sap/opu/odata/sap/API_BUSINESS_PARTNER'
    PURCHASE_ORDER_SRV = 'sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV'
    SALES_ORDER_SRV = 'sap/opu/odata/sap/API_SALES_ORDER_SRV'
    MATERIAL_SRV = 'sap/opu/odata/sap/API_MATERIAL_SRV'
    MATERIAL_STOCK_SRV = 'sap/opu/odata/sap/API_MATERIAL_STOCK_SRV'
    GOODS_MOVEMENT_SRV = 'sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV'

    def __init__(self, config):
        super().__init__(config)
        self._csrf_token = None
        self._csrf_cookies = None

    def _get_headers(self):
        creds = self.config.credentials or {}
        import base64
        username = creds.get('username', '')
        password = creds.get('password', '')
        raw = f'{username}:{password}'
        encoded = base64.b64encode(raw.encode()).decode()
        headers = {
            'Authorization': f'Basic {encoded}',
            'Accept': 'application/json',
            'sap-client': self.config.sap_client or '100',
        }
        return headers

    def _fetch_csrf_token(self, service_path: str):
        """
        Perform the SAP CSRF handshake for a given OData service.
        Caches the token for the session lifetime.
        """
        import requests as req_lib
        url = f'{self.base_url.rstrip("/")}/{service_path}/'
        session = self._get_session()
        headers = self._get_headers()
        headers['X-CSRF-Token'] = 'Fetch'
        try:
            resp = session.get(url, headers=headers, timeout=15)
            self._csrf_token = resp.headers.get('X-CSRF-Token', '')
            self._csrf_cookies = resp.cookies
            logger.debug('SAP CSRF token fetched: %s', self._csrf_token[:8] + '...' if self._csrf_token else 'None')
        except req_lib.exceptions.RequestException as exc:
            raise AdapterError(f'SAP CSRF handshake failed: {exc}') from exc

    def _mutating_headers(self, service_path: str) -> dict:
        """Return headers with CSRF token for POST/PATCH/DELETE."""
        if not self._csrf_token:
            self._fetch_csrf_token(service_path)
        h = self._get_headers()
        h['X-CSRF-Token'] = self._csrf_token
        h['Content-Type'] = 'application/json'
        return h

    # ---- Connection Test ----

    def test_connection(self) -> bool:
        try:
            self._fetch_csrf_token(self.GL_ACCOUNTS_SRV)
            return bool(self._csrf_token)
        except AdapterError:
            return False

    # ---- Chart of Accounts ----

    def get_gl_accounts(self, chart_of_accounts: str = None) -> list:
        """
        Fetch GL accounts from SAP.
        Maps to DTSG accounting.Account model.
        """
        params = {
            '$format': 'json',
            '$top': 1000,
        }
        if chart_of_accounts:
            params['$filter'] = f"ChartOfAccounts eq '{chart_of_accounts}'"
        data = self.get(f'{self.GL_ACCOUNTS_SRV}/A_GLAccountInChartOfAccounts', params=params)
        results = data.get('d', {}).get('results', [])
        mapped = []
        for row in results:
            mapped.append({
                'code': row.get('GLAccount', '').lstrip('0'),
                'name': row.get('GLAccountName', ''),
                'account_type': self._map_sap_account_type(row.get('GLAccountGroup', '')),
                'is_reconciliation': row.get('IsBalanceSheetAccount', 'X') == 'X',
                'remote_id': row.get('GLAccount', ''),
                'remote_system': 'sap',
            })
        return mapped

    def push_journal_entry(self, journal_header, lines) -> dict:
        """
        Post a DTSG journal entry to SAP FI as a document.
        Uses SAP API_JOURNALENTRYITEMBASIC_SRV (S/4HANA).
        """
        items = []
        for i, line in enumerate(lines, start=1):
            items.append({
                'SequenceNumber': str(i).zfill(6),
                'GLAccount': str(line.get('account_code', '')).zfill(10),
                'AmountInTransactionCurrency': str(abs(line.get('amount', 0))),
                'DebitCreditCode': 'S' if line.get('debit', 0) > 0 else 'H',
                'DocumentItemText': line.get('description', '')[:50],
                'CostCenter': line.get('cost_center', ''),
                'ProfitCenter': line.get('profit_center', ''),
            })
        payload = {
            'CompanyCode': self.config.sap_client or '1000',
            'DocumentDate': journal_header.get('date', '').replace('-', ''),
            'PostingDate': journal_header.get('date', '').replace('-', ''),
            'DocumentReferenceID': str(journal_header.get('reference', ''))[:16],
            'DocumentHeaderText': journal_header.get('description', '')[:25],
            'to_JournalEntryItem': {'results': items},
        }
        headers = self._mutating_headers(self.FI_ITEMS_SRV)
        return self._request('POST', f'{self.FI_ITEMS_SRV}/A_JournalEntry',
                              data=payload, extra_headers=headers)

    # ---- Vendors / Customers (Business Partner) ----

    def get_vendors(self, top: int = 500) -> list:
        params = {
            '$format': 'json',
            '$top': top,
            '$filter': "BusinessPartnerCategory eq '2'",  # 2 = Organization
            '$expand': 'to_BusinessPartnerAddress',
        }
        data = self.get(f'{self.BUSINESS_PARTNER_SRV}/A_BusinessPartner', params=params)
        results = data.get('d', {}).get('results', [])
        return [{
            'name': row.get('BusinessPartnerFullName', ''),
            'code': row.get('BusinessPartner', ''),
            'email': '',
            'remote_id': row.get('BusinessPartner', ''),
            'remote_system': 'sap',
        } for row in results]

    def get_customers(self, top: int = 500) -> list:
        params = {
            '$format': 'json',
            '$top': top,
            '$filter': "BusinessPartnerCategory eq '2'",
            '$expand': 'to_Customer',
        }
        data = self.get(f'{self.BUSINESS_PARTNER_SRV}/A_BusinessPartner', params=params)
        results = data.get('d', {}).get('results', [])
        return [{
            'name': row.get('BusinessPartnerFullName', ''),
            'code': row.get('BusinessPartner', ''),
            'remote_id': row.get('BusinessPartner', ''),
            'remote_system': 'sap',
        } for row in results]

    # ---- Materials / Inventory ----

    def get_materials(self, top: int = 1000) -> list:
        params = {'$format': 'json', '$top': top}
        data = self.get(f'{self.MATERIAL_SRV}/A_Product', params=params)
        results = data.get('d', {}).get('results', [])
        return [{
            'code': row.get('Product', ''),
            'name': row.get('ProductDescription', ''),
            'uom': row.get('BaseUnit', ''),
            'remote_id': row.get('Product', ''),
            'remote_system': 'sap',
        } for row in results]

    def get_stock_levels(self, material: str = None, plant: str = None) -> list:
        params = {'$format': 'json', '$top': 2000}
        if material:
            params['$filter'] = f"Material eq '{material}'"
        if plant:
            params.setdefault('$filter', '')
            if params['$filter']:
                params['$filter'] += f" and Plant eq '{plant}'"
            else:
                params['$filter'] = f"Plant eq '{plant}'"
        data = self.get(f'{self.MATERIAL_STOCK_SRV}/A_MatlStkInAcctMod', params=params)
        results = data.get('d', {}).get('results', [])
        return [{
            'item_code': row.get('Material', ''),
            'warehouse': row.get('Plant', ''),
            'quantity': float(row.get('MaterialBaseQuantity', 0) or 0),
            'remote_system': 'sap',
        } for row in results]

    def post_goods_movement(self, movement_data: dict) -> dict:
        """
        Post goods movement (goods receipt, goods issue) to SAP via
        API_MATERIAL_DOCUMENT_SRV.
        """
        headers = self._mutating_headers(self.GOODS_MOVEMENT_SRV)
        return self._request(
            'POST', f'{self.GOODS_MOVEMENT_SRV}/A_MaterialDocumentHeader',
            data=movement_data, extra_headers=headers,
        )

    # ---- Purchase Orders ----

    def get_purchase_orders(self, top: int = 500) -> list:
        params = {'$format': 'json', '$top': top, '$expand': 'to_PurchaseOrderItem'}
        data = self.get(f'{self.PURCHASE_ORDER_SRV}/A_PurchaseOrder', params=params)
        results = data.get('d', {}).get('results', [])
        return [{
            'po_number': row.get('PurchaseOrder', ''),
            'vendor_code': row.get('Supplier', ''),
            'document_date': row.get('PurchaseOrderDate', ''),
            'status': row.get('ProcessingStatus', ''),
            'lines': [
                {
                    'line_number': l.get('PurchaseOrderItem', ''),
                    'item_code': l.get('Material', ''),
                    'quantity': float(l.get('OrderQuantity', 0) or 0),
                    'unit_price': float(l.get('NetPriceAmount', 0) or 0),
                }
                for l in row.get('to_PurchaseOrderItem', {}).get('results', [])
            ],
            'remote_id': row.get('PurchaseOrder', ''),
            'remote_system': 'sap',
        } for row in results]

    def push_purchase_order(self, po_data: dict) -> dict:
        """Create a Purchase Order in SAP."""
        headers = self._mutating_headers(self.PURCHASE_ORDER_SRV)
        return self._request(
            'POST', f'{self.PURCHASE_ORDER_SRV}/A_PurchaseOrder',
            data=po_data, extra_headers=headers,
        )

    # ---- Sales Orders ----

    def get_sales_orders(self, top: int = 500) -> list:
        params = {'$format': 'json', '$top': top, '$expand': 'to_Item'}
        data = self.get(f'{self.SALES_ORDER_SRV}/A_SalesOrder', params=params)
        results = data.get('d', {}).get('results', [])
        return [{
            'so_number': row.get('SalesOrder', ''),
            'customer_code': row.get('SoldToParty', ''),
            'document_date': row.get('SalesOrderDate', ''),
            'status': row.get('OverallSDProcessStatus', ''),
            'remote_id': row.get('SalesOrder', ''),
            'remote_system': 'sap',
        } for row in results]

    # ---- Helpers ----

    @staticmethod
    def _map_sap_account_type(sap_group: str) -> str:
        """Map SAP GL account group to DTSG account type."""
        mapping = {
            '1': 'asset',
            '2': 'liability',
            '3': 'equity',
            '4': 'revenue',
            '5': 'expense',
            '6': 'expense',
        }
        return mapping.get(str(sap_group)[:1], 'asset')
