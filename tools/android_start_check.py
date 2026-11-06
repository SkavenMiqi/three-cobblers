"""Capture only this application's live startup, without unrelated device logs."""
import subprocess
import threading
import time
from pathlib import Path
adb = 'F:/TalkAppEnvs/android/platform-tools/adb.exe'
root = Path(__file__).resolve().parents[1]
subprocess.run([adb, 'shell', 'am', 'force-stop', 'org.skaven.talkapp'], check=True)
process = subprocess.Popen([adb, 'logcat', '-v', 'brief', 'python:I', 'AndroidRuntime:E', 'libc:F', '*:S'],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
lines = []
def capture():
    for line in iter(process.stdout.readline, b''):
        lines.append(line)
thread = threading.Thread(target=capture, daemon=True)
thread.start()
subprocess.run([adb, 'shell', 'am', 'start', '-W', '-n', 'org.skaven.talkapp/org.kivy.android.PythonActivity'])
time.sleep(18)
process.terminate()
thread.join(3)
path = root / 'backups/android-startup.log'
path.write_bytes(b''.join(lines))
print(path)
subprocess.run([adb, 'shell', 'pidof', 'org.skaven.talkapp'])
