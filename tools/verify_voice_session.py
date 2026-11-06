"""Simulated continuous turn-taking without opening the microphone or billing API."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory() as directory:
    os.environ['TALKAPP_DATA_DIR'] = directory
    from main import TalkApp
    from kivy.clock import Clock
    from talkapp.storage import Config
    Config(api_key='test').save()
    app = TalkApp()
    completed = [False]
    calls = [0]

    def recorder(cancel, finish=None, progress=None, device=None):
        cancel.wait(.15)
        return (b'audio', 'voice.wav') if not cancel.is_set() else None

    def reply(config, rows, delta, cancel, **kwargs):
        if kwargs.get('prompt', '').startswith('维护长期'):
            return 'SKIP'
        delta('你好，我们继续聊。')
        return '你好，我们继续聊。'

    def begin(_):
        def speak(text):
            calls[0] += 1
            Clock.schedule_once(lambda _: app.chat.speech_notice('朗读完成'), .1)
        app.chat.speaker.speak = speak
        app.chat.voice()
        Clock.schedule_once(check, 2)

    def check(_):
        session = app.chat.voice_session
        assert calls[0] >= 1
        session.dismiss()
        assert not session.active and session.token.is_set()
        completed[0] = True
        print('VOICE_SESSION_OK: auto send, playback, resume, exit')
        app.stop()

    with patch('talkapp.voice_chat.record_until_silence', side_effect=recorder), \
         patch('talkapp.voice_chat.transcribe', return_value='你好，今天过得如何？'), \
         patch('talkapp.ui.stream_reply', side_effect=reply):
        Clock.schedule_once(begin, .4)
        app.run()
    assert completed[0]
