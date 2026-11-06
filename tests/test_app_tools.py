import io
import json
import threading
import unittest
from unittest.mock import patch
from talkapp.storage import History, Config
from talkapp.app_tools import execute, TOOLS
from talkapp.client import stream_reply


class AppToolTests(unittest.TestCase):
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
