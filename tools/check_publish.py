"""Inspect publish candidates without printing potential secret values."""
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
files = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=root).decode().split('\0')
patterns = [re.compile(r'\bsk-[a-zA-Z0-9_-]{20,}'), re.compile(r'\bgh[pousr]_[a-zA-Z0-9]{20,}'),
            re.compile(r'github_pat_[a-zA-Z0-9_]{20,}')]
found = []
for name in files:
    if not name or Path(name).suffix.lower() in ('.ttf', '.png', '.jpg', '.ico'):
        continue
    try:
        content = (root / name).read_text(encoding='utf-8')
    except (ValueError, OSError):
        continue
    if any(pattern.search(content) for pattern in patterns):
        found.append(name)
print('Candidate files:', sum(bool(value) for value in files))
print('Potential secret files:', found)
if found:
    raise SystemExit(1)
