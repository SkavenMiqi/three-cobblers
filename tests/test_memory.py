import unittest

from talkapp.storage import History
from talkapp.memory import retrieve, supplement, parse_candidates


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.h = History(':memory:')
        self.old = self.h.create()
        self.user = self.h.append(self.old, 'user', '我正在学习Python，想做安卓聊天软件')
        self.h.append(self.old, 'assistant', '可以从Python界面和安卓打包开始')
        self.new = self.h.create()

    def tearDown(self):
        self.h.close()

    def test_confirmation_required_and_rejection_not_reproposed(self):
        self.h.propose_memory('用户正在学习Python', self.user)
        self.assertEqual(self.h.memories('accepted'), [])
        candidate = self.h.memories('pending')[0]
        self.h.update_memory(candidate['id'], 'accepted')
        self.assertIn('学习Python', supplement(self.h.memories('accepted'), []))
        self.h.forget_memory(candidate['id'])
        self.h.propose_memory('用户正在学习Python', self.user)
        self.assertEqual(self.h.memories('pending'), [])
        self.assertEqual(self.h.memories('accepted'), [])

    def test_cross_chat_retrieval_has_source_and_excludes_current(self):
        values = retrieve(self.h, '上次Python安卓软件讨论的方案', self.new)
        self.assertEqual(values[0]['chat_id'], self.old)
        self.assertEqual(values[0]['message_id'], self.user)
        self.assertIn('[历史1]', supplement([], values))
        self.assertEqual(retrieve(self.h, 'Python安卓软件', self.old), [])

    def test_abandoned_branches_are_not_retrieved(self):
        self.h.append(self.old, 'user', '周末去公园散步', parent=None)
        self.assertEqual(retrieve(self.h, 'Python安卓软件', self.new), [])

    def test_invalid_extraction_and_deleted_source(self):
        self.assertEqual(parse_candidates('not json'), [])
        self.assertEqual(parse_candidates('{"fact":"x"}'), [])
        self.assertEqual(parse_candidates('```json\n["喜欢举例说明", "喜欢举例说明"]\n```'), ['喜欢举例说明'])
        self.h.propose_memory('喜欢举例说明', self.user)
        self.h.delete(self.old)
        self.assertIsNone(self.h.memories()[0]['source_id'])
        self.h.propose_memory('已删除内容', self.user)
        self.assertEqual(len(self.h.memories()), 1)
