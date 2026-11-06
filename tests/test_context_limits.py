import unittest
from talkapp.storage import Config, History
from talkapp.context import request_budget


class ContextLimitTests(unittest.TestCase):
    def test_tool_traffic_and_output_reserved_each_round(self):
        config = Config(api_key='test', context_tokens=4000, max_output_tokens=1000)
        messages = [{'role': 'user', 'content': '你好'}]
        self.assertLess(request_budget(config, messages), 100)
        messages.append({'role': 'tool', 'content': '结果' * 1000})
        with self.assertRaises(ValueError):
            request_budget(config, messages)

    def test_hard_limit_wins_over_soft_budget(self):
        config = Config(api_key='test', context_tokens=272000, model_context_limit=4000, max_output_tokens=1000)
        with self.assertRaises(ValueError):
            request_budget(config, [{'role': 'user', 'content': '长' * 2000}])

    def test_draft_is_per_chat_and_deleted_with_chat(self):
        history = History(':memory:')
        try:
            first, second = history.create(), history.create()
            history.save_draft(first, '还没发送的消息')
            self.assertEqual(history.draft(second), '')
            self.assertEqual(history.draft(first), '还没发送的消息')
            history.delete(first)
            self.assertEqual(history.draft(first), '')
        finally:
            history.close()
