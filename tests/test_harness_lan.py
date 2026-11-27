import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from talkapp import harness_lan, lan_pairing, harness_collaboration
from talkapp.pairing_qr import validate_invitation


class HarnessLanTests(unittest.TestCase):
    def test_configure_accepts_unwrapped_opencode_info(self):
        address = lan_pairing.local_address()
        if not address:
            self.skipTest('No private IPv4 interface')
        with tempfile.TemporaryDirectory() as tmp, \
                patch('talkapp.opencode_tasks.executable', return_value='opencode'), \
                patch('talkapp.opencode_tasks.api', return_value={'version': '2.4.2'}) as api:
            root = Path(tmp)
            phone = root / 'phone'
            phone.mkdir()
            host = harness_lan.HarnessHost(root, address, root, port=0)
            try:
                harness_lan.pair(phone, host.invitation())
                harness_lan.configure(phone)
                self.assertIs(harness_collaboration.observe(phone, 'a' * 32, 1, [['user', '测试']]), True)
                api.assert_called_once_with('opencode', 'get', '/api/info', None, timeout=8)
            finally:
                host.close()
                host.worker.join(4)

    def test_phone_conversation_scopes_are_separate(self):
        self.assertEqual(harness_collaboration.scope('phone', 1), harness_collaboration.scope('phone', 1))
        self.assertNotEqual(harness_collaboration.scope('phone', 1), harness_collaboration.scope('phone', 2))
        self.assertNotEqual(harness_collaboration.scope('phone', 1), harness_collaboration.scope('other', 1))

    def test_authenticated_chat_reuses_session_and_does_not_repeat_ambiguous_send(self):
        address = lan_pairing.local_address()
        if not address:
            self.skipTest('No private IPv4 interface')
        calls = []

        def request(method, path, body=None):
            calls.append((method, path, body))
            if path == '/api/session':
                return {'id': 'ses_test'}
            if path.endswith('/prompt'):
                if body['text'] == 'ambiguous':
                    raise OSError('lost response')
                return {}
            if path.endswith('/permission'):
                return [{'id': 'perm_test', 'sessionID': 'ses_test', 'permission': 'test'}]
            if path.endswith('/reply'):
                return {}
            return [{'type': 'user', 'text': 'test'}]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('host', 'phone', 'unknown'):
                (root / name).mkdir()
            host = harness_lan.HarnessHost(root / 'host', address, root, port=0, request=request)
            try:
                phone = root / 'phone'
                code = host.invitation()
                with self.assertRaises(ValueError):
                    validate_invitation(code, lan_pairing.PREFIX)
                harness_lan.pair(phone, validate_invitation(code, harness_lan.PREFIX))
                with self.assertRaises(ValueError):
                    harness_lan.pair(root / 'unknown', code)
                scope = 'c' * 32
                with self.assertRaises(ValueError):
                    harness_lan.call(phone, 'read', scope=scope)
                self.assertFalse(harness_lan.call(phone, 'configure', manifest={'protocol': 99})['configured'])
                harness_lan.configure(phone)
                harness_lan.configure(phone)
                self.assertEqual(calls, [('get', '/api/info', None)])
                self.assertIs(harness_lan.call(phone, 'observe', scope=scope, revision=2,
                                               rows=[['user', '背景']]), True)
                harness_lan.call(phone, 'observe', scope=scope, revision=1, rows=[['user', '过时背景']])
                self.assertEqual(lan_pairing._load(root / 'host' / f'chat-{scope}.json')['observed'], [['user', '背景']])
                self.assertEqual(calls, [('get', '/api/info', None)])
                self.assertIs(harness_lan.call(phone, 'send', id='a' * 32, text='test'), True)
                self.assertIs(harness_lan.call(phone, 'send', id='a' * 32, text='test'), True)
                for _ in range(2):
                    with self.assertRaises(ValueError):
                        harness_lan.call(phone, 'send', id='b' * 32, text='ambiguous')
                self.assertEqual(harness_lan.call(phone, 'read')['lines'], [['我', 'test']])
                with self.assertRaises(ValueError):
                    harness_lan.call(phone, 'decision', request_id='other', decision='once')
                self.assertIs(harness_lan.call(phone, 'decision', request_id='perm_test', decision='reject'), True)
                self.assertEqual([path for method, path, _ in calls if method == 'post'],
                                 ['/api/session', '/api/session/ses_test/prompt', '/api/session/ses_test/prompt',
                                  '/api/session/ses_test/permission/perm_test/reply'])
                host.forget()
                with self.assertRaises(ValueError):
                    harness_lan.call(phone, 'read')
            finally:
                host.close()
                host.worker.join(4)
