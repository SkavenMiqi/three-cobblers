from pathlib import Path
import subprocess
root = Path(__file__).resolve().parents[1]
adb = 'F:/TalkAppEnvs/android/platform-tools/adb.exe'
data = subprocess.check_output([adb, 'exec-out', 'screencap', '-p'], timeout=15)
path = root / 'backups/android-screen.png'
path.write_bytes(data)
print(path)
