import io
import json
import threading
import unittest
from unittest.mock import patch
from talkapp.storage import History, Config
from talkapp.app_tools import execute, TOOLS
from talkapp.client import stream_reply


class AppToolTests(unittest.TestCase):
    def test_completed_step_note_is_searchable_on_its_own_branch(self):
        history = History(':memory:')
        try:
            chat = history.create()
            user = history.append(chat, 'user', '万用表检查完成')
            history.merge_steps(chat, user, [{'title': '器材检查', 'detail': '核对型号'}])
            reply = history.append(chat, 'assistant', '', parent=user)
            step, = history.steps(chat)
            result = execute(history, chat, 'update_step', {'id': step['id'], 'done': True,
                             'note': '万用表型号为优利德 UT139C。'}, leaf=reply)
            self.assertTrue(result['done'])
            notes = execute(history, chat, 'search_current_chat', {'query': '万用表'}, leaf=reply)['notes']
            self.assertEqual(notes[0]['text'], '万用表型号为优利德 UT139C。')
            self.assertEqual(notes[0]['source_id'], reply)
            other_reply = history.append(chat, 'assistant', '另一分支', parent=user)
            self.assertEqual(history.progress_notes(chat, '万用表', leaf=other_reply), [])
            self.assertEqual(history.progress_notes(history.create(), '万用表'), [])
        finally:
            history.close()

    def test_sort_and_fold_42_steps_with_two_compact_reads(self):
        history = History(':memory:')
        try:
            chat = history.create()
            source = history.append(chat, 'user', '调整顺序并折叠已完成项')
            history.merge_steps(chat, source, [{'title': f'步骤 {n}', 'detail': '详细说明' * 100} for n in range(42)])
            original = history.steps(chat)
            for step in original[:26]:
                history.step_state(step['id'], done=True)
            first = execute(history, chat, 'get_progress', {'compact': True})
            second = execute(history, chat, 'get_progress', {'compact': True, 'start': first['next_start']})
            self.assertIsNone(second['next_start'])
            ids = [step[1] for step in reversed(first['steps'] + second['steps'])]
            self.assertEqual(len(ids), 42)
            with self.assertRaises(ValueError):
                execute(history, chat, 'reorder_steps', {'ids': ids[:-1] + [ids[0]]})
            self.assertEqual([step['id'] for step in history.steps(chat)], [step['id'] for step in original])
            with self.assertRaises(ValueError):
                execute(history, chat, 'reorder_steps', {'ids': ids, 'completed_summary': ''})
            self.assertEqual([step['id'] for step in history.steps(chat)], [step['id'] for step in original])
            folded = execute(history, chat, 'reorder_steps', {'ids': ids, 'completed_summary': '已完成 26 项，保留原记录。'})
            self.assertTrue(folded['saved'])
            self.assertEqual(folded['folded'], 26)
            self.assertEqual([step['id'] for step in history.steps(chat)], ids)
            self.assertEqual(history.step_fold(chat)[1], {step['id'] for step in original[:26]})
        finally:
            history.close()

    def test_multiple_goals_move_and_merge_in_current_conversation(self):
        history = History(':memory:')
        try:
            chat = history.create()
            history.set_goal(chat, '已有目标')
            self.assertEqual(execute(history, chat, 'manage_goals', {}), {'goals': ['已有目标']})
            execute(history, chat, 'manage_goals', {'goals': ['已有目标', '第二个目标']})
            self.assertEqual(history.goals(chat), ['已有目标', '第二个目标'])
            history.append(chat, 'user', '整理步骤')
            reply = history.append(chat, 'assistant', '整理中')
            items = execute(history, chat, 'add_steps', {'steps': [
                {'title': '接线', 'detail': '检查电源' * 100}, {'title': '编译', 'detail': '核对输出' * 100},
                {'title': '测试', 'detail': '检查读数'},
            ]})['steps']
            execute(history, chat, 'move_step', {'id': items[2]['id'], 'number': 1})
            self.assertEqual([step['title'] for step in history.steps(chat)], ['测试', '接线', '编译'])
            history.step_state(items[0]['id'], done=True)
            history.step_state(items[1]['id'], active=True)
            before = history.project_snapshot(chat)
            merged = execute(history, chat, 'merge_steps', {'ids': [items[0]['id'], items[1]['id']], 'title': '准备草图'})
            self.assertFalse(merged['done'])
            step, = execute(history, chat, 'get_progress', {'number': 2, 'include_detail': True})['steps']
            self.assertTrue(step['active'])
            self.assertEqual(step['detail'], '接线\n' + '检查电源' * 100 + '\n\n编译\n' + '核对输出' * 100)
            with history.db:
                action = history.db.execute('INSERT INTO action_log(reply_id,name,result,before_state,after_state) VALUES (?,?,?,?,?)',
                    (reply, 'merge_steps', json.dumps(merged), json.dumps(before), json.dumps(history.project_snapshot(chat)))).lastrowid
            history.undo_action(action)
            self.assertEqual(history.project_snapshot(chat), before)
            merged = execute(history, chat, 'merge_steps', {'ids': [items[0]['id'], items[1]['id']], 'title': '准备草图'})
            execute(history, chat, 'update_step', {'id': merged['id'], 'done': True})
            self.assertEqual(history.steps(chat)[1]['detail'], step['detail'])
        finally:
            history.close()

    def test_lookup_progress_by_display_number_and_title(self):
        history = History(':memory:')
        try:
            other = history.create()
            history.merge_steps(other, history.append(other, 'user', '其他对话'),
                                [{'title': '其他步骤', 'detail': ''}])
            chat = history.create()
            source = history.append(chat, 'user', '检查进度')
            history.merge_steps(chat, source, [
                {'title': f'步骤 {number}', 'detail': '很长的说明' * 100}
                for number in range(1, 26)
            ])
            page = execute(history, chat, 'get_progress', {})
            self.assertEqual((len(page['steps']), page['next_start'], page['total']), (8, 9, 25))
            step, = execute(history, chat, 'get_progress', {'number': 22})['steps']
            self.assertEqual(step['title'], '步骤 22')
            self.assertNotEqual(step['id'], 22)
            self.assertNotIn('detail', step)
            self.assertEqual(execute(history, chat, 'get_progress', {'query': '22'})['steps'], [step])
            saved = execute(history, chat, 'update_step', {'id': step['id'], 'done': True})
            self.assertTrue(saved['done'])
            self.assertFalse(history.steps(chat)[20]['done'])
            self.assertTrue(history.steps(chat)[21]['done'])
        finally:
            history.close()

    def test_actual_goal_steps_and_cross_chat_boundary(self):
        h = History(':memory:')
        try:
            chat = h.create()
            h.append(chat, 'user', '把当前内容加入步骤')
            execute(h, chat, 'set_goal', {'goal': '完成聊天软件'})
            result = execute(h, chat, 'add_steps', {'steps': [{'title': '实现进度', 'detail': '可保存和更新'}]})
            self.assertTrue(result['saved'])
            step = result['steps'][0]
            execute(h, chat, 'update_step', {'id': step['id'], 'done': True})
            self.assertEqual(h.steps(chat)[0]['done'], 1)
            self.assertEqual(h.goal(chat), '完成聊天软件')
            with self.assertRaises(ValueError):
                execute(h, h.create(), 'update_step', {'id': step['id'], 'done': False})
            with self.assertRaises(ValueError):
                execute(h, chat, 'run_python', {'code': 'bad'})
        finally:
            h.close()

    def test_streamed_tool_arguments_are_assembled(self):
        class Response(io.BytesIO):
            headers = {'Content-Type': 'text/event-stream'}
        events = [
            {'choices': [{'delta': {'tool_calls': [{'index': 0, 'id': 'call1', 'function': {'name': 'set_goal', 'arguments': '{"goal":'}}]}}]},
            {'choices': [{'delta': {'tool_calls': [{'index': 0, 'function': {'arguments': '"目标"}'}}]}, 'finish_reason': 'tool_calls'}]}]
        payload = ''.join('data: ' + json.dumps(event) + '\n\n' for event in events) + 'data: [DONE]\n'
        calls = []
        with patch('urllib.request.urlopen', return_value=Response(payload.encode())):
            stream_reply(Config(api_key='test'), [('user', '设置目标', None)], lambda _: None,
                         threading.Event(), tools=TOOLS, on_tools=calls.extend)
        self.assertEqual(calls[0]['function']['name'], 'set_goal')
        self.assertEqual(json.loads(calls[0]['function']['arguments'])['goal'], '目标')
