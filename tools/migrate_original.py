"""Copy the exact tracked upstream project into the application root."""
from pathlib import Path
import shutil
import subprocess
from datetime import datetime

root = Path(__file__).resolve().parents[1]
source = root / 'fitness-original'
files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=source).decode().split('\0')
backup = root / 'backups' / ('before-original-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
copied = 0
for name in files:
    if not name or name == '.gitignore':
        continue
    src, dst = source / name, root / name
    if dst.exists():
        saved = backup / name
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dst, saved)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if src.read_bytes() != dst.read_bytes():
        raise RuntimeError('Copy mismatch: ' + name)
    copied += 1
print(f'Copied and byte-verified {copied} upstream files')
print(f'Backup: {backup}')
