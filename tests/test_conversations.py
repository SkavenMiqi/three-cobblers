import sqlite3
import tempfile
import unittest
from pathlib import Path

from talkapp.storage import Config, History
from talkapp.context import plan_context, summary_batches


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.history = History(':memory:')
        self.chat = self.history.create()

    def tearDown(self):
        self.history.close()

    def test_edit_and_regenerate_preserve_independent_paths(self):
        h = self.history
        first = h.append(self.chat, 'user', 'original')
        answer = h.append(self.chat, 'assistant', 'answer', model='model-a', provider='provider-a')
        follow = h.append(self.chat, 'user', 'follow-up')
        leaf = h.append(self.chat, 'assistant', 'continued')
        alternative = h.append(self.chat, 'assistant', 'alternative', parent=first, model='model-b')
        self.assertEqual([n['text'] for n in h.path(self.chat)], ['original', 'alternative'])
        h.select(answer)
        self.assertEqual(h.path(self.chat)[-1]['id'], leaf)
        edit = h.append(self.chat, 'user', 'edited', parent=None)
        self.assertEqual(h.messages(self.chat), [('user', 'edited', None)])
        h.select(first)
        self.assertEqual(h.path(self.chat)[-1]['id'], leaf)
        self.assertEqual(h.node(answer)['model'], 'model-a')
        self.assertEqual(h.siblings(h.node(edit)), [first, edit])
        self.assertEqual(h.siblings(h.node(answer)), [answer, alternative])

    def test_summaries_never_cross_edited_ancestors(self):
        h = self.history
        user = h.append(self.chat, 'user', 'private path A')
        answer = h.append(self.chat, 'assistant', 'A answer')
        h.save_summary(self.chat, answer, 'A summary', 'model')
        edit = h.append(self.chat, 'user', 'different path B', parent=None)
        h.append(self.chat, 'assistant', 'B answer')
        self.assertIsNone(h.summary(self.chat, h.path(self.chat)))
        h.select(user)
        self.assertEqual(h.summary(self.chat, h.path(self.chat))['text'], 'A summary')

    def test_delete_branch_preserves_siblings_and_removes_descendants(self):
        h = self.history
        user = h.append(self.chat, 'user', 'question')
        old = h.append(self.chat, 'assistant', 'old')
        child = h.append(self.chat, 'user', 'follow')
        new = h.append(self.chat, 'assistant', 'new', parent=user)
        h.remove_branch(old)
        self.assertIsNone(h.node(child))
        self.assertEqual(h.path(self.chat)[-1]['id'], new)
        h.remove_branch(new)
        self.assertEqual(h.path(self.chat)[-1]['id'], user)

    def test_interrupted_stream_keeps_partial_and_can_retry(self):
        h = self.history
        user = h.append(self.chat, 'user', 'hello')
        reply = h.append(self.chat, 'assistant', '', state='generating')
        h.checkpoint(reply, 'partial answer')
        h.recover_interrupted()
        self.assertEqual(h.node(reply)['state'], 'interrupted')
        self.assertEqual(h.node(reply)['text'], 'partial answer')
        retry = h.append(self.chat, 'assistant', 'retried', parent=user)
        self.assertEqual(h.siblings(h.node(retry)), [reply, retry])

    def test_search_pinning_and_manual_title(self):
        h = self.history
        h.append(self.chat, 'user', 'needle original')
        h.append(self.chat, 'user', 'other branch', parent=None)
        other = h.create()
        h.pin(self.chat)
        self.assertEqual(h.search()[0]['id'], self.chat)
        self.assertEqual(h.search('needle')[0]['id'], self.chat)
        h.rename(self.chat, 'chosen')
        h.auto_title(self.chat, 'AI title')
        self.assertEqual(h.chats()[0][1], 'chosen')
        h.append(other, 'user', '100% literal')
        self.assertEqual(len(h.search('%')), 1)

    def test_context_compression_keeps_latest_turn(self):
        h = self.history
        for i in range(12):
            h.append(self.chat, 'user', '用户信息' * 150)
            h.append(self.chat, 'assistant', '回答内容' * 150)
        latest = h.append(self.chat, 'user', '最新问题')
        config = Config(api_key='test', context_tokens=4000)
        plan = plan_context(h.path(self.chat), config)
        self.assertTrue(plan.compress)
        self.assertEqual(plan.recent[0]['role'], 'user')
        self.assertEqual(plan.recent[-1]['id'], latest)
        self.assertTrue(list(summary_batches(plan.compress, config)))
        h.save_summary(self.chat, plan.compress[-1]['id'], '精简的历史摘要', 'model')
        saved = h.summary(self.chat, h.path(self.chat))
        next_plan = plan_context(h.path(self.chat), config, saved)
        self.assertEqual(next_plan.previous, '精简的历史摘要')
        self.assertFalse(next_plan.compress)

    def test_legacy_database_migrates_without_losing_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'legacy.db'
            db = sqlite3.connect(path)
            db.executescript("""
                CREATE TABLE chats(id INTEGER PRIMARY KEY,title TEXT,updated TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE messages(id INTEGER PRIMARY KEY,chat_id INTEGER REFERENCES chats(id) ON DELETE CASCADE,
                    role TEXT,text TEXT,image TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);
                INSERT INTO chats(id,title) VALUES(1,'legacy');
                INSERT INTO messages(chat_id,role,text) VALUES(1,'user','hello');
                INSERT INTO messages(chat_id,role,text) VALUES(1,'assistant','world');
            """)
            db.commit()
            db.close()
            upgraded = History(path)
            self.assertEqual([n['text'] for n in upgraded.path(1)], ['hello', 'world'])
            upgraded.close()
            reopened = History(path)
            self.assertEqual(len(reopened.path(1)), 2)
            reopened.close()


if __name__ == '__main__':
    unittest.main()
