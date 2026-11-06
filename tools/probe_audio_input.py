"""Send synthetic test audio directly to the configured model, without ASR."""
import base64
import json
import tempfile
from pathlib import Path

import httpx
import win32com.client

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from talkapp.storage import Config


def main():
    config = Config.load()
    config.validate()
    with tempfile.TemporaryDirectory(dir='F:/TalkAppEnvs/voice-tmp') as folder:
        path = Path(folder) / 'probe.wav'
        voice = win32com.client.Dispatch('SAPI.SpVoice')
        for item in voice.GetVoices():
            if '804' in str(item.GetAttribute('Language')).lower().split(';'):
                voice.Voice = item
                break
        output = win32com.client.Dispatch('SAPI.SpFileStream')
        output.Open(str(path), 3)
        voice.AudioOutputStream = output
        voice.Speak('我今天买了三个苹果，明天下午两点去图书馆。')
        output.Close()
        audio = base64.b64encode(path.read_bytes()).decode('ascii')
    body = {'model': config.model, 'stream': True, 'messages': [
        {'role': 'user', 'content': [
            {'type': 'text', 'text': '请直接听这段音频，复述说话内容。听不到请明确说明，不要猜测。'},
            {'type': 'input_audio', 'input_audio': {'data': audio, 'format': 'wav'}}]}]}
    with httpx.Client(timeout=90) as client:
        with client.stream('POST', config.api_base_url.rstrip('/') + '/chat/completions',
                           headers={'Authorization': 'Bearer ' + config.api_key}, json=body) as response:
            print('HTTP_STATUS', response.status_code)
            if response.status_code >= 400:
                # Do not dump provider response bodies or requests containing credentials/audio.
                response.read()
                try:
                    error = response.json().get('error', {})
                    message = error.get('message', '') if isinstance(error, dict) else str(error)
                    message = message.replace(config.api_key, '[REDACTED]').replace(audio, '[AUDIO]')
                    print('PROVIDER_ERROR', message[:1200])
                except (ValueError, AttributeError):
                    pass
                print('AUDIO_REQUEST_REJECTED')
                return
            text = ''
            if 'text/event-stream' not in response.headers.get('content-type', ''):
                response.read()
                value = response.json()
                text = value.get('choices', [{}])[0].get('message', {}).get('content', '')
            else:
                for line in response.iter_lines():
                    if not line.startswith('data:'):
                        continue
                    value = line[5:].strip()
                    if value == '[DONE]':
                        break
                    event = json.loads(value)
                    choices = event.get('choices', [])
                    if choices:
                        part = choices[0].get('delta', {}).get('content', '')
                        if isinstance(part, str):
                            text += part
            print('MODEL_RESPONSE', text[:2000])


if __name__ == '__main__':
    main()
