"""Inspect only routing metadata and message error fields, never print credentials/audio."""
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path
adb = 'F:/TalkAppEnvs/android/platform-tools/adb.exe'
def remote(path):
    return subprocess.check_output([adb, 'exec-out', 'run-as', 'org.skaven.talkapp', 'cat', path], timeout=15)
for name in ('collaboration.json', 'profiles.json'):
    try:
        value = json.loads(remote('files/' + name))
        if name == 'profiles.json':
            value = [{'model': row.get('model'), 'base': row.get('api_base_url')} for row in value]
        print(name, json.dumps(value, ensure_ascii=True))
    except Exception:
        print('Not found at files/', name)
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'history.db'
    path.write_bytes(remote('files/history.db'))
    db = sqlite3.connect(path)
    print('Recent errors:', db.execute("SELECT id,state,error,model FROM messages WHERE role='assistant' ORDER BY id DESC LIMIT 5").fetchall())
    db.close()
