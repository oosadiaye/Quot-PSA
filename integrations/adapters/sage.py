"""
Sage Adapter
============
Supports:
  - Sage Intacct   (XML/HTTPS API — unique among major ERPs)
  - Sage 200 Cloud (REST API)
  - Sage X3        (REST API via Web Services)

Sage Intacct uses an XML-over-HTTPS request model with session authentication.
Each API call wraps a <function> element in an XML <request> envelope.
"""
import logging
import xml.etree.ElementTree as ET

from .base import AdapterError, BaseERPAdapter

logger = logging.getLogger('integrations.sage')


# ---------------------------------------------------------------------------
# Sage Intacct
# ---------------------------------------------------------------------------

class SageIntacctAdapter(BaseERPAdapter):
    """
    Adapter for Sage Intacct XML API.
    Ref: https://developer.intacct.com/api/
    """

    ENDPOINT = 'https://api.intacct.com/ia/xml/xmlgw.phtml'

    def __init__(self, config):
        super().__init__(config)
        self._session_id = None

    def _build_envelope(self, functions: list, authenticated: bool = True) -> str:
        """
        Build Sage Intacct XML request envelope.
        :param functions: list of ET.Element <function> elements
        """
        creds = self.config.credentials or {}
        root = ET.Element('request')

        ctrl = ET.SubElement(root, 'control')
        ET.SubElement(ctrl, 'senderid').text = creds.get('sender_id', '')
        ET.SubElement(ctrl, 'password').text = creds.get('sender_password', '')
        ET.SubElement(ctrl, 'controlid').text = 'dtsg_erp'
        ET.SubElement(ctrl, 'uniqueid').text = 'false'
        ET.SubElement(ctrl, 'dtdversion').text = '3.0'
        ET.SubElement(ctrl, 'includewhitespace').text = 'false'

        op = ET.SubElement(root, 'operation')
        ET.SubElement(op, 'authentication')

        if authenticated and self._session_id:
            auth = op.find('authentication')
            ET.SubElement(auth, 'sessionid').text = self._session_id
        else:
            auth = op.find('authentication')
            login = ET.SubElement(auth, 'login')
            ET.SubElement(login, 'userid').text = creds.get('user_id', '')
            ET.SubElement(login, 'companyid').text = self.config.sage_company_id or creds.get('company_id', '')
            ET.SubElement(login, 'password').text = creds.get('password', '')

        content = ET.SubElement(op, 'content')
        for fn in functions:
            content.append(fn)

        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='unicode')

    def _send_xml(self, xml_body: str) -> ET.Element:
        """POST XML envelope, return parsed response root."""
        import requests as req_lib
        try:
            resp = req_lib.post(
                self.ENDPOINT,
                data=xml_body.encode('utf-8'),
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=30,
            )
            if not resp.ok:
                raise AdapterError(f'Sage Intacct HTTP error {resp.status_code}', resp.status_code, resp.text)
            root = ET.fromstring(resp.text)
            status = root.findtext('./operation/result/status')
            if status != 'success':
                errmsgs = root.findall('./operation/result/errormessage/error/description')
                err = '; '.join(e.text or '' for e in errmsgs) if errmsgs else 'Unknown error'
                raise AdapterError(f'Sage Intacct API error: {err}')
            return root
        except req_lib.exceptions.RequestException as exc:
            raise AdapterError(f'Sage Intacct connection failed: {exc}') from exc

    def _get_session(self):
        """Authenticate and cache session ID."""
        if self._session_id:
            return self._session_id
        fn = ET.Element('function', controlid='getSession')
        ET.SubElement(fn, 'getAPISession')
        xml = self._build_envelope([fn], authenticated=False)
        root = self._send_xml(xml)
        self._session_id = root.findtext('./operation/result/data/api/sessionid')
        return self._session_id

    # ---- Connection Test ----

    def test_connection(self) -> bool:
        try:
            self._get_session()
            return bool(self._session_id)
        except AdapterError:
            return False

    # ---- GL Accounts ----

    def get_gl_accounts(self) -> list:
        self._get_session()
        fn = ET.Element('function', controlid='getGLAccounts')
        query = ET.SubElement(fn, 'query')
        ET.SubElement(query, 'object').text = 'GLACCOUNT'
        ET.SubElement(query, 'select').text = '<field>ACCOUNTNO</field><field>TITLE</field><field>ACCOUNTTYPE</field>'
        ET.SubElement(query, 'pagesize').text = '2000'
        xml = self._build_envelope([fn])
        root = self._send_xml(xml)
        accounts = []
        for item in root.findall('./operation/result/data/GLACCOUNT'):
            accounts.append({
                'code': item.findtext('ACCOUNTNO', ''),
                'name': item.findtext('TITLE', ''),
                'account_type': self._map_intacct_type(item.findtext('ACCOUNTTYPE', '')),
                'remote_id': item.findtext('ACCOUNTNO', ''),
                'remote_system': 'sage_intacct',
            })
        return accounts

    def push_journal_entry(self, header: dict, lines: list) -> dict:
        """Create a GL journal entry in Sage Intacct."""
        self._get_session()
        fn = ET.Element('function', controlid='createJournal')
        create = ET.SubElement(fn, 'create_gltransaction')
        ET.SubElement(create, 'journalid').text = 'GJ'
        ET.SubElement(create, 'datecreated').text = self._intacct_date(header.get('date', ''))
        ET.SubElement(create, 'description').text = header.get('description', '')[:100]
        ET.SubElement(create, 'referenceno').text = str(header.get('reference', ''))[:20]
        items_el = ET.SubElement(create, 'gltransactionentries')
        for line in lines:
            item = ET.SubElement(items_el, 'glentry')
            ET.SubElement(item, 'trtype').text = 'debit' if float(line.get('debit', 0)) > 0 else 'credit'
            ET.SubElement(item, 'amount').text = str(abs(float(line.get('debit', 0) or line.get('credit', 0))))
            ET.SubElement(item, 'glaccountno').text = str(line.get('account_code', ''))
            ET.SubElement(item, 'memo').text = line.get('description', '')[:100]
        xml = self._build_envelope([fn])
        root = self._send_xml(xml)
        return {'status': 'posted', 'key': root.findtext('./operation/result/key', '')}

    # ---- Vendors ----

    def get_vendors(self) -> list:
        self._get_session()
        fn = ET.Element('function', controlid='getVendors')
        query = ET.SubElement(fn, 'query')
        ET.SubElement(query, 'object').text = 'VENDOR'
        ET.SubElement(query, 'select').text = '<field>VENDORID</field><field>NAME</field><field>EMAIL1</field>'
        ET.SubElement(query, 'pagesize').text = '2000'
        xml = self._build_envelope([fn])
        root = self._send_xml(xml)
        return [{
            'code': v.findtext('VENDORID', ''),
            'name': v.findtext('NAME', ''),
            'email': v.findtext('EMAIL1', ''),
            'remote_id': v.findtext('VENDORID', ''),
            'remote_system': 'sage_intacct',
        } for v in root.findall('./operation/result/data/VENDOR')]

    # ---- Helpers ----

    @staticmethod
    def _intacct_date(date_str: str) -> str:
        """Convert ISO date string to Sage Intacct MM/DD/YYYY format."""
        if not date_str:
            return ''
        try:
            from datetime import datetime
            d = datetime.strptime(str(date_str)[:10], '%Y-%m-%d')
            return d.strftime('%m/%d/%Y')
        except ValueError:
            return date_str

    @staticmethod
    def _map_intacct_type(t: str) -> str:
        mapping = {
            'balancesheet': 'asset',
            'incomestatement': 'expense',
        }
        return mapping.get(t.lower(), 'asset') if t else 'asset'


