"""Build the source-only Harness backend included in the Android app."""
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from talkapp.harness_setup import BUNDLE_ASSET

FILES = (
    'talkapp/__init__.py',
    'talkapp/chat_sync.py',
    'talkapp/client.py',
    'talkapp/harness_lan.py',
    'talkapp/lan_pairing.py',
    'talkapp/opencode_chat.py',
    'talkapp/opencode_tasks.py',
    'talkapp/output_modes.py',
    'talkapp/progress_sync.py',
    'talkapp/storage.py',
    'tools/talkapp_harness.py',
)


def build(destination):
    with ZipFile(destination / BUNDLE_ASSET, 'w', compression=ZIP_DEFLATED) as bundle:
        for name in FILES:
            bundle.write(ROOT / name, name)
        bundle.writestr('requirements-harness.txt', 'certifi\ncryptography\nPillow>=10.4,<13\nqrcode==8.2\n')


if __name__ == '__main__':
    build(Path(sys.argv[1]))
