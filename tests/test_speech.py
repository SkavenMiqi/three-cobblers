import io
import json
import tempfile
import unittest
import wave
from unittest.mock import patch

from talkapp.speech import SpeechConfig, spoken_text, sentences, request_wav


class SpeechTests(unittest.TestCase):
    def test_markdown_to_speech_and_sentence_chunks(self):
        text = spoken_text('# 标题\n**你好** [例子](https://example.com)\n```python\nprint(1)\n```')
        self.assertIn('你好 例子', text)
        self.assertNotIn('print', text)
        self.assertNotIn('https', text)
        pieces = sentences('长' * 700 + '。最后一句。', 240)
        self.assertTrue(all(len(item) <= 240 for item in pieces))
        self.assertEqual(''.join(pieces), '长' * 700 + '。最后一句。')

    def test_config_private_network_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'TALKAPP_DATA_DIR': folder}):
            config = SpeechConfig(endpoint='http://192.168.1.2:50001/v1/audio/speech', auto_read=True)
            config.save()
            self.assertEqual(SpeechConfig.load(), config)
            with self.assertRaises(ValueError):
                SpeechConfig(endpoint='http://example.com/speech').validate()
            with self.assertRaises(ValueError):
                SpeechConfig(speed=4).validate()

    def test_endpoint_contract_and_wav_validation(self):
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(b'\0\0' * 100)
        with patch('urllib.request.urlopen', return_value=io.BytesIO(buffer.getvalue())) as send:
            data = request_wav(SpeechConfig(endpoint='https://example.com/tts'), '你好')
            self.assertTrue(data.startswith(b'RIFF'))
            request = send.call_args.args[0]
            payload = json.loads(request.data)
            self.assertEqual(payload['input'], '你好')
            self.assertEqual(payload['response_format'], 'wav')
        with patch('urllib.request.urlopen', return_value=io.BytesIO(b'invalid')):
            with self.assertRaises((wave.Error, EOFError)):
                request_wav(SpeechConfig(endpoint='https://example.com/tts'), '你好')
