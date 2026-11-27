import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from talkapp import lan_opencode, opencode_tasks
from talkapp.storage import History


class OpenCodeTaskTests(unittest.TestCase):
    def test_progress_and_retry_preserve_original_branch(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / 'history.db'
            store = History(db)
            try:
                cid = store.create()
                seed = store.append(cid, 'user', 'LED 实测 1.9 V')
                job = store.append(cid, 'user', '保存 LED 实验报告', local_opencode=True)
                self.assertEqual(lan_opencode.retry_choices(store.db, cid), [])
                lan_opencode.claim(db, job)
                ack = lan_opencode.progress_note(db, job, '已接单')
                run = lan_opencode.progress_note(db, job, '执行中')
                self.assertEqual(store.node(run)['parent_id'], ack)
                lan_opencode.finish(db, job, '执行结束')
                self.assertEqual(store.path(cid)[-1]['parent_id'], run)
                wrong = store.append(cid, 'user', '重新执行上一条命令', local_opencode=True)
                lan_opencode.claim(db, wrong)
                lan_opencode.finish(db, wrong, '检查了开关')
                (original,) = lan_opencode.retry_choices(store.db, cid)
                self.assertEqual(original['id'], job)
                retry = store.append(cid, 'user', original['text'], parent=original['parent_id'], local_opencode=True)
                self.assertEqual(store.node(retry)['parent_id'], seed)
                self.assertEqual(lan_opencode.context(db, retry), [['user', 'LED 实测 1.9 V']])
                self.assertEqual(lan_opencode.retry_choices(store.db, cid), [])
            finally:
                store.close()

    def test_natural_approval_only_matches_the_pending_note(self):
        note = '请回复「批准本次 123456」或「拒绝本次 123456」。只适用这一次。'
        self.assertEqual(opencode_tasks.approval_for_note('好。', note), ('123456', 'once'))
        self.assertEqual(opencode_tasks.approval_for_note('拒绝', note), ('123456', 'reject'))
        self.assertIsNone(opencode_tasks.approval_for_note('好', '普通消息'))
        self.assertIsNone(opencode_tasks.approval_for_note('先解释一下', note))
        self.assertIsNone(opencode_tasks.approval_for_note('批准本次 654321', note))

    def test_approval_consumes_only_the_exact_child_once(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / 'history.db'
            store = History(db)
            try:
                cid = store.create()
                mid = store.append(cid, 'user', '创建实验报告', local_opencode=True)
                self.assertEqual(lan_opencode.pending(store.db, local=False), [])
                self.assertEqual(lan_opencode.claim(db, mid), '创建实验报告')
                note = lan_opencode.permission_note(db, mid, '授权提示')
                yes = store.append(cid, 'user', '批准本次 123456', parent=note, local_opencode=True)
                self.assertIsNone(lan_opencode.take_approval(db, note, '000000'))
                self.assertIsNone(lan_opencode.take_approval(db, mid, '123456'))
                self.assertEqual(lan_opencode.take_approval(db, note, '123456'), 'once')
                self.assertIsNone(lan_opencode.take_approval(db, note, '123456'))
                note2 = lan_opencode.permission_note(db, mid, '授权提示二')
                self.assertEqual(store.node(note2)['parent_id'], yes)
                self.assertTrue(lan_opencode.finish(db, mid, '报告已生成'))
                self.assertEqual(store.path(cid)[-1]['parent_id'], note2)
            finally:
                store.close()

    def test_service_uses_one_time_native_reply(self):
        sid = 'ses_test'
        replies = iter([{'data': {'id': sid}}, {}, {'data': [{'id': 'req_1', 'sessionID': sid}]}, {},
                        {'data': {}}, {'data': []}, {'data': {'outcome': 'succeeded'}},
                        {'data': [{'content': [{'type': 'text', 'text': '完成'}]}]}])
        with patch.object(opencode_tasks, 'executable', return_value='cli.exe'), \
                patch.object(opencode_tasks, 'api', side_effect=lambda *a, **kw: next(replies)) as call, \
                patch.object(opencode_tasks.time, 'sleep'):
            self.assertIn('完成', opencode_tasks.run('生成文档', '.', authorize=lambda code, request: 'once'))
            self.assertEqual(call.call_args_list[0].args[3]['model'], {'providerID': '4router', 'id': 'gpt-6.2-sol'})
            call.assert_any_call('cli.exe', 'post', '/api/session/ses_test/permission/req_1/reply', {'decision': 'once'})
