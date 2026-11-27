"""Read-only OpenCode V2 client over a verified HTTPS connection."""
import re
from urllib.parse import urlsplit

import httpx


def server_address(text):
    try:
        url = urlsplit(text.strip())
        port = url.port
    except ValueError:
        raise ValueError('OpenCode 地址无效') from None
    if (url.scheme != 'https' or not url.hostname or port == 0 or url.username is not None
            or url.password is not None or url.path not in ('', '/') or url.query or url.fragment
            or any(c.isspace() or c == '\\' for c in url.netloc)):
        raise ValueError('请输入 HTTPS 服务根地址，不要把密码或配对码放进地址')
    return 'https://' + url.netloc


class DirectClient:
    def __init__(self, address, password, *, transport=None):
        self.address = server_address(address)
        if not password:
            raise ValueError('请输入 OpenCode 服务密码')
        self._auth = ('opencode', password)
        self._transport = transport

    def _get(self, path, params=None):
        try:
            with httpx.Client(base_url=self.address, auth=self._auth, follow_redirects=False,
                              trust_env=False, timeout=10, transport=self._transport) as client:
                response = client.get(path, params=params)
        except httpx.RequestError:
            raise ValueError('无法连接 OpenCode，请检查私网、HTTPS 地址和证书') from None
        if response.status_code in (401, 403):
            raise ValueError('OpenCode 拒绝访问，请检查服务密码')
        if response.is_redirect:
            raise ValueError('服务返回重定向，请直接填写最终 HTTPS 地址')
        if not response.is_success:
            raise ValueError(f'OpenCode 接口返回 HTTP {response.status_code}')
        try:
            data = response.json()
        except (UnicodeError, ValueError):
            raise ValueError('服务未返回 OpenCode API 数据') from None
        return data.get('data', data) if isinstance(data, dict) else data

    def sessions(self):
        info = self._get('/api/info')
        rows = self._get('/api/session', {'limit': 20}) if isinstance(info, dict) else None
        if not isinstance(rows, list):
            raise ValueError('OpenCode 会话数据格式不兼容')
        return [(row['id'], str(row.get('title') or '未命名会话')[:120]) for row in rows[:20]
                if isinstance(row, dict) and isinstance(row.get('id'), str)
                and re.fullmatch(r'ses[a-zA-Z0-9_-]+', row['id'])]

    def messages(self, session_id):
        if not re.fullmatch(r'ses[a-zA-Z0-9_-]+', session_id):
            raise ValueError('无效的会话标识')
        rows = self._get(f'/api/session/{session_id}/message', {'limit': 20, 'order': 'desc'})
        if not isinstance(rows, list):
            raise ValueError('OpenCode 消息数据格式不兼容')
        lines = []
        for row in reversed(rows[:20]):
            if not isinstance(row, dict) or row.get('type') not in ('user', 'assistant'):
                continue
            if row['type'] == 'user' and isinstance(row.get('text'), str):
                text = row['text']
            else:
                parts = row.get('content')
                text = '\n'.join(part['text'] for part in (parts if isinstance(parts, list) else [])
                                 if isinstance(part, dict) and part.get('type') == 'text'
                                 and isinstance(part.get('text'), str))
            if text:
                lines.append(('我：' if row['type'] == 'user' else 'OpenCode：') + text[:4000])
        return '\n\n'.join(lines)
