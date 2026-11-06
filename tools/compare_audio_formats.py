import sys
import io
import json
import base64
import sqlite3
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
import av
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from talkapp.storage import Config
from talkapp.client import stream_reply
adb = 'F:/TalkAppEnvs/android/platform-tools/adb.exe'
def remote(name):
    return subprocess.check_output([adb, 'exec-out', 'run-as', 'org.skaven.talkapp', 'cat', 'files/' + name], timeout=20)
profiles = json.loads(remote('profiles.json'))
routing = json.loads(remote('collaboration.json'))
profile = next(item for item in profiles if item['api_base_url'].rstrip('/') + '|' + item['model'] == routing['audio_parser'])
with tempfile.TemporaryDirectory(dir='F:/TalkAppEnvs/voice-tmp') as directory:
    path = Path(directory) / 'db'
    path.write_bytes(remote('history.db'))
    db = sqlite3.connect(path)
    value = db.execute("SELECT image FROM messages WHERE image LIKE '{%' ORDER BY id DESC LIMIT 1").fetchone()[0]
    db.close()
data = base64.b64decode(json.loads(value)['audio']['data'])
output = io.BytesIO()
with av.open(io.BytesIO(data)) as container, wave.open(output, 'wb') as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(16000)
    resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
    for frame in container.decode(audio=0):
        for converted in resampler.resample(frame):
            wav.writeframes(converted.to_ndarray().tobytes())
for format, raw in [('m4a', data), ('wav', output.getvalue())]:
    payload = json.dumps({'audio': {'data': base64.b64encode(raw).decode(), 'format': format}})
    try:
        import httpx
        from talkapp.client import messages_for_api
        cfg = Config(**{k:v for k,v in profile.items() if k in Config.__dataclass_fields__})
        with httpx.Client(timeout=90) as client:
            response = client.post(cfg.api_base_url.rstrip('/') + '/chat/completions',
                headers={'api-key': cfg.api_key}, json={'model': cfg.model, 'messages': messages_for_api(
                    [('user', '请听录音并转写内容。', payload)], ''), 'stream': False,
                    'max_completion_tokens': 4096, 'thinking': {'type': 'disabled'}})
            body = response.json()
            choice = (body.get('choices') or [{}])[0]
            message = choice.get('message') or {}
            print('RAW', format, response.status_code, 'finish', choice.get('finish_reason'),
                  'content_chars', len(message.get('content') or ''), 'reasoning_chars', len(message.get('reasoning_content') or ''),
                  'usage', body.get('usage'))
        text = stream_reply(Config(**{k:v for k,v in profile.items() if k in Config.__dataclass_fields__}),
            [('user', '请准确听取录音，只输出说话内容，不回答；听不清输出[听不清]。', payload)],
            lambda _: None, threading.Event(), prepared=True, task='audio_parse', prompt='忠实转写用户录音，不猜测。')
        print(format, 'UNCLEAR' if '听不清' in text else 'TRANSCRIPT_RETURNED', 'characters', len(text))
    except Exception as exc:
        print(format, type(exc).__name__)
