"""Replay the latest failed audio to its configured parser; never print secrets/audio."""
import json
import sqlite3
import subprocess
import tempfile
import threading
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from talkapp.collaboration import CollaborationConfig, parse_audio
from talkapp.client import stream_reply
adb = 'F:/TalkAppEnvs/android/platform-tools/adb.exe'
def read(name):
    return subprocess.check_output([adb, 'exec-out', 'run-as', 'org.skaven.talkapp', 'cat', 'files/' + name], timeout=20)
profiles = json.loads(read('profiles.json'))
config = CollaborationConfig(**json.loads(read('collaboration.json')))
with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / 'db'
    path.write_bytes(read('history.db'))
    db = sqlite3.connect(path)
    row = db.execute("SELECT image FROM messages WHERE image LIKE '{%' ORDER BY id DESC LIMIT 1").fetchone()
    db.close()
    if not row:
        raise SystemExit('No audio message')
    def call(model, rows, delta, cancel, **kwargs):
        return stream_reply(model, rows, delta, cancel, **kwargs)
    try:
        text = parse_audio(config, profiles, row[0], threading.Event(), call)
        print('PARSER_SUCCESS', 'characters=', len(text))
    except Exception as exc:
        import traceback
        traceback.print_tb(exc.__traceback__)
        message = str(exc)
        for profile in profiles:
            message = message.replace(profile.get('api_key', '') or '___', '[REDACTED]')
        print('PARSER_FAILURE', type(exc).__name__, message[:600])
