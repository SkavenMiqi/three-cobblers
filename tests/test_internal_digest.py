import unittest
from talkapp.storage import History
from talkapp.memory import digest_chunks, digest_prompt, digest_value


class DigestTests(unittest.TestCase):
    def test_short_dialogue_can_be_remembered_or_skipped(self):
        history = History(':memory:')
        try:
            chat = history.create()
            history.append(chat, 'user', '我叫小明，喜欢简洁回答')
            _, pending = history.digest_work()
            self.assertEqual(len(pending), 1)
            item = pending[0]
            history.save_digest(chat, item['key'], '用户：小明，偏好简洁回答。')
            self.assertIn('小明', digest_prompt(history.digest_work()[0]))
            self.assertEqual(digest_value('你好', 'SKIP'), '')
            history.save_digest(chat, item['key'], '')
            self.assertEqual(history.digest_work()[1], [])
        finally:
            history.close()

    def test_threshold_branch_and_deletion(self):
        history = History(':memory:')
        try:
            chat = history.create()
            history.append(chat, 'user', '甲' * 9000)
            self.assertEqual(len(history.digest_work()[1]), 1)
            history.append(chat, 'assistant', '乙' * 2000)
            _, pending = history.digest_work()
            self.assertEqual(len(pending), 2)
            item = pending[0]
            history.save_digest(chat, item['key'], '用户讨论了一个长期目标。')
            ready, remaining = history.digest_work()
            self.assertEqual(len(remaining), 1)
            self.assertIn('长期目标', digest_prompt(ready))
            history.append(chat, 'user', '完全不同的分支', parent=None)
            self.assertEqual(history.digest_work()[0], [])
            self.assertEqual(len(history.digest_work()[1]), 1)
            history.delete(chat)
            history.save_digest(chat, item['key'], '迟到的摘要')
            self.assertEqual(history.db.execute('SELECT COUNT(*) FROM internal_digests').fetchone()[0], 0)
        finally:
            history.close()
