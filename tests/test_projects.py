import json
import unittest
from talkapp.storage import History
from talkapp.app_tools import execute


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.h = History(':memory:')
        self.chat = self.h.create()
        self.source = self.h.append(self.chat, 'user', '建立计划')

    def tearDown(self):
        self.h.close()

    def test_shared_progress_and_isolated_library(self):
        project = self.h.project(self.chat)
        other = self.h.create(project_id=project['id'])
        separate = self.h.create()
        execute(self.h, self.chat, 'set_goal', {'goal': '共享目标'})
        execute(self.h, self.chat, 'add_steps', {'steps': [{'title': '步骤一', 'detail': '准备'}]})
        self.assertEqual(self.h.goal(other), '')
        self.assertEqual(self.h.steps(other), [])
        self.assertEqual(self.h.steps(separate), [])
        self.h.save_library(self.chat, '资料.md', '第一版')
        self.h.save_library(self.chat, '资料.md', '第二版')
        self.assertEqual(self.h.library(other)[0]['version'], 2)
        self.assertEqual(self.h.library(separate), [])
        file_id = self.h.library(other)[0]['id']
        self.assertIn('第二版', execute(self.h, other, 'read_project_file', {'id': file_id})['text'])
        with self.assertRaises(ValueError):
            execute(self.h, separate, 'read_project_file', {'id': file_id})
        self.h.delete(self.chat)
        self.assertEqual(self.h.steps(other), [])

    def test_undo_checks_subsequent_changes(self):
        reply = self.h.append(self.chat, 'assistant', '处理中')
        before = self.h.project_snapshot(self.chat)
        execute(self.h, self.chat, 'set_goal', {'goal': '新目标'})
        after = self.h.project_snapshot(self.chat)
        with self.h.db:
            action = self.h.db.execute('INSERT INTO action_log(reply_id,name,result,before_state,after_state) VALUES (?,?,?,?,?)',
                (reply, 'set_goal', '{}', json.dumps(before), json.dumps(after))).lastrowid
        self.h.undo_action(action)
        self.assertEqual(self.h.goal(self.chat), '')
        with self.assertRaises(ValueError):
            self.h.undo_action(action)

    def test_undo_does_not_overwrite_later_step_update(self):
        reply = self.h.append(self.chat, 'assistant', '处理中')
        before = self.h.project_snapshot(self.chat)
        execute(self.h, self.chat, 'set_goal', {'goal': '目标A'})
        after = self.h.project_snapshot(self.chat)
        with self.h.db:
            action = self.h.db.execute('INSERT INTO action_log(reply_id,name,result,before_state,after_state) VALUES (?,?,?,?,?)',
                (reply, 'set_goal', '{}', json.dumps(before), json.dumps(after))).lastrowid
        self.h.set_goal(self.chat, '目标B')
        with self.assertRaises(ValueError):
            self.h.undo_action(action)
        self.assertEqual(self.h.goal(self.chat), '目标B')
