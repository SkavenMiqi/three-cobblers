from pathlib import Path
from datetime import datetime
import shutil

root = Path(__file__).resolve().parents[1]
source = root / 'fitness-original'
backup = root / 'backups' / ('ui-v230-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
mapping = {name: name for name in ('config/theme.py', 'utils/fx.py', 'utils/skin.py',
           'utils/appearance.py', 'utils/instrument.py', 'llm_client.py')}
mapping['ai_settings.py'] = 'talkapp/legacy_settings.py'
mapping['config/theme.py'] = 'config/theme.py'
for src, dst in mapping.items():
    target = root / dst
    if target.exists():
        saved = backup / dst
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, saved)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / src, target)
shutil.copy2(source / 'config/theme.py', root / 'talkapp/theme.py')
p = root / 'talkapp/legacy_settings.py'
p.write_text(p.read_text(encoding='utf-8').replace('from llm_config import LLMConfig',
             'from talkapp.storage import Config as LLMConfig'), encoding='utf-8')
p = root / 'utils/appearance.py'
p.write_text(p.read_text(encoding='utf-8').replace('from utils.platform import _data_dir',
             'from talkapp.storage import data_dir as _data_dir'), encoding='utf-8')
print('Updated v2.3.0 shared visual components and AI settings; backup:', backup)
