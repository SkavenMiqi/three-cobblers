"""Archive incompatible generated lxml source so p4a fetches the pinned version."""
from pathlib import Path
from datetime import datetime
root = Path('/home/skaven/android-build/project/.buildozer/android/platform/build-arm64-v8a/build/other_builds/lxml')
if root.exists():
    target = root.with_name('lxml-backup-' + datetime.now().strftime('%H%M%S'))
    root.rename(target)
    print('Archived', target)
