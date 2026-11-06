import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from talkapp.client import image_data, messages_for_api, stream_reply
from talkapp.storage import Config, History


class CoreTests(unittest.TestCase):
    def test_mimo_transcription_disables_reasoning(self):
        class Response(io.BytesIO):
            headers = {'Content-Type': 'text/event-stream'}
        with patch('urllib.request.urlopen', return_value=Response(b'data: [DONE]\n')) as send:
            stream_reply(Config(api_key='test', api_base_url='https://api.xiaomimimo.com/v1'),
                         [('user', 'hi', None)], lambda _: None, threading.Event(), task='audio_parse')
        self.assertEqual(json.loads(send.call_args.args[0].data)['thinking'], {'type': 'disabled'})
    def test_provider_null_tool_calls_are_valid_text_stream(self):
        class Response(io.BytesIO):
            headers = {'Content-Type': 'text/event-stream'}
        data = b'data: {"choices":[{"delta":{"content":"heard","tool_calls":null}}]}\n\ndata: {"choices":[{"delta":null,"finish_reason":"stop"}]}\n\ndata: [DONE]\n'
        with patch('urllib.request.urlopen', return_value=Response(data)):
            result = stream_reply(Config(api_key='test'), [('user', 'hi', None)], lambda _: None, threading.Event())
        self.assertEqual(result, 'heard')
    def test_history_survives_reopen_and_deletes_messages(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "history.db"
            history = History(path)
            chat = history.create()
            history.append(chat, "user", "你好", "data:image/jpeg;base64,AA==")
            history.append(chat, "assistant", "你好呀")
            history.close()
            history = History(path)
            self.assertEqual(history.chats()[0][1], "你好")
            self.assertEqual(len(history.messages(chat)), 2)
            history.rename(chat, "日常")
            self.assertEqual(history.chats()[0][1], "日常")
            history.delete(chat)
            self.assertEqual(history.messages(chat), [])
            history.close()

    def test_config_roundtrip_and_https_validation(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict("os.environ", {"TALKAPP_DATA_DIR": folder}):
            config = Config(api_key="test-key")
            config.save()
            self.assertEqual(Config.load(), config)
            config.api_base_url = "http://example.com"
            with self.assertRaises(ValueError):
                config.save()

    def test_multimodal_context_and_turn_limit(self):
        rows = [("user", "看看", "data:image/jpeg;base64,AA=="), ("assistant", "图片", None)]
        result = messages_for_api(rows, "助手")
        self.assertEqual(result[1]["content"][1]["type"], "image_url")
        long = [("user" if i % 2 == 0 else "assistant", "x", None) for i in range(100)]
        context = messages_for_api(long, "助手")
        self.assertEqual(len(context), 41)
        self.assertEqual(context[1]["role"], "user")

    def test_image_is_resized_and_encoded(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "image.png"
            Image.new("RGBA", (2000, 1000)).save(path)
            self.assertTrue(image_data(path).startswith("data:image/jpeg;base64,"))

    def test_stream_and_provider_prefix(self):
        class Response(io.BytesIO):
            headers = {"Content-Type": "text/event-stream"}
        response = Response(b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\ndata: [DONE]\n')
        config = Config(api_key="test", api_base_url="https://example.com/zen/go")
        values = []
        with patch("urllib.request.urlopen", return_value=response) as request:
            text = stream_reply(config, [("user", "hi", None)], values.append, threading.Event())
        self.assertEqual(text, "hello")
        self.assertEqual(values, ["hello"])
        self.assertEqual(request.call_args.args[0].full_url, "https://example.com/zen/go/chat/completions")

    def test_truncated_stream_preserves_delta_but_reports_failure(self):
        class Response(io.BytesIO):
            headers = {"Content-Type": "text/event-stream"}
        values = []
        response = Response(b'data: {"choices":[{"delta":{"content":"partial"}}]}\n')
        with patch('urllib.request.urlopen', return_value=response):
            with self.assertRaisesRegex(ValueError, '连接提前结束'):
                stream_reply(Config(api_key='test'), [('user', 'hi', None)], values.append, threading.Event())
        self.assertEqual(values, ['partial'])


if __name__ == "__main__":
    unittest.main()
