import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from talkapp import chat_sync, lan_opencode, lan_pairing
from talkapp.storage import History


class LanOpenCodeTests(unittest.TestCase):
    def test_only_exact_model_decision_delegates(self):
        self.assertTrue(lan_opencode.should_delegate('DELEGATE\n'))
        self.assertFalse(lan_opencode.should_delegate('CHAT'))
        self.assertFalse(lan_opencode.should_delegate('Do not DELEGATE'))

    def test_old_manual_requests_are_never_auto_claimed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'history.db'
            with self.subTest('explicit opt-in and pairing required'):
                (root / 'lan-phone.json').touch()
                self.assertFalse(lan_opencode.enabled(root, False))
                lan_opencode.set_enabled(root, True)
                self.assertTrue(lan_opencode.enabled(root, False))
                self.assertFalse(lan_opencode.enabled(root, True))
            store = History(path)
            try:
                mid = store.append(store.create(), 'user', '旧请求')
                with store.db:
                    store.db.execute("INSERT INTO lan_opencode VALUES (?,'pending')", (mid,))
                self.assertEqual(lan_opencode.pending(store.db), [])
                self.assertIsNone(lan_opencode.claim(path, mid))
            finally:
                store.close()

    def test_live_lan_request_approval_and_result_round_trip(self):
        with tempfile.TemporaryDirectory() as pc, tempfile.TemporaryDirectory() as phone, \
                patch.object(lan_pairing, 'lan_address', side_effect=lambda address: address), \
                patch('talkapp.engineering_assistant.consult', return_value='答案是 3 mA') as assistant:
            desktop, mobile = [History(Path(folder) / 'history.db') for folder in (pc, phone)]
            host = lan_pairing.PairingHost(pc, '127.0.0.1', port=0)
            try:
                chat = mobile.create()
                mobile.append(chat, 'user', '请 OpenCode 看旧消息')
                mobile.append(chat, 'assistant', '这是普通聊天')
                text = '请 OpenCode 复核 LED 电流'
                original = mobile.append(chat, 'user', text, lan_opencode=True)
                lan_pairing.pair(phone, host.invitation())
                host.sync_enabled = True
                lan_pairing.sync(phone)
                lan_pairing.sync(phone)
                (request,) = lan_opencode.pending(desktop.db)
                assistant.assert_not_called()
                path = Path(pc) / 'history.db'
                self.assertEqual(lan_opencode.claim(path, request['id']), text)
                self.assertIsNone(lan_opencode.claim(path, request['id']))
                lan_opencode.progress_note(path, request['id'], '电脑已接单')
                lan_opencode.progress_note(path, request['id'], 'OpenCode 执行中')
                lan_pairing.sync(phone)
                self.assertEqual([row['text'] for row in mobile.path(chat)[-2:]], ['电脑已接单', 'OpenCode 执行中'])
                self.assertEqual(lan_opencode.retry_choices(mobile.db, chat), [])
                self.assertTrue(lan_opencode.finish(path, request['id'], lan_opencode.consult(text)))
                self.assertFalse(lan_opencode.finish(path, request['id'], '重复答复'))
                assistant.assert_called_once_with('opencode', text)
                lan_pairing.sync(phone)
                reply = mobile.path(chat)[-1]
                self.assertEqual(mobile.path(chat)[-4]['id'], original)
                self.assertIn('答案是 3 mA', reply['text'])
                self.assertEqual([row['id'] for row in lan_opencode.retry_choices(mobile.db, chat)], [original])
                self.assertEqual(lan_opencode.pending(desktop.db), [])
            finally:
                host.close()
                host.worker.join(timeout=5)
                desktop.close()
                mobile.close()

    def test_restore_never_queues_request(self):
        with tempfile.TemporaryDirectory() as folder:
            store = History(Path(folder) / 'history.db')
            try:
                event = dict(seq=1, uuid='a'*32, chat='b'*32, parent=None, title='测试', role='user',
                             text='请 OpenCode 查看', image=None, state='complete', model='', provider='', error='',
                             created='', opencode_request=True)
                with store.db:
                    chat_sync._insert(store.db, event, restoring=True, opencode=True)
                self.assertEqual(lan_opencode.pending(store.db), [])
            finally:
                store.close()
