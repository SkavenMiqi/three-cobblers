"""Synthesize a Chinese test phrase and send it to the actual local ASR server."""
import sys
import tempfile
from pathlib import Path
import win32com.client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from talkapp.voice_chat import transcribe
import threading

with tempfile.TemporaryDirectory(dir='F:/TalkAppEnvs/voice-tmp') as folder:
    voice = win32com.client.Dispatch('SAPI.SpVoice')
    for item in voice.GetVoices():
        if '804' in str(item.GetAttribute('Language')).lower().split(';'):
            voice.Voice = item
    stream = win32com.client.Dispatch('SAPI.SpFileStream')
    path = Path(folder) / 'test.wav'
    stream.Open(str(path), 3)
    voice.AudioOutputStream = stream
    voice.Speak('你好，我想和你聊聊今天发生的事情。')
    stream.Close()
    result = transcribe(path.read_bytes(), 'test.wav', 'http://127.0.0.1:50002/v1/audio/transcriptions', threading.Event())
    assert result, 'Empty transcription'
    print('VOICE_ASR_ROUNDTRIP_OK:', result)
