from pathlib import Path
import tarfile

root = Path('/home/skaven/android-build')
target = root / 'p4a-local'
target.mkdir(exist_ok=True)
with tarfile.open('/mnt/f/TalkAppEnvs/p4a-2024.tar.gz') as archive:
    for member in archive.getmembers():
        parts = Path(member.name).parts[1:]
        if not parts:
            continue
        member.name = str(Path(*parts))
        archive.extract(member, target)
print(target)
