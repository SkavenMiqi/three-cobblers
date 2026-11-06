"""Measure captured audio locally without printing spoken content or credentials."""
import base64
import io
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path
import av
import numpy as np

adb = 'F:/TalkAppEnvs/android/platform-tools/adb.exe'
raw = subprocess.check_output([adb, 'exec-out', 'run-as', 'org.skaven.talkapp', 'cat', 'files/history.db'], timeout=20)
with tempfile.TemporaryDirectory(dir='F:/TalkAppEnvs/voice-tmp') as directory:
    path = Path(directory) / 'history.db'
    path.write_bytes(raw)
    db = sqlite3.connect(path)
    rows = db.execute("SELECT id,image FROM messages WHERE image LIKE '{%' ORDER BY id DESC LIMIT 5").fetchall()
    db.close()
    for message_id, value in rows:
        audio = json.loads(value).get('audio')
        if not audio:
            continue
        data = base64.b64decode(audio['data'])
        try:
            with av.open(io.BytesIO(data)) as container:
                stream = container.streams.audio[0]
                frames = [frame.to_ndarray().astype(np.float32).flatten() for frame in container.decode(audio=0)]
                samples = np.concatenate(frames) if frames else np.array([])
                if samples.size and np.max(np.abs(samples)) > 2:
                    samples /= 32768
                print(json.dumps({'message_id': message_id, 'bytes': len(data), 'format': audio['format'],
                    'codec': stream.codec_context.name, 'sample_rate': stream.codec_context.sample_rate,
                    'seconds': round(float(samples.size / max(1, stream.codec_context.sample_rate)), 2),
                    'rms': round(float(np.sqrt(np.mean(samples ** 2))), 5) if samples.size else 0,
                    'peak': round(float(np.max(np.abs(samples))), 5) if samples.size else 0}))
        except Exception as exc:
            print(message_id, 'DECODE_FAILED', type(exc).__name__)
