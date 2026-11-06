import json
from dataclasses import dataclass, asdict
from .storage import data_dir


@dataclass
class ReadingConfig:
    mode: str = 'auto'
    search_key: str = ''
    search_endpoint: str = 'https://api.tavily.com/search'

    @classmethod
    def load(cls):
        try:
            raw = json.loads((data_dir() / 'reading.json').read_text(encoding='utf-8'))
            return cls(**{key: value for key, value in raw.items() if key in cls.__dataclass_fields__})
        except (ValueError, OSError, TypeError):
            return cls()

    def save(self):
        from urllib.parse import urlparse
        url = urlparse(self.search_endpoint)
        if url.scheme != 'https' or not url.hostname:
            raise ValueError('搜索接口需要HTTPS')
        path = data_dir() / 'reading.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(asdict(self), ensure_ascii=False), encoding='utf-8')
        temporary.chmod(0o600)
        temporary.replace(path)
