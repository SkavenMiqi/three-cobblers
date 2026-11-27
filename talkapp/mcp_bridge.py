"""Desktop-only bridge to the live TalkApp view, using authenticated loopback IPC."""
import json
import secrets
import socket
import socketserver
import threading
from hmac import compare_digest

from .lan_pairing import _frame, _save

ENDPOINT = 'mcp-desktop.json'
MAX_NOTE = 6000


def handle(view, request):
    """Run on the UI thread. Never expose arbitrary conversations or commands."""
    chat_id = view.chat_id
    history = view.history
    if view.closed or history.is_temporary(chat_id):
        raise ValueError('请在电脑版打开一条普通对话')
    chat = history.db.execute('SELECT title,active_leaf FROM chats WHERE id=?', (chat_id,)).fetchone()
    if not chat:
        raise ValueError('当前对话不存在')
    if request.get('op') == 'read':
        rows, leaf = [], chat['active_leaf']
        while leaf and len(rows) < 12:
            row = history.db.execute('''SELECT parent_id,role,substr(text,1,1500) AS text,
                length(text)>1500 AS truncated,image IS NOT NULL AS has_media,state,created
                FROM messages WHERE id=? AND chat_id=?''', (leaf, chat_id)).fetchone()
            if not row:
                break
            item = dict(row)
            leaf = item.pop('parent_id')
            rows.append(item)
        return {'chat_id': chat_id, 'leaf_id': chat['active_leaf'] or 0, 'title': chat['title'],
                'goal': (history.goal(chat_id) or '')[:1500],
                'steps': [{'title': step['title'][:160], 'detail': step['detail'][:500], 'done': step['done'],
                           'active': step['active']} for step in history.steps(chat_id)[:20]],
                'messages': rows[::-1]}
    if request.get('op') != 'append':
        raise ValueError('不支持的操作')
    if view.busy or view.editing:
        raise ValueError('请等电脑版结束生成或编辑后再回写')
    if (type(request.get('chat_id')) is not int or type(request.get('leaf_id')) is not int
            or request['chat_id'] != chat_id or request['leaf_id'] != (chat['active_leaf'] or 0)):
        raise ValueError('对话或分支已变化，请重新读取后再回写')
    text = request.get('text')
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_NOTE:
        raise ValueError('回写内容须为 1–6000 字符')
    with history.db:
        # Recheck the branch while holding the write lock shared with LAN sync.
        history.db.execute('BEGIN IMMEDIATE')
        leaf = history.db.execute('SELECT active_leaf FROM chats WHERE id=?', (chat_id,)).fetchone()
        if not leaf or (leaf[0] or 0) != request['leaf_id']:
            raise ValueError('对话或分支已变化，请重新读取后再回写')
        message_id = history.append(chat_id, 'assistant', '【OpenCode 工程结果】\n\n' + text.strip(),
                                    parent=leaf[0], model='OpenCode', provider='local-mcp')
    view.follow = True
    view.render()
    return {'chat_id': chat_id, 'message_id': message_id, 'saved': True}


class Bridge:
    def __init__(self, root, dispatch):
        token = secrets.token_hex(32)
        self.path = root / ENDPOINT

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                try:
                    request = _frame(self.request, limit=32768)
                    supplied = request.pop('token', '')
                    if not isinstance(supplied, str) or not supplied.isascii() or not compare_digest(supplied, token):
                        return
                    _frame(self.request, dispatch(request), limit=262144)
                except (OSError, ValueError, RecursionError):
                    return

        self.server = socketserver.TCPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .1}, daemon=True)
        try:
            _save(self.path, json.dumps({'port': self.server.server_address[1], 'token': token}).encode())
            self.thread.start()
        except (OSError, RuntimeError):
            self.server.server_close()
            raise

    def close(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass
        # Stop accepting in the background: a pending request may be waiting for Kivy.
        def stop():
            self.server.shutdown()
            self.server.server_close()
        threading.Thread(target=stop, daemon=True).start()


def request(root, data):
    try:
        endpoint = json.loads((root / ENDPOINT).read_bytes())
        with socket.create_connection(('127.0.0.1', endpoint['port']), timeout=2) as conn:
            _frame(conn, {**data, 'token': endpoint['token']}, limit=32768)
            return _frame(conn, limit=262144)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError('请在电脑版 TalkApp 开启「OpenCode 本机桥接」') from exc
