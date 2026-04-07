"""
Base Adapter
============
All ERP adapters inherit from BaseERPAdapter.
Provides: request session management, auth headers, retry logic, logging.
"""
import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from django.utils import timezone

logger = logging.getLogger('integrations.adapter')


class AdapterError(Exception):
    """Raised when an adapter operation fails unrecoverably."""
    def __init__(self, message: str, status_code: int = None, response_body: str = ''):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class BaseERPAdapter(ABC):
    """
    Base class for all ERP / 3rd-party adapters.

    Subclasses must implement:
        _get_headers()      -> dict of HTTP headers for this system
        test_connection()   -> bool
    """

    def __init__(self, config):
        """
        :param config: IntegrationConfig model instance
        """
        self.config = config
        self.base_url = config.base_url.rstrip('/') + '/'
        self._session = None  # lazy-init per request

    def _get_session(self):
        """Lazy-init a requests.Session."""
        import requests
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def _get_headers(self) -> Dict[str, str]:
        """Return auth headers. Override per adapter."""
        creds = self.config.credentials or {}
        method = self.config.auth_method
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if method == 'bearer':
            headers['Authorization'] = f'Bearer {creds.get("token", "")}'
        elif method == 'api_key':
            header_name = creds.get('header_name', 'X-Api-Key')
            headers[header_name] = creds.get('key', '')
        elif method == 'basic':
            import base64
            raw = f'{creds.get("username","")}:{creds.get("password","")}'
            encoded = base64.b64encode(raw.encode()).decode()
            headers['Authorization'] = f'Basic {encoded}'
        return headers

    def _request(
        self, method: str, path: str,
        params: Dict = None, data: Any = None,
        extra_headers: Dict = None, timeout: int = 30,
        retries: int = None,
    ) -> Any:
        """
        Make an HTTP request, with retry on 429/5xx.
        Returns parsed JSON or raises AdapterError.
        """
        import requests as req_lib
        if retries is None:
            retries = self.config.max_retries

        url = urljoin(self.base_url, path.lstrip('/'))
        headers = self._get_headers()
        if extra_headers:
            headers.update(extra_headers)

        session = self._get_session()
        attempt = 0
        backoff = self.config.retry_backoff_seconds

        while attempt <= retries:
            try:
                response = session.request(
                    method.upper(), url,
                    headers=headers,
                    params=params,
                    json=data if method.upper() != 'GET' else None,
                    timeout=timeout,
                )
                if response.status_code == 401:
                    raise AdapterError('Authentication failed', 401, response.text)
                if response.status_code == 403:
                    raise AdapterError('Forbidden', 403, response.text)
                if response.status_code == 404:
                    raise AdapterError(f'Not found: {url}', 404, response.text)
                if response.status_code == 422:
                    raise AdapterError('Validation error', 422, response.text)
                if response.status_code in (429, 503) and attempt < retries:
                    retry_after = int(response.headers.get('Retry-After', backoff))
                    logger.warning('Rate-limited by %s, retry in %ds', url, retry_after)
                    time.sleep(retry_after)
                    attempt += 1
                    continue
                if response.status_code >= 500 and attempt < retries:
                    logger.warning('Server error %d from %s, retry in %ds', response.status_code, url, backoff)
                    time.sleep(backoff)
                    attempt += 1
                    backoff *= 2
                    continue
                if not response.ok:
                    raise AdapterError(
                        f'HTTP {response.status_code} from {url}',
                        response.status_code, response.text,
                    )
                # Empty body (204 No Content)
                if not response.content:
                    return {}
                try:
                    return response.json()
                except ValueError:
                    return {'raw': response.text}
            except req_lib.exceptions.ConnectionError as exc:
                if attempt < retries:
                    time.sleep(backoff)
                    attempt += 1
                    backoff *= 2
                    continue
                raise AdapterError(f'Connection error: {exc}') from exc
            except req_lib.exceptions.Timeout as exc:
                raise AdapterError(f'Timeout calling {url}') from exc

        raise AdapterError(f'Exhausted {retries} retries for {url}')

    def get(self, path, params=None, **kwargs):
        return self._request('GET', path, params=params, **kwargs)

    def post(self, path, data=None, **kwargs):
        return self._request('POST', path, data=data, **kwargs)

    def patch(self, path, data=None, **kwargs):
        return self._request('PATCH', path, data=data, **kwargs)

    def put(self, path, data=None, **kwargs):
        return self._request('PUT', path, data=data, **kwargs)

    def delete(self, path, **kwargs):
        return self._request('DELETE', path, **kwargs)

    @abstractmethod
    def test_connection(self) -> bool:
        """Return True if the remote connection is healthy."""
        ...

    def apply_field_mappings(self, module: str, dtsg_data: dict, direction: str = 'outbound') -> dict:
        """
        Transform a DTSG record dict using saved FieldMapping rules.
        direction: 'outbound' maps DTSG -> remote; 'inbound' maps remote -> DTSG.
        """
        from integrations.models import FieldMapping, SyncDirection
        mappings = self.config.field_mappings.filter(
            module=module,
            direction__in=[direction, SyncDirection.BIDIRECTIONAL],
        )
        result = dict(dtsg_data)
        for m in mappings:
            src = m.dtsg_field if direction == 'outbound' else m.remote_field
            dst = m.remote_field if direction == 'outbound' else m.dtsg_field
            if src in result:
                result[dst] = m.apply(result.pop(src))
            elif m.default_value:
                result[dst] = m.default_value
        return result
