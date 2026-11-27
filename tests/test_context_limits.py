import json
import unittest
from talkapp.storage import Config, History
from talkapp.context import compaction_slice, context_rows, fit_chat_context, fit_tool_round, interactive_config, limit_recent, plan_context, request_budget, stable_chat_window, window_compaction, without_old_images
from talkapp.app_tools import INSTRUCTIONS, TOOLS, execute
from talkapp.client import messages_for_api


class ContextLimitTests(unittest.TestCase):
    def test_text_window_moves_in_batches_and_summary_waits_for_next_boundary(self):
        config = interactive_config(Config(max_output_tokens=2048))
        history = []
        saved = None
        first_ids = []
        compactions = []
        for turn in range(1, 31):
            history.append(dict(id=2 * turn - 1, role='user', text='问题' * 100))
            window = stable_chat_window(history, config, overhead=INSTRUCTIONS)
            first_ids.append(window[0]['id'])
            old = window_compaction(history, window, saved)
            if old:
                batch, through = compaction_slice(old, config, recent_first=True)
                self.assertTrue(batch)
                self.assertEqual(through, old[-1]['id'])
                saved = {'through_id': through}
                compactions.append(turn)
            history.append(dict(id=2 * turn, role='assistant', text='回答' * 100))
        self.assertTrue(compactions)
        self.assertEqual(compactions, [i + 1 for i in range(1, len(first_ids)) if first_ids[i] != first_ids[i - 1]])
        self.assertTrue(all(b - a > 1 for a, b in zip(compactions, compactions[1:])))
        self.assertTrue(all(b - a > 2 for a, b in zip(first_ids, first_ids[1:]) if a != b))

    def test_current_chat_recall_is_pinned_to_reply_branch(self):
        history = History(':memory:')
        try:
            chat = history.create()
            root = history.append(chat, 'user', '开始项目')
            correct = history.append(chat, 'assistant', '调光成功，使用 D9', parent=root)
            followup = history.append(chat, 'user', '继续', parent=correct)
            reply = history.append(chat, 'assistant', '', parent=followup, state='generating')
            history.append(chat, 'assistant', '调光失败，使用 D6', parent=root)
            sources = execute(history, chat, 'search_current_chat', {'query': '调光'}, leaf=reply)['sources']
            self.assertEqual([row['message_id'] for row in sources], [correct])
        finally:
            history.close()

    def test_progress_followup_keeps_recent_confirmation_without_resending_photos(self):
        config = interactive_config(Config(max_output_tokens=8000))
        images = ['data:image/png;base64,AAAA'] * 3
        path = [dict(id=1, role='user', text='准备用旋钮调光', state='complete'),
                dict(id=2, role='assistant', text='烧录后观察 LED', state='complete'),
                dict(id=3, role='user', text='成功了', image=images, state='complete'),
                dict(id=4, role='assistant', text='旋转电位器时亮度改变，调光成功。', state='complete'),
                dict(id=5, role='user', text='确认进度吧，然后开始下一条', state='complete')]
        plan = plan_context(without_old_images(path), config)
        _, recent = fit_chat_context(plan.recent, config, '基础指令', ('旧背景' * 1350,),
                                     overhead=INSTRUCTIONS + json.dumps(TOOLS, ensure_ascii=False))
        self.assertIn(4, [node['id'] for node in recent])
        self.assertFalse(next(node for node in recent if node['id'] == 3).get('image'))
        self.assertEqual(path[2]['image'], images)

    def test_background_is_skipped_without_dropping_current_photo(self):
        config = interactive_config(Config(context_tokens=16000, max_output_tokens=8000))
        photo = {'role': 'user', 'text': '看这张图', 'image': 'data:image/png;base64,AAAA'}
        nodes = [{'role': 'user', 'text': '旧' * 6000}, photo]
        prompt, recent = fit_chat_context(nodes, config, '基础指令', ('不相关' * 4000, '\n相关摘要'),
                                          overhead=INSTRUCTIONS + json.dumps(TOOLS, ensure_ascii=False))
        self.assertEqual(prompt, '基础指令\n相关摘要')
        self.assertEqual(recent, [photo])
        self.assertEqual(len(nodes), 2)

    def test_short_photo_question_fits_with_large_saved_output_reserve(self):
        config = Config(context_tokens=16000, model_context_limit=16000, max_output_tokens=8000)
        photo = {'role': 'user', 'text': '这张照片里是什么？', 'image': 'data:image/png;base64,AAAA'}
        prompt = '背景' * 1125
        wire_config = interactive_config(config)
        recent = limit_recent([photo], wire_config, prefix=prompt + INSTRUCTIONS + json.dumps(TOOLS, ensure_ascii=False))
        messages = messages_for_api(context_rows(recent), prompt + INSTRUCTIONS, prepared=True)
        wire = fit_tool_round(wire_config, messages, TOOLS)
        self.assertEqual(wire[-1]['content'][0]['text'], photo['text'])
        self.assertEqual(wire[-1]['content'][1]['type'], 'image_url')
        self.assertEqual(wire_config.context_tokens, 16000)
        self.assertEqual(config.max_output_tokens, 8000)

    def test_tool_round_trims_old_turns_and_result_without_losing_protocol(self):
        config = Config(context_tokens=4000, max_output_tokens=512)
        messages = [{'role': 'system', 'content': '指令'}, {'role': 'user', 'content': '旧' * 1300},
                    {'role': 'assistant', 'content': '旧回复'}, {'role': 'user', 'content': '当前问题'},
                    {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'c1'}]},
                    {'role': 'tool', 'tool_call_id': 'c1', 'content': '结果' * 4000}]
        wire = fit_tool_round(config, messages, None)
        self.assertEqual(wire[1]['content'], messages[1]['content'])
        self.assertEqual(wire[3]['content'], '当前问题')
        self.assertEqual(wire[-1]['tool_call_id'], 'c1')
        self.assertLess(len(wire[-1]['content']), len(messages[-1]['content']))
        request_budget(config, wire)

    def test_large_history_setting_does_not_set_interactive_request_size(self):
        config = Config(api_key='test', context_tokens=400000, model_context_limit=400000)
        path = [{'id': i, 'role': 'user' if i % 2 else 'assistant', 'state': 'complete', 'text': '甲' * 4000}
                for i in range(1, 18)] + [{'id': 18, 'role': 'user', 'text': '继续'}]
        self.assertFalse(plan_context(path, config).compress)
        wire = interactive_config(config)
        self.assertEqual(wire.context_tokens, 16000)
        self.assertEqual(config.context_tokens, 400000)
        recent = limit_recent(path, wire)
        self.assertLess(len(recent), len(path))
        self.assertEqual(recent[-1]['id'], 18)
        batch, _ = compaction_slice(path, config)
        self.assertEqual(len(batch), 1)

    def test_one_compaction_request_per_turn_with_no_skipped_checkpoint(self):
        config = Config(api_key='test', context_tokens=16000)
        nodes = [{'id': i, 'role': 'user', 'text': '甲' * 1200} for i in range(1, 9)]
        batch, through = compaction_slice(nodes, config)
        self.assertEqual(through, 1)
        self.assertEqual(len(batch), 1)
        self.assertEqual(compaction_slice(nodes[through:], config)[1], 2)

    def test_200k_compaction_retains_recent_and_reuses_saved_summary(self):
        config = Config(api_key='test', context_tokens=400000, model_context_limit=400000)
        path = [{'id': i, 'role': 'user' if i % 2 else 'assistant', 'state': 'complete', 'text': '旧' * 10000}
                for i in range(1, 12)]
        self.assertFalse(plan_context(path[:9], config).compress)
        plan = plan_context(path, config)
        self.assertTrue(plan.compress)
        self.assertEqual(plan.recent[-1]['id'], 11)
        self.assertFalse(plan_context(path, config, {'through_id': plan.compress[-1]['id'], 'text': '摘要'}).compress)
        self.assertTrue(plan_context(path[:5], config, force=True).compress)

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

    def test_400k_budget_accepts_request_above_200k_and_reserves_output(self):
        config = Config(api_key='test', context_tokens=400000, model_context_limit=400000)
        config.validate()
        self.assertGreater(request_budget(config, [{'role': 'user', 'content': '长' * 110000}]), 200000)
        with self.assertRaises(ValueError):
            request_budget(config, [{'role': 'user', 'content': '长' * 185000}])

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
