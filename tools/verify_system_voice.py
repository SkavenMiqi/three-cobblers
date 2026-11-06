"""Check Windows SAPI availability and synthesize a short sentence without playback."""
import tempfile
from pathlib import Path
import win32com.client

with tempfile.TemporaryDirectory() as folder:
    voice = win32com.client.Dispatch('SAPI.SpVoice')
    voices = voice.GetVoices()
    print('Installed voices:', voices.Count)
    for item in voices:
        print(item.GetDescription(), item.GetAttribute('Language'))
        if '804' in str(item.GetAttribute('Language')).lower().split(';'):
            voice.Voice = item
    stream = win32com.client.Dispatch('SAPI.SpFileStream')
    output = Path(folder) / 'test.wav'
    stream.Open(str(output), 3)
    voice.AudioOutputStream = stream
    voice.Speak('你好，语音朗读已准备好。')
    stream.Close()
    assert output.stat().st_size > 44
    print('SYSTEM_VOICE_SYNTHESIS_OK', output.stat().st_size)
