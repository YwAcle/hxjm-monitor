"""Explicit service-authenticated calls to the v0.2 business API."""
import json
import math
import re
import socket
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class BusinessRequestError(ValueError):
    """An invalid or rejected request must not be retried without correction."""
    retryable = False

    def __init__(self, code, status=None):
        self.code, self.status = code, status
        super().__init__(f'Business API {code}' + (f' (HTTP {status})' if status else ''))


class BusinessUnavailable(RuntimeError):
    """The immutable request can be submitted again after the dependency recovers."""
    retryable = True

    def __init__(self, code='DEPENDENCY_UNAVAILABLE', status=None):
        self.code, self.status = code, status
        super().__init__(f'Business API {code}' + (f' (HTTP {status})' if status else ''))


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        # Service credentials must never follow a redirect to another host.
        return None


def image_multipart(fields, image):
    """Encode the existing image API's scalar form fields and JPEG file."""
    if not isinstance(image, bytes) or not 0 < len(image) <= 10 * 1024 * 1024:
        raise ValueError('Image upload requires 1 byte to 10 MiB')
    boundary = 'hxjm-' + uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        if not isinstance(name, str) or re.fullmatch(r'[a-z_][a-z_0-9]*', name) is None:
            raise ValueError('Invalid multipart field name')
        if not isinstance(value, str):
            raise ValueError('Multipart fields must be strings')
        parts.append(('--' + boundary + '\r\nContent-Disposition: form-data; name="'
                      + name + '"\r\n\r\n' + value + '\r\n').encode('utf-8'))
    parts.extend([('--' + boundary + '\r\nContent-Disposition: form-data; name="file"; '
                   'filename="sample.jpg"\r\nContent-Type: image/jpeg\r\n\r\n').encode('ascii'),
                  image, ('\r\n--' + boundary + '--\r\n').encode('ascii')])
    return b''.join(parts), 'multipart/form-data; boundary=' + boundary


class BusinessClient:
    """base_url includes /api/v1/business; construction does not contact a server."""
    MAX_RESPONSE_BYTES = 4 * 1024 * 1024

    def __init__(self, base_url, *, service_id, token_provider, timeout=5):
        if not isinstance(base_url, str):
            raise ValueError('Business API URL must be explicit')
        parts = urlsplit(base_url)
        if (parts.scheme not in ('http', 'https') or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment
                or parts.path.rstrip('/') != '/api/v1/business'):
            raise ValueError('Business API URL must end in /api/v1/business without credentials or query')
        if (not isinstance(service_id, str)
                or re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}', service_id) is None):
            raise ValueError('A valid business service ID is required')
        if not callable(token_provider):
            raise ValueError('token_provider must supply the current service token')
        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout) or timeout <= 0):
            raise ValueError('Business API timeout must be positive')
        self.base_url = base_url.rstrip('/')
        self.service_id = service_id
        self.actor_key = 'service:' + service_id
        self._token_provider = token_provider
        self.timeout = timeout
        self._opener = build_opener(_NoRedirect())

    def post(self, path, payload):
        if not isinstance(payload, dict):
            raise ValueError('Business request must be a JSON object')
        data = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
        return self._request('POST', path, data, 'application/json')

    def get(self, path, parameters=None):
        return self._request('GET', path, parameters=parameters)

    def _request(self, method, path, data=None, content_type=None, parameters=None, raw_image=False):
        if (not isinstance(path, str) or not path.startswith('/') or path.startswith('//')
                or '?' in path or '#' in path or '..' in path):
            raise ValueError('Business operation requires a relative API path')
        token = self._token_provider()
        if not isinstance(token, str) or not token.strip() or '\r' in token or '\n' in token:
            raise BusinessRequestError('MISSING_SERVICE_TOKEN')
        headers = {
            'Accept': 'application/json',
            'X-HXJM-Service-Id': self.service_id, 'X-HXJM-Service-Token': token,
        }
        if content_type is not None:
            headers['Content-Type'] = content_type
        query = '' if not parameters else '?' + urlencode(parameters)
        request = Request(self.base_url + path + query, data=data, method=method, headers=headers)
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                if raw_image:
                    image = response.read(10 * 1024 * 1024 + 1)
                    if not 0 < len(image) <= 10 * 1024 * 1024:
                        raise BusinessRequestError('INVALID_IMAGE_RESPONSE')
                    return image
                result = self._decode(response.read(self.MAX_RESPONSE_BYTES + 1))
        except HTTPError as error:
            try:
                body = self._decode(error.read(self.MAX_RESPONSE_BYTES + 1))
            except BusinessRequestError:
                body = {}
            finally:
                error.close()
            failure = body.get('error', {})
            if not isinstance(failure, dict):
                failure = {}
            code = failure.get('code')
            if not isinstance(code, str) or re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', code) is None:
                code = 'HTTP_ERROR'
            exception = BusinessUnavailable if failure.get('retryable') is True else BusinessRequestError
            if 'retryable' not in failure and error.code in (408, 429, 502, 503, 504):
                exception = BusinessUnavailable
            raise exception(code, error.code) from None
        except (URLError, socket.timeout, TimeoutError, OSError):
            raise BusinessUnavailable() from None
        if 'error' in result:
            raise BusinessRequestError('INVALID_SUCCESS_RESPONSE')
        return result

    @classmethod
    def _decode(cls, raw):
        if len(raw) > cls.MAX_RESPONSE_BYTES:
            raise BusinessRequestError('RESPONSE_TOO_LARGE')
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError):
            raise BusinessRequestError('INVALID_JSON_RESPONSE') from None
        if not isinstance(result, dict):
            raise BusinessRequestError('INVALID_JSON_RESPONSE')
        return result

    def open_session(self, payload):
        return self.post('/streams/open', payload)

    def close_session(self, payload):
        return self.post('/streams/close', payload)

    def create_task(self, payload):
        return self.post('/tasks', payload)

    def start_task(self, payload):
        return self.post('/tasks/start', payload)

    def register_asset(self, payload):
        return self.post('/assets/register', payload)

    def upload_image(self, fields, image):
        data, content_type = image_multipart(fields, image)
        return self._request('POST', '/assets/upload', data, content_type)

    def image_content(self, asset_id):
        if str(uuid.UUID(asset_id)) != asset_id:
            raise ValueError('Canonical asset UUID required')
        return self._request('GET', '/assets/' + asset_id + '/content', raw_image=True)

    def register_sample(self, payload):
        return self.post('/samples/register', payload)

    def register_feature_space(self, payload):
        return self.post('/feature-spaces/register', payload)

    def register_feature(self, payload):
        return self.post('/features/register', payload)

    def associate_identity(self, payload):
        return self.post('/identities/associate', payload)

    def finish_task(self, payload):
        return self.post('/tasks/finish', payload)

    def submit(self, actor_key, operation, payload):
        if actor_key != self.actor_key or operation != 'results.register':
            raise BusinessRequestError('REQUEST_ACTOR_OR_OPERATION_MISMATCH')
        return self.post('/results/register', payload)
