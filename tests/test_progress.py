import unittest
from talkapp.progress import parse_steps, has_requirements
from talkapp.storage import History


class ProgressTests(unittest.TestCase):
    def test_merge_preserves_completion_and_current_step(self):
        h = History(':memory:')
        try:
            chat = h.create()
            source = h.append(chat, 'user', '我想开发一个软件，需要分步骤完成')
            steps = parse_steps('```json\n[{"title":"准备环境","detail":"安装依赖"},{"title":"实现功能","detail":"完成聊天"}]\n```')
            h.merge_steps(chat, source, steps)
            first, second = h.steps(chat)
            h.step_state(first['id'], done=True)
            h.step_state(second['id'], active=True)
            h.merge_steps(chat, source, steps)
            self.assertEqual(len(h.steps(chat)), 2)
            self.assertEqual(h.steps(chat)[0]['done'], 1)
            self.assertEqual(h.steps(chat)[1]['active'], 1)
            h.delete(chat)
            self.assertEqual(h.steps(chat), [])
        finally:
            h.close()

    def test_parser_and_trigger(self):
        self.assertEqual(parse_steps('not json'), [])
        self.assertFalse(has_requirements('你好'))
        self.assertTrue(has_requirements('我想学习Python，请帮我安排计划'))
