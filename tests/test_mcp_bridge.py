import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from talkapp.mcp_bridge import Bridge, handle
from talkapp.storage import History


class McpBridgeTests(unittest.TestCase):
    def test_live_chat_read_and_scoped_write(self):
        history = History(':memory:')
        self.addCleanup(history.close)
        chat = history.create()
        leaf = history.append(chat, 'user', '工程需求', image='data:image/jpeg;base64,private')
        history.set_goal(chat, '原型')
        view = SimpleNamespace(chat_id=chat, history=history, closed=False, busy=False, editing=None, render=lambda: None)
        context = handle(view, {'op': 'read'})
        self.assertEqual((context['goal'], context['leaf_id']), ('原型', leaf))
        self.assertNotIn('base64', json.dumps(context))
        note = {'op': 'append', 'chat_id': chat, 'leaf_id': leaf, 'text': '完成验证'}
        self.assertTrue(handle(view, note)['saved'])
        self.assertIn('完成验证', history.path(chat)[-1]['text'])
        with self.assertRaisesRegex(ValueError, '分支已变化'):
            handle(view, note)
        view.chat_id = history.create(temporary=True)
        with self.assertRaisesRegex(ValueError, '普通对话'):
            handle(view, {'op': 'read'})

    def test_stdio_roundtrip_through_running_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            bridge = Bridge(Path(directory), lambda data: {'value': data})
            try:
                messages = [{'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26'}},
                            {'id': 2, 'method': 'tools/list'},
                            {'id': 3, 'method': 'tools/call', 'params': {'name': 'read_current_chat'}}]
                result = subprocess.run([sys.executable, 'tools/talkapp_mcp.py'], check=True, capture_output=True,
                                        input='\n'.join(map(json.dumps, messages)) + '\n', text=True, timeout=10,
                                        env={**os.environ, 'TALKAPP_DATA_DIR': directory}, cwd=Path(__file__).resolve().parents[1])
                hello, tools, read = [json.loads(line)['result'] for line in result.stdout.splitlines()]
                self.assertEqual(hello['protocolVersion'], '2025-03-26')
                self.assertEqual(len(tools['tools']), 2)
                self.assertEqual(json.loads(read['content'][0]['text']), {'op': 'read'})
            finally:
                bridge.close()
