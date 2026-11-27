import unittest

import httpx

from talkapp.opencode_direct import DirectClient, server_address


class DirectOpenCodeTests(unittest.TestCase):
    def test_verified_address_only(self):
        self.assertEqual(server_address(' https://host.example:8443/ '), 'https://host.example:8443')
        for invalid in ('http://host.example', 'https://u:p@host.example', 'https://a/auth/connect/123',
                        'https://a?secret=1', 'https://a/#secret', 'https://a:99999'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                server_address(invalid)

    def test_reads_sessions_and_visible_text_only(self):
        def handler(request):
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.host, 'host.example')
            self.assertTrue(request.headers['Authorization'].startswith('Basic '))
            if request.url.path == '/api/info':
                return httpx.Response(200, json={'data': {'version': '2'}})
            if request.url.path == '/api/session':
                return httpx.Response(200, json={'data': [{'id': 'ses_1', 'title': '工程'}]})
            self.assertEqual(request.url.path, '/api/session/ses_1/message')
            return httpx.Response(200, json={'data': [
                {'type': 'assistant', 'content': [{'type': 'reasoning', 'text': 'hidden'}, {'type': 'text', 'text': '完成'}]},
                {'type': 'user', 'text': '继续'},
            ]})

        client = DirectClient('https://host.example', 'test', transport=httpx.MockTransport(handler))
        self.assertEqual(client.sessions(), [('ses_1', '工程')])
        self.assertEqual(client.messages('ses_1'), '我：继续\n\nOpenCode：完成')
        with self.assertRaises(ValueError):
            client.messages('../outside')

    def test_does_not_forward_auth_on_redirect(self):
        seen = []

        def handler(request):
            seen.append(request.url.host)
            return httpx.Response(302, headers={'Location': 'https://other.example/'})

        client = DirectClient('https://host.example', 'test', transport=httpx.MockTransport(handler))
        with self.assertRaisesRegex(ValueError, '重定向'):
            client.sessions()
        self.assertEqual(seen, ['host.example'])
