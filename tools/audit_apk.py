import io
import tarfile
import zipfile
from pathlib import Path

apk = next((Path(__file__).resolve().parents[1] / 'bin').glob('*.apk'))
bad = []
def check(name, data):
    if data[:4] == b'\x7fELF' and int.from_bytes(data[18:20], 'little') != 183:
        bad.append(name)
with zipfile.ZipFile(apk) as package:
    for item in package.infolist():
        if item.filename.endswith('.so'):
            check(item.filename, package.read(item))
        if item.filename.endswith('.tar') or item.filename.endswith('.mp3'):
            data = package.read(item)
            try:
                with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                    for member in archive:
                        if member.isfile() and member.name.endswith('.so'):
                            check(member.name, archive.extractfile(member).read())
            except tarfile.ReadError:
                pass
print('APK', apk, 'BYTES', apk.stat().st_size)
print('NON_ARM64_LIBRARIES', bad)
if bad:
    raise SystemExit(1)
