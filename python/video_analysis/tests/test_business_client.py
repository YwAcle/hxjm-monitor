import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from video_analysis.business_client import BusinessClient, BusinessRequestError, BusinessUnavailable


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class BusinessClientTests(unittest.TestCase):
    def client(self, token_provider=lambda: 'fixture-token'):
        client = BusinessClient('http://127.0.0.1:18080/api/v1/business',
                                service_id='fixture-tracker', token_provider=token_provider)
        client._opener = Mock()
        return client

    def test_flat_response_current_credentials_and_stable_request(self):
        token = {'value': 'first-fixture-token'}
        client = self.client(lambda: token['value'])
        client._opener.open.side_effect = [Response(b'{"stream_session_id":"session","duplicate":false}'),
                                           Response(b'{"stream_session_id":"session","duplicate":true}')]
        payload = {'request_id': 'same-request', 'stream_session_id': 'session'}
        self.assertFalse(client.open_session(payload)['duplicate'])
        token['value'] = 'second-fixture-token'
        self.assertTrue(client.open_session(payload)['duplicate'])
        requests = [call.args[0] for call in client._opener.open.call_args_list]
        self.assertEqual(requests[0].full_url,
                         'http://127.0.0.1:18080/api/v1/business/streams/open')
        self.assertEqual(requests[0].data, requests[1].data)
        self.assertEqual(json.loads(requests[0].data), payload)
        for request, expected_token in zip(requests, ('first-fixture-token', 'second-fixture-token')):
            headers = {key.lower(): value for key, value in request.header_items()}
            self.assertEqual(headers['x-hxjm-service-id'], 'fixture-tracker')
            self.assertEqual(headers['x-hxjm-service-token'], expected_token)
            self.assertEqual(request.get_method(), 'POST')

    def test_invalid_configuration_and_missing_token_do_not_send(self):
        for base in ('http://user:secret@localhost/api/v1/business',
                     'https://localhost/api/v1/business?token=secret',
                     'https://localhost/other', 'file:///api/v1/business'):
            with self.subTest(base=base), self.assertRaises(ValueError):
                BusinessClient(base, service_id='fixture', token_provider=lambda: 'fixture-token')
        for token in ('', '   ', 'fixture\nsecret', None):
            client = self.client(lambda: token)
            with self.subTest(token=repr(token)), self.assertRaises(BusinessRequestError):
                client.create_task({'request_id': 'fixture'})
            client._opener.open.assert_not_called()

    def test_http_errors_distinguish_rejected_and_retryable_without_exposing_body(self):
        for status, retryable, expected in ((409, False, BusinessRequestError),
                                             (503, True, BusinessUnavailable)):
            client = self.client()
            body = json.dumps({'error': {'code': 'FIXTURE_ERROR', 'message': 'private-file-or-token',
                                         'retryable': retryable}}).encode()
            client._opener.open.side_effect = HTTPError(
                'http://private-url.invalid', status, 'private-message', {}, io.BytesIO(body))
            with self.subTest(status=status), self.assertRaises(expected) as raised:
                client.create_task({'request_id': 'fixture'})
            self.assertEqual(raised.exception.code, 'FIXTURE_ERROR')
            self.assertEqual(raised.exception.status, status)
            self.assertEqual(raised.exception.retryable, retryable)
            self.assertNotIn('private', str(raised.exception))

    def test_network_failure_and_unstructured_gateway_failure_can_retry(self):
        for error in (URLError('private-network-detail'),
                      HTTPError('http://private-url.invalid', 502, 'private-message', {},
                                io.BytesIO(b'upstream not ready'))):
            client = self.client()
            client._opener.open.side_effect = error
            with self.assertRaises(BusinessUnavailable) as raised:
                client.create_task({'request_id': 'fixture'})
            self.assertNotIn('private', str(raised.exception))

    def test_invalid_success_or_oversized_response_is_never_an_acknowledgement(self):
        for raw in (b'[]', b'not json', b'{"error":{"code":"NO"}}', b' ' * 32):
            client = self.client()
            client._opener.open.return_value = Response(raw)
            with self.subTest(raw=raw), patch.object(BusinessClient, 'MAX_RESPONSE_BYTES', 16), \
                    self.assertRaises(BusinessRequestError):
                client.start_task({'request_id': 'fixture'})

    def test_submit_rejects_actor_or_operation_changes(self):
        client = self.client()
        for actor, operation in (('service:another', 'results.register'),
                                 (client.actor_key, 'assets.register')):
            with self.assertRaises(BusinessRequestError):
                client.submit(actor, operation, {'request_id': 'fixture'})
        client._opener.open.assert_not_called()

    def test_recording_uses_the_existing_asset_registration_route(self):
        client = self.client()
        client._opener.open.return_value = Response(b'{"asset_id":"fixture","state":"available"}')
        client.register_asset({'request_id': 'asset-fixture'})
        request = client._opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'http://127.0.0.1:18080/api/v1/business/assets/register')

    def test_redirect_handler_does_not_forward_service_credentials(self):
        from video_analysis.business_client import _NoRedirect
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, '', {},
                                                        'https://different.example.invalid'))

    def test_image_upload_and_content_keep_service_authentication(self):
        client = self.client()
        client._opener.open.return_value = Response(b'{"asset_id":"fixture"}')
        client.upload_image({'request_id': 'image-request', 'purpose': 'history'}, b'fixture-image')
        request = client._opener.open.call_args.args[0]
        self.assertTrue(request.full_url.endswith('/assets/upload'))
        self.assertIn(b'name="file"', request.data)
        self.assertIn(b'image-request', request.data)
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers['x-hxjm-service-id'], 'fixture-tracker')
        self.assertTrue(headers['content-type'].startswith('multipart/form-data; boundary='))
        client._opener.open.return_value = Response(b'fixture-image')
        self.assertEqual(client.image_content('10000000-0000-4000-8000-000000000001'), b'fixture-image')
        self.assertEqual(client._opener.open.call_args.args[0].get_method(), 'GET')


if __name__ == '__main__':
    unittest.main()
