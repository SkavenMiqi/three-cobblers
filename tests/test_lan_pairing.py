import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from talkapp import lan_pairing as lan
from talkapp.storage import History


class LanPairingTests(unittest.TestCase):
    def test_auto_sync_is_opt_in_and_requires_existing_peer(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pc, phone = root / 'lan-phone.json', root / 'lan-computer.json'
            pc.touch()
            self.assertIsNone(lan.auto_sync(root, False))
            lan.set_auto_sync(root, '192.168.1.12')
            self.assertEqual(lan.auto_sync(root, False), '192.168.1.12')
            with self.assertRaises(ValueError):
                lan.set_auto_sync(root, '8.8.8.8')
            pc.unlink()
            self.assertIsNone(lan.auto_sync(root, False))
            phone.touch()
            self.assertIsNone(lan.auto_sync(root, True))
            lan.set_auto_sync(root, True)
            self.assertIs(lan.auto_sync(root, True), True)
            lan.set_auto_sync(root)
            self.assertIsNone(lan.auto_sync(root, True))

    def test_invitation_active_until_expiry_or_revocation(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(lan, 'lan_address', side_effect=lambda value: value):
            host = lan.PairingHost(folder, '127.0.0.1', port=0)
            try:
                self.assertFalse(host.invitation_active())
                self.assertTrue(host.invitation().startswith(lan.PREFIX))
                self.assertTrue(host.invitation_active())
                with patch.object(lan.time, 'monotonic', return_value=host.deadline):
                    self.assertFalse(host.invitation_active())
                host.forget()
                self.assertFalse(host.invitation_active())
            finally:
                host.close()
                host.worker.join(timeout=5)

    def test_progress_initial_merge_then_bidirectional_edits(self):
        with tempfile.TemporaryDirectory() as desktop, tempfile.TemporaryDirectory() as mobile, \
                patch.object(lan, 'lan_address', side_effect=lambda value: value):
            pc, phone = [History(Path(root) / 'history.db') for root in (desktop, mobile)]
            host = lan.PairingHost(desktop, '127.0.0.1', port=0)
            try:
                cid = phone.create()
                mid = phone.append(cid, 'user', '做一个原型')
                lan.pair(mobile, host.invitation())
                host.sync_enabled = True
                lan.sync(mobile)
                pcid = pc.chats()[0][0]
                phone.set_goal(cid, '完成原型')
                phone.merge_steps(cid, mid, [{'title': '准备零件', 'detail': '确认型号'}])
                pc.merge_steps(pcid, pc.path(pcid)[0]['id'], [{'title': '准备零件', 'detail': ''}, {'title': '测量电压', 'detail': ''}])
                phone.step_state(phone.steps(cid)[0]['id'], done=True)
                pc.step_state(pc.steps(pcid)[1]['id'], active=True)
                for _ in range(4):
                    lan.sync(mobile)
                for store, chat in ((pc, pcid), (phone, cid)):
                    steps = {row['title']: row for row in store.steps(chat)}
                    self.assertEqual(len(steps), 2)
                    self.assertEqual(store.goal(chat), '完成原型')
                    self.assertEqual(steps['准备零件']['detail'], '确认型号')
                    self.assertTrue(steps['准备零件']['done'])
                    self.assertTrue(steps['测量电压']['active'])
                pc.step_state(next(s['id'] for s in pc.steps(pcid) if s['title'] == '准备零件'), done=False)
                phone.set_goal(cid, '完成并测试原型')
                for _ in range(4):
                    lan.sync(mobile)
                self.assertFalse(next(s['done'] for s in phone.steps(cid) if s['title'] == '准备零件'))
                self.assertEqual(pc.goal(pcid), '完成并测试原型')
                step = next(s for s in pc.steps(pcid) if s['title'] == '测量电压')
                self.assertTrue(pc.delete_step(pcid, step['id']))
                self.assertFalse(pc.delete_step(pcid, step['id']))
                pc.merge_steps(pcid, pc.path(pcid)[0]['id'], [{'title': '测量电压', 'detail': '旧步骤'}])
                for _ in range(4):
                    lan.sync(mobile)
                self.assertEqual(len(pc.steps(pcid)), 1)
                self.assertEqual(len(phone.steps(cid)), 2)
                self.assertTrue(next(s['active'] for s in phone.steps(cid) if s['title'] == '测量电压'))
            finally:
                host.close()
                host.worker.join(timeout=5)
                phone.close()
                pc.close()

    def test_restore_in_either_direction_and_never_if_both_deleted(self):
        from talkapp.chat_sync import queue_restore
        with tempfile.TemporaryDirectory() as desktop, tempfile.TemporaryDirectory() as mobile, \
                patch.object(lan, 'lan_address', side_effect=lambda value: value):
            pc, phone = [History(Path(root) / 'history.db') for root in (desktop, mobile)]
            host = lan.PairingHost(desktop, '127.0.0.1', port=0)
            try:
                cid = phone.create()
                photo = 'data:image/jpeg;base64,example'
                head = phone.append(cid, 'user', '原图', photo)
                phone.append(cid, 'assistant', '另一分支', parent=head)
                phone.append(cid, 'assistant', '选中分支', parent=head)
                lan.pair(mobile, host.invitation())
                host.sync_enabled = True
                lan.sync(mobile)
                pc.delete(pc.chats()[0][0])
                phone.append(cid, 'user', '删除之后收到的新消息')
                for _ in range(2):
                    lan.sync(mobile)
                self.assertEqual(pc.chats(), [])
                for destination in (pc, phone):
                    if destination.chats():
                        destination.delete(destination.chats()[0][0])
                    with destination.db:
                        self.assertEqual(queue_restore(destination.db), 1)
                    for _ in range(4):
                        lan.sync(mobile)
                    restored = destination.chats()[0][0]
                    self.assertEqual([m[1] for m in destination.messages(restored)], ['原图', '选中分支', '删除之后收到的新消息'])
                    self.assertIn(photo, destination.messages(restored)[0][2])
                    self.assertEqual(destination.db.execute('SELECT count(*) FROM messages').fetchone()[0], 4)
                for endpoint in (pc, phone):
                    endpoint.delete(endpoint.chats()[0][0])
                    with endpoint.db:
                        queue_restore(endpoint.db)
                lan.sync(mobile)
                for endpoint in (pc, phone):
                    self.assertEqual(endpoint.chats(), [])
                    self.assertEqual(endpoint.db.execute('SELECT count(*) FROM lan_restore').fetchone()[0], 0)
            finally:
                host.close()
                host.worker.join(timeout=5)
                phone.close()
                pc.close()

    def test_two_way_sync_keeps_parallel_branches_and_excludes_temporary(self):
        with tempfile.TemporaryDirectory() as desktop, tempfile.TemporaryDirectory() as mobile, \
                patch.object(lan, 'lan_address', side_effect=lambda value: value):
            pc, phone = [History(Path(root) / 'history.db') for root in (desktop, mobile)]
            host = lan.PairingHost(desktop, '127.0.0.1', port=0)
            try:
                cid = phone.create()
                phone.append(cid, 'user', '手机提问')
                original = phone.append(cid, 'assistant', '手机回答')
                temporary = phone.create(temporary=True)
                phone.append(temporary, 'user', '不共享')
                lan.pair(mobile, host.invitation())
                with self.assertRaisesRegex(ValueError, '开启同步'):
                    lan.sync(mobile)
                host.sync_enabled = True
                lan.sync(mobile)
                pc_chat = pc.chats()[0][0]
                self.assertEqual(len(pc.chats()), 1)
                self.assertEqual([m[1] for m in pc.messages(pc_chat)], ['手机提问', '手机回答'])
                pc.append(pc_chat, 'user', '电脑续写')
                pc.append(pc_chat, 'assistant', '电脑回答')
                local = phone.append(cid, 'user', '手机续写', parent=original)
                reply = phone.append(cid, 'assistant', '', parent=local, state='generating')
                lan.sync(mobile)
                self.assertEqual(pc.db.execute("SELECT count(*) FROM messages WHERE state='generating'").fetchone()[0], 0)
                from PIL import Image
                from talkapp.client import image_data
                photo = Path(mobile) / 'sample.png'
                Image.new('RGB', (10, 10), 'blue').save(photo)
                phone.checkpoint(reply, '手机新回答', 'complete', image=image_data(photo))
                for _ in range(3):
                    lan.sync(mobile)
                for db in (pc, phone):
                    rows = db.db.execute('SELECT text,image FROM messages WHERE chat_id NOT IN (SELECT id FROM chats WHERE temporary=1)').fetchall()
                    self.assertEqual(len(rows), 6)
                    self.assertIn('电脑回答', [row[0] for row in rows])
                    self.assertIn('data:image/jpeg;base64,', next(row[1] for row in rows if row[0] == '手机新回答'))
                self.assertEqual(phone.messages(cid)[-1][1], '手机新回答')
                self.assertEqual(pc.messages(pc_chat)[-1][1], '电脑回答')
                host.forget()
                with self.assertRaises(ValueError):
                    lan.sync(mobile)
            finally:
                host.close()
                host.worker.join(timeout=5)
                phone.close()
                pc.close()

    def test_private_ipv4_only(self):
        self.assertEqual(lan.lan_address('192.168.1.20'), '192.168.1.20')
        for address in ('8.8.8.8', 'localhost', '::1', '0.0.0.0', '127.0.0.1'):
            with self.subTest(address=address), self.assertRaises(ValueError):
                lan.lan_address(address)

    def test_encrypted_pairing_pin_one_time_expiry_and_revocation(self):
        with tempfile.TemporaryDirectory() as desktop, tempfile.TemporaryDirectory() as mobile, \
                patch.object(lan, 'lan_address', side_effect=lambda value: value):
            host = lan.PairingHost(desktop, '127.0.0.1', port=0)
            try:
                code = host.invitation()
                host.deadline = 0
                with self.assertRaisesRegex(ValueError, '过期'):
                    lan.pair(mobile, code)
                code = host.invitation()
                invitation = json.loads(base64.urlsafe_b64decode(code[len(lan.PREFIX):]))
                invitation[2] = '0' * 64
                wrong_pin = lan.PREFIX + base64.urlsafe_b64encode(json.dumps(invitation).encode()).decode()
                with self.assertRaisesRegex(ValueError, '身份不匹配'):
                    lan.pair(mobile, wrong_pin)
                self.assertFalse(host.paired())
                lan.pair(mobile, code)
                self.assertTrue(host.paired())
                lan.check(mobile)
                token = json.loads((Path(mobile) / 'lan-computer.json').read_text())[3]
                self.assertNotIn(token, host.peer_file.read_text())
                with self.assertRaisesRegex(ValueError, '过期'):
                    lan.pair(mobile, code)
                host.forget()
                with self.assertRaisesRegex(ValueError, '解除'):
                    lan.check(mobile)
            finally:
                host.close()
                host.worker.join(timeout=5)