# ---------------------------------------------------------------------------
# Sage 200 Cloud
# ---------------------------------------------------------------------------

class Sage200Adapter(BaseERPAdapter):
    """Adapter for Sage 200 Cloud REST API."""

    def _get_headers(self) -> dict:
        creds = self.config.credentials or {}
        return {
            'Authorization': f'Bearer {creds.get("access_token", "")}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

    def test_connection(self) -> bool:
        try:
            self.get('api/resources')
            return True
        except AdapterError:
            return False

    def get_nominal_accounts(self) -> list:
        data = self.get('api/nominal/ledgerAccounts', params={'$top': 2000})
        return [{
            'code': str(row.get('nominalCode', '')),
            'name': row.get('name', ''),
            'remote_id': str(row.get('id', '')),
            'remote_system': 'sage_200',
        } for row in data.get('$resources', [])]

    def get_suppliers(self) -> list:
        data = self.get('api/purchase/suppliers', params={'$top': 2000})
        return [{
            'code': row.get('supplierAccountNumber', ''),
            'name': row.get('name', ''),
            'email': row.get('email', ''),
            'remote_id': str(row.get('id', '')),
            'remote_system': 'sage_200',
        } for row in data.get('$resources', [])]

    def get_customers(self) -> list:
        data = self.get('api/sales/customers', params={'$top': 2000})
        return [{
            'code': row.get('customerAccountNumber', ''),
            'name': row.get('name', ''),
            'email': row.get('email', ''),
            'remote_id': str(row.get('id', '')),
            'remote_system': 'sage_200',
        } for row in data.get('$resources', [])]
