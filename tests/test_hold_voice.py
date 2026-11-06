import unittest
from talkapp.hold_voice import audio_message
from talkapp.client import messages_for_api, image_list, audio_input


class AudioInputTests(unittest.TestCase):
    def test_audio_is_sent_as_audio_not_image_or_transcription(self):
        payload = audio_message(b'test-wave', 'wav')
        self.assertEqual(image_list(payload), [])
        self.assertEqual(audio_input(payload)['format'], 'wav')
        content = messages_for_api([('user', '（语音消息）', payload)], '')[0]['content']
        self.assertEqual(content[0]['type'], 'input_audio')
        self.assertEqual(content[0]['input_audio']['data'], 'dGVzdC13YXZl')
