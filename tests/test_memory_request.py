import unittest
from talkapp.storage import History, Config
from talkapp.memory import retrieve, supplement
from talkapp.context import plan_context, context_prompt


class MemoryRequestTests(unittest.TestCase):
    def test_new_chat_request_contains_only_confirmed_memory_and_cited_history(self):
        h = History(':memory:')
        try:
            old = h.create()
            source = h.append(old, 'user', '我喜欢Python编程，解释时要多举例')
            h.append(old, 'assistant', '我们讨论了Python学习计划')
            h.propose_memory('用户喜欢举例说明', source)
            h.propose_memory('未确认信息', source)
            candidate = next(item for item in h.memories() if item['text'] == '用户喜欢举例说明')
            h.update_memory(candidate['id'], 'accepted')
            new = h.create()
            h.append(new, 'user', '上次Python编程学习计划是什么？')
            sources = retrieve(h, h.path(new)[-1]['text'], new)
            extra = supplement(h.memories('accepted'), sources)
            config = Config(api_key='test', system_prompt='助手' + extra)
            plan = plan_context(h.path(new), config)
            prompt = context_prompt(config, plan.summary)
            self.assertIn('用户喜欢举例说明', prompt)
            self.assertNotIn('未确认信息', prompt)
            self.assertIn('[历史1]', prompt)
            reply = h.append(new, 'assistant', '回答')
            h.save_recall(reply, sources, h.memories('accepted'))
            self.assertEqual(h.recall(reply)[0][0]['message_id'], source)
        finally:
            h.close()
