"""Archive unrelated upstream files while keeping the chat's shared assets."""
import subprocess
import shutil
from pathlib import Path
from datetime import datetime

root = Path(__file__).resolve().parents[1]
upstream = root / 'fitness-original'
keep = {'main.py', 'topbar.py', 'sounds.py', 'theme.py', 'config/__init__.py',
        'config/theme.py', 'utils/__init__.py', 'utils/instrument.py',
        'assets/__init__.py', 'assets/fonts/__init__.py', 'assets/fonts/roboto_regular.ttf',
        'assets/fonts/symbols.ttf', 'assets/icons/icon.png', '.gitignore'}
archive = root / 'backups' / ('fitness-unrelated-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=upstream).decode().split('\0')
count = 0
for name in files:
    if not name or name in keep:
        continue
    path = root / name
    if not path.is_file():
        continue
    target = archive / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), target)
    count += 1
print(f'Archived {count} unrelated files to {archive}')
previous = root / 'backups' / 'before-original-20261105-153948'
for name in ('README.md', 'buildozer.spec'):
    shutil.copy2(previous / name, root / name)
