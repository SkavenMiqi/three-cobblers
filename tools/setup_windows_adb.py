from pathlib import Path
import zipfile

root = Path('F:/TalkAppEnvs')
with zipfile.ZipFile(root / 'platform-tools-windows.zip') as archive:
    archive.extractall(root / 'android')
print(root / 'android/platform-tools/adb.exe')
