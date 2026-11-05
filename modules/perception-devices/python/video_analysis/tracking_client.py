"""Service-authenticated business API client; no requests are made on import."""
import json
from urllib import error, parse, request


class BusinessError(Exception):
    def __init__(self, code, retryable=False):
        # Never include response bodies, request headers, or credential-bearing URLs.
        super().__init__(code)
        self.code, self.retryable = code, retryable


class BusinessClient:
    def __init__(self, base_url, service_id, token, timeout=10, opener=None):
        address = parse.urlsplit(base_url)
        if (address.scheme not in ('http', 'https') or not address.hostname
                or address.username or address.password or address.query or address.fragment):
            raise ValueError('Business API URL must be an HTTP(S) URL without credentials or query')
        self.base = base_url.rstrip('/')
        self.headers = {'Content-Type': 'application/json', 'X-HXJM-Service-Id': service_id,
                        'X-HXJM-Service-Token': token}
        # Do not forward the service credential to a redirected host or through an env proxy.
        class NoRedirect(request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        self.opener = opener or request.build_opener(request.ProxyHandler({}), NoRedirect())
        self.timeout = timeout

    def call(self, path, body=None):
        if not path.startswith('/') or path.startswith('//'):
            raise ValueError('Expected a relative business operation path')
        data = None if body is None else json.dumps(body, allow_nan=False, separators=(',', ':')).encode()
        req = request.Request(self.base + path, data=data, headers=self.headers,
                              method='GET' if body is None else 'POST')
        status = 200
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
        except error.HTTPError as exc:
            status = exc.code
            try:
                raw = exc.read(4 * 1024 * 1024 + 1)
            finally:
                exc.close()
        except (error.URLError, TimeoutError, OSError):
            raise BusinessError('TRANSPORT_UNAVAILABLE', True) from None
        if len(raw) > 4 * 1024 * 1024:
            raise BusinessError('INVALID_RESPONSE', True)
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError):
            raise BusinessError('INVALID_RESPONSE', status >= 500) from None
        if not isinstance(result, dict):
            raise BusinessError('INVALID_RESPONSE')
        if isinstance(result.get('error'), dict):
            failure = result['error']
            code = failure.get('code', 'BUSINESS_ERROR')
            if not isinstance(code, str) or not code.replace('_', '').isalnum() or len(code) > 64:
                code = 'BUSINESS_ERROR'
            raise BusinessError(code, failure.get('retryable') is True)
        if status >= 300 or 'code' in result:
            # A legacy AjaxResult or login page is not a reliable business acknowledgement.
            raise BusinessError('HTTP_' + str(status), status >= 500 or status == 429)
        return result
