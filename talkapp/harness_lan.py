"""Paired, single-workspace OpenCode access without a desktop UI."""
import json
import re
import threading
from pathlib import Path

from . import lan_pairing as lan, opencode_tasks

PORT = 47632
PREFIX = 'HARNESS1-'
MANIFEST = {'protocol': 1, 'client': 'TalkApp', 'features': ['observe_text', 'delegate', 'task_status', 'permission_reply']}


class HarnessHost(lan.PairingHost):
    def __init__(self, root, address, directory, port=PORT, *, request=None):
        workspace = Path(directory).resolve(strict=True)
        if not workspace.is_dir():
            raise ValueError('Harness 工作目录必须是文件夹')
        self.directory = str(workspace)
        self.session_file = Path(root) / 'session.json'
        self.session_lock = threading.Lock()
        cli = opencode_tasks.executable() if request is None else None

        def request_opencode(method, route, body=None):
            reply = opencode_tasks.api(cli, method, route, body, timeout=8)
            if route == '/api/info':
                # OpenCode can return service metadata without the session API's envelope.
                return reply.get('data', reply)
            return reply['data']

        self.request = request or request_opencode
        super().__init__(root, address, port)
        self.sync_enabled = True

    def invitation(self):
        return PREFIX + super().invitation()[len(lan.PREFIX):]

    def _sync(self, connection, request):
        lan._write(connection, {'ok': True})
        args = lan._frame(connection, limit=32000)
        try:
            with self.session_lock:
                with self.lock:
                    if self.stop.is_set() or not self._respond(request).get('ok'):
                        return
                value = self.chat(args)
            lan._frame(connection, {'ok': True, 'data': value}, limit=160000)
        except (ValueError, OSError, KeyError, TypeError, opencode_tasks.subprocess.SubprocessError):
            lan._frame(connection, {'ok': False}, limit=160000)

    def chat(self, args):
        if args.get('action') == 'configure':
            manifest = args.get('manifest')
            if not isinstance(manifest, dict) or type(manifest.get('protocol')) is not int or manifest != MANIFEST:
                return {'configured': False, 'protocol': MANIFEST['protocol']}
            file = self.session_file.with_name('client-config.json')
            settings = {'manifest': MANIFEST, 'peer': lan._load(self.peer_file), 'adapter': 'opencode-v2'}
            if lan._load(file) != settings:
                self.request('get', '/api/info')
                lan._save(file, json.dumps(settings).encode())
            return {'configured': True, 'protocol': 1, 'features': MANIFEST['features']}
        scope = args.get('scope')
        if scope is not None and not lan._hex(scope, 32):
            raise ValueError('Invalid conversation scope')
        if scope:
            settings = lan._load(self.session_file.with_name('client-config.json'))
            if not isinstance(settings, dict) or settings.get('manifest') != MANIFEST or settings.get('peer') != lan._load(self.peer_file):
                raise ValueError('Client not configured')
        session_file = self.session_file if scope is None else self.session_file.with_name(f'chat-{scope}.json')
        state = lan._load(session_file)
        state = state if isinstance(state, dict) and state.get('directory') == self.directory else {}
        sid = state.get('session')
        if sid is not None and not re.fullmatch(r'ses[a-zA-Z0-9_-]+', sid):
            raise ValueError('Invalid stored session')
        op = args.get('action')
        if scope and (op == 'observe' or (op == 'send' and 'rows' in args)):
            rows, revision = args.get('rows'), args.get('revision')
            if (type(revision) is not int or not 0 < revision < 2**63 or not isinstance(rows, list) or len(rows) > 20
                    or any(not isinstance(row, list) or len(row) != 2 or row[0] not in ('user', 'assistant')
                           or not isinstance(row[1], str) for row in rows)
                    or sum(len(row[1].encode('utf-8')) for row in rows) > 5600):
                raise ValueError('Invalid conversation snapshot')
            if revision >= state.get('revision', 0):
                state.update(directory=self.directory, revision=revision, observed=rows)
                lan._save(session_file, json.dumps(state, ensure_ascii=False).encode('utf-8'))
            if op == 'observe':
                return True
        if op == 'send':
            text, key = args.get('text'), args.get('id')
            if not isinstance(text, str) or not text.strip() or len(text.encode('utf-8')) > 8000 or not lan._hex(key, 32):
                raise ValueError('Invalid message')
            if not sid:
                sid = self.request('post', '/api/session', {'title': 'TalkApp · 手机直连', 'agent': 'build',
                                    'location': {'directory': self.directory}})['id']
                if not isinstance(sid, str) or not re.fullmatch(r'ses[a-zA-Z0-9_-]+', sid):
                    raise ValueError('Invalid session')
                state.update(directory=self.directory, session=sid, submitted={})
            if key not in state['submitted']:
                state['submitted'][key] = False
                lan._save(session_file, json.dumps(state).encode())
                context = state.get('observed') or []
                message = opencode_tasks.prompt(text, context) if context else text
                self.request('post', f'/api/session/{sid}/prompt', {'text': message})
                state['submitted'][key] = True
                lan._save(session_file, json.dumps(state).encode())
            if not state['submitted'][key]:
                raise ValueError('Submission unknown')
            return True
        if op == 'decision' and sid:
            rid, decision = args.get('request_id'), args.get('decision')
            if not isinstance(rid, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', rid) or decision not in ('once', 'reject'):
                raise ValueError('Invalid permission decision')
            base = f'/api/session/{sid}/permission'
            if not any(item.get('id') == rid and item.get('sessionID') == sid for item in self.request('get', base)):
                raise ValueError('Permission no longer pending')
            self.request('post', f'{base}/{rid}/reply', {'decision': decision})
            return True
        if op != 'read':
            raise ValueError('Unsupported operation')
        if not sid:
            return {'lines': [], 'permission': None, 'latest_user': None, 'finished': None, 'answer': ''}
        base = f'/api/session/{sid}'
        rows = self.request('get', base + '/message?limit=20&order=desc')
        lines = []
        for row in reversed(rows[:20]):
            if row.get('type') == 'user':
                text = row.get('text') or ''
                who = '我'
            elif row.get('type') == 'assistant':
                text = '\n'.join(p['text'] for p in row.get('content', []) if p.get('type') == 'text')
                who = 'OpenCode'
            else:
                continue
            if text:
                lines.append([who, text[:1800]])
        permission = next((item for item in self.request('get', base + '/permission')
                           if item.get('sessionID') == sid and isinstance(item.get('id'), str)), None)
        latest_user = next((i for i, row in enumerate(rows) if row.get('type') == 'user'), None)
        info = self.request('get', base) if args.get('scope') else {}
        outcome = info.get('outcome') if isinstance(info, dict) else None
        answer = '\n'.join(p['text'] for row in reversed(rows[:latest_user]) if row.get('type') == 'assistant'
                           for p in row.get('content', []) if p.get('type') == 'text') if latest_user is not None else ''
        return {'lines': lines, 'latest_user': rows[latest_user].get('id') if latest_user is not None else None,
                'finished': {'succeeded': '已完成', 'failed': '执行失败', 'interrupted': '执行中断'}.get(outcome), 'answer': answer[:2400],
                'permission': {'id': permission['id'], 'description': json.dumps(
            {key: permission[key] for key in ('permission', 'patterns', 'action', 'resource', 'metadata') if key in permission},
            ensure_ascii=False)[:1200]} if permission else None}


def pair(root, code):
    if not code.startswith(PREFIX):
        raise ValueError('请扫描 Harness 后台专用二维码')
    lan.pair(root, lan.PREFIX + code[len(PREFIX):])


class HostUnavailable(ValueError):
    """The configured LAN endpoint could not be reached."""


def configure(root):
    try:
        result = call(root, 'configure', manifest=MANIFEST)
    except OSError:
        raise HostUnavailable('找不到 Harness，请检查电脑后台和局域网。') from None
    except (ValueError, KeyError):
        raise ValueError('已保存配对，但未能配置 Harness；请检查电脑后台是否已更新并运行。') from None
    if result != {'configured': True, 'protocol': 1, 'features': MANIFEST['features']}:
        raise ValueError('Harness 协作协议不兼容，请更新电脑后台。')


def call(root, action, **payload):
    address, port, fingerprint, secret = lan._computer(root)
    with lan._connected(address, port, fingerprint) as secure:
        lan._write(secure, {'op': 'sync', 'secret': secret})
        if not lan._read(secure).get('ok'):
            raise ValueError('配对已解除，请重新扫码')
        lan._frame(secure, {'action': action, **payload}, limit=32000)
        reply = lan._frame(secure, limit=160000)
    if not reply.get('ok'):
        raise ValueError('未能确认 OpenCode 状态，未自动重发')
    return reply['data']
