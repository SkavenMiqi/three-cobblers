"""Append-only, replay-safe exchange of settled chat messages between two stores."""
import json
import sqlite3
import uuid
from contextlib import closing, contextmanager

from .client import image_list

BATCH = 32
FRAME = 16 * 1024 * 1024
STATES = {'complete', 'failed', 'interrupted', 'cancelled'}


def _uuid():
    return uuid.uuid4().hex


def valid_id(value):
    return isinstance(value, str) and len(value) == 32 and all(c in '0123456789abcdef' for c in value)


def valid_seq(value):
    return type(value) is int and 0 <= value < 2**63


@contextmanager
def database(path):
    with closing(sqlite3.connect(path, timeout=2)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        yield db


def identity(db):
    return db.execute('SELECT uuid FROM lan_replica WHERE id=1').fetchone()[0]


def cursors(db, peer):
    row = db.execute('SELECT received FROM lan_cursors WHERE peer=?', (peer,)).fetchone()
    return row[0] if row else 0


def _index(db, chat_id=None):
    # Parents are created before children; only complete/settled nodes get a sequence.
    rows = db.execute('''SELECT m.id,m.chat_id,m.parent_id FROM messages m JOIN chats c ON c.id=m.chat_id
        LEFT JOIN lan_messages i ON i.local_id=m.id
        WHERE c.temporary=0 AND m.state!='generating' AND i.seq IS NULL AND (? IS NULL OR m.chat_id=?)
        ORDER BY m.id LIMIT ?''', (chat_id, chat_id, BATCH)).fetchall()
    added = 0
    for row in rows:
        if row['parent_id'] is not None and not db.execute('SELECT 1 FROM lan_messages WHERE local_id=?', (row['parent_id'],)).fetchone():
            continue
        db.execute('INSERT OR IGNORE INTO lan_chats VALUES (?,?)', (_uuid(), row['chat_id']))
        db.execute('INSERT INTO lan_messages(uuid,local_id) VALUES (?,?)', (_uuid(), row['id']))
        added += 1
    return added


def outgoing(db, after, *, opencode=False):
    if not valid_seq(after):
        raise ValueError('无效的同步游标')
    _index(db)
    return _outgoing(db, after, opencode=opencode)


def _outgoing(db, after, chat=None, *, opencode=False):
    rows = db.execute('''SELECT i.seq,i.uuid,k.uuid AS chat,p.uuid AS parent,c.title,
        m.role,m.text,m.image,m.state,m.model,m.provider,m.error,m.created,q.state AS opencode_state,
        e.message_id AS execution_id
        FROM lan_messages i JOIN messages m ON m.id=i.local_id JOIN chats c ON c.id=m.chat_id
        JOIN lan_chats k ON k.local_id=c.id LEFT JOIN lan_messages p ON p.local_id=m.parent_id
        LEFT JOIN lan_opencode q ON q.message_id=m.id
            AND EXISTS (SELECT 1 FROM lan_opencode_auto_requests a WHERE a.message_id=m.id)
        LEFT JOIN opencode_execution_tasks e ON e.message_id=q.message_id
        WHERE i.seq>? AND c.temporary=0 AND (m.parent_id IS NULL OR p.seq IS NOT NULL)
        AND (? IS NULL OR k.uuid=?) ORDER BY i.seq LIMIT ?''', (after, chat, chat, BATCH))
    result, size = [], 0
    for row in rows:
        event = dict(row)
        execution = event.pop('execution_id') is not None
        if event.pop('opencode_state') == 'outgoing' and opencode:
            event['opencode_request'] = True
            if execution:
                event['opencode_execution'] = True
        photos = image_list(event['image'])
        event['image'] = json.dumps(photos) if photos else None
        length = len(json.dumps(event, ensure_ascii=False).encode('utf-8'))
        if length > FRAME - 4096:
            event['image'] = None
            event['text'] = event['text'][:240000] + '\n（跨设备同步时已省略超大内容）'
            length = len(json.dumps(event, ensure_ascii=False).encode('utf-8'))
        if size + length > FRAME - 4096:
            break
        result.append(event)
        size += length
    return result


def _insert(db, event, *, restoring=False, opencode=False, execution=False):
    mid, cid, parent = (event[key] for key in ('uuid', 'chat', 'parent'))
    if not valid_id(mid) or not valid_id(cid) or (parent is not None and not valid_id(parent)):
        raise ValueError('无效的同步消息 ID')
    if not restoring and db.execute('SELECT 1 FROM lan_restore WHERE chat=?', (cid,)).fetchone():
        return  # Recovery replays this conversation in its own parent-first stream.
    indexed = db.execute('SELECT local_id FROM lan_messages WHERE uuid=?', (mid,)).fetchone()
    if indexed and (indexed[0] is not None or not restoring):
        return
    chat = db.execute('SELECT local_id FROM lan_chats WHERE uuid=?', (cid,)).fetchone()
    if chat and chat[0] is None:
        return  # Locally deleted chats stay deleted on this device.
    image = event['image']
    if image is not None and (not isinstance(image, str) or not image_list(image)):
        raise ValueError('无效的同步图片')
    values = [event[key] for key in ('role', 'text', 'state', 'model', 'provider', 'error', 'created', 'title')]
    if (not all(isinstance(value, str) for value in values) or values[0] not in ('user', 'assistant')
            or values[2] not in STATES):
        raise ValueError('无效的同步消息')
    parent_id = None
    if parent:
        ancestor = db.execute('''SELECT m.id,m.chat_id FROM lan_messages i
            LEFT JOIN messages m ON m.id=i.local_id WHERE i.uuid=?''', (parent,)).fetchone()
        if ancestor and ancestor[0] is None:
            db.execute('INSERT INTO lan_messages(uuid) VALUES (?)', (mid,))
            return  # Don't resurrect a branch deleted on this device.
        if not ancestor or not chat or ancestor[1] != chat[0]:
            raise ValueError('等待同步父消息')
        parent_id = ancestor[0]
    if chat:
        chat_id = chat[0]
    else:
        project = db.execute('INSERT INTO projects(name) VALUES (?)', ('局域网对话',)).lastrowid
        chat_id = db.execute('INSERT INTO chats(title,project_id) VALUES (?,?)', (values[-1][:120], project)).lastrowid
        db.execute('INSERT INTO lan_chats VALUES (?,?)', (cid, chat_id))
    role, text, state, model, provider, error, created, _ = values
    message_id = db.execute('''INSERT INTO messages(chat_id,parent_id,role,text,image,state,model,provider,error,created)
        VALUES (?,?,?,?,?,?,?,?,?,?)''', (chat_id, parent_id, role, text, image, state, model, provider, error, created)).lastrowid
    if opencode and not restoring and event.get('opencode_request') is True and role == 'user' and state == 'complete' and image is None:
        from .lan_opencode import valid_prompt
        if valid_prompt(text):
            db.execute("INSERT INTO lan_opencode VALUES (?,'pending')", (message_id,))
            db.execute('INSERT INTO lan_opencode_auto_requests VALUES (?)', (message_id,))
            if execution and event.get('opencode_execution') is True:
                db.execute('INSERT INTO opencode_execution_tasks VALUES (?)', (message_id,))
    if indexed:
        db.execute('UPDATE lan_messages SET local_id=? WHERE uuid=?', (message_id, mid))
    else:
        db.execute('INSERT INTO lan_messages(uuid,local_id) VALUES (?,?)', (mid, message_id))
    active = db.execute('SELECT active_leaf FROM chats WHERE id=?', (chat_id,)).fetchone()[0]
    if parent_id is not None:
        db.execute('UPDATE messages SET selected_child=? WHERE id=? AND (selected_child IS NULL OR ?)',
                   (message_id, parent_id, active == parent_id))
    db.execute('''UPDATE chats SET active_leaf=CASE WHEN active_leaf IS ? THEN ? ELSE active_leaf END,
        updated=CURRENT_TIMESTAMP WHERE id=?''', (parent_id, message_id, chat_id))


def receive(db, peer, events, *, opencode=False, execution=False):
    if not valid_id(peer) or not isinstance(events, list) or len(events) > BATCH:
        raise ValueError('无效的同步数据')
    received = cursors(db, peer)
    for event in events:
        if not isinstance(event, dict) or not valid_seq(event.get('seq')):
            raise ValueError('无效的同步消息')
        if event['seq'] > received:
            _insert(db, event, opencode=opencode, execution=execution)
            received = event['seq']
    if events:
        db.execute('''INSERT INTO lan_cursors(peer,received) VALUES (?,?)
            ON CONFLICT(peer) DO UPDATE SET received=excluded.received WHERE received<excluded.received''', (peer, received))
    return received


def queue_restore(db):
    """Request only conversations with a locally recorded deletion."""
    db.execute('''INSERT OR IGNORE INTO lan_restore(chat) SELECT uuid FROM lan_chats WHERE local_id IS NULL''')
    return db.execute('SELECT count(*) FROM lan_restore').fetchone()[0]


def restore_request(db):
    row = db.execute('SELECT chat,after_seq FROM lan_restore ORDER BY rowid LIMIT 1').fetchone()
    return list(row) if row else None


def restore_offer(db, request):
    if request is None:
        return None
    if (not isinstance(request, list) or len(request) != 2 or not valid_id(request[0]) or not valid_seq(request[1])):
        raise ValueError('无效的恢复请求')
    chat, after = request
    row = db.execute('''SELECT c.id,c.active_leaf FROM lan_chats k JOIN chats c ON c.id=k.local_id
        WHERE k.uuid=? AND c.temporary=0''', (chat,)).fetchone()
    if not row:
        return {'chat': chat, 'after': after, 'found': False}
    while _index(db, row['id']):
        # Index newly added branches too; batches on the wire remain bounded.
        pass
    events = _outgoing(db, after, chat)
    active = db.execute('SELECT uuid FROM lan_messages WHERE local_id=?', (row['active_leaf'],)).fetchone()
    return {'chat': chat, 'after': after, 'found': True, 'events': events, 'active': active[0] if active else None}


def receive_restore(db, request, offer):
    if request is None or offer is None:
        return
    chat, after = request
    queued = db.execute('SELECT after_seq FROM lan_restore WHERE chat=?', (chat,)).fetchone()
    if not queued or queued[0] != after:
        return
    if not isinstance(offer, dict) or (offer.get('chat'), offer.get('after')) != (chat, after):
        return  # A retry may offer the previous batch again.
    local = db.execute('SELECT local_id FROM lan_chats WHERE uuid=?', (chat,)).fetchone()
    if not local or (bool(after) != (local[0] is not None)):
        db.execute('DELETE FROM lan_restore WHERE chat=?', (chat,))
        return
    if offer.get('found') is not True:
        db.execute('DELETE FROM lan_restore WHERE chat=?', (chat,))
        return
    events = offer.get('events')
    if not isinstance(events, list) or len(events) > BATCH:
        raise ValueError('无效的恢复数据')
    if events and local[0] is None:
        title = events[0].get('title') if isinstance(events[0], dict) else None
        if not isinstance(title, str):
            raise ValueError('无效的对话标题')
        project = db.execute('INSERT INTO projects(name) VALUES (?)', ('局域网对话',)).lastrowid
        local_id = db.execute('INSERT INTO chats(title,project_id) VALUES (?,?)', (title[:120], project)).lastrowid
        db.execute('UPDATE lan_chats SET local_id=? WHERE uuid=?', (local_id, chat))
        db.execute('DELETE FROM lan_progress WHERE chat=?', (chat,))
    if events:
        for event in events:
            if not isinstance(event, dict) or event.get('chat') != chat or not valid_seq(event.get('seq')) or event['seq'] <= after:
                raise ValueError('无效的恢复消息')
            _insert(db, event, restoring=True)
            after = event['seq']
        db.execute('UPDATE lan_restore SET after_seq=? WHERE chat=?', (after, chat))
    else:
        if local[0] is not None and valid_id(offer.get('active')):
            active = db.execute('''SELECT m.id FROM lan_messages i JOIN messages m ON m.id=i.local_id
                WHERE i.uuid=? AND m.chat_id=?''', (offer['active'], local[0])).fetchone()
            # Don't move someone who already started chatting in the restored copy.
            if active and not db.execute('''SELECT 1 FROM messages m LEFT JOIN lan_messages i ON i.local_id=m.id
                WHERE m.chat_id=? AND i.local_id IS NULL''', (local[0],)).fetchone():
                db.execute('''WITH RECURSIVE branch(id,parent_id) AS (
                    SELECT id,parent_id FROM messages WHERE id=? UNION
                    SELECT m.id,m.parent_id FROM messages m JOIN branch b ON m.id=b.parent_id)
                    UPDATE messages SET selected_child=(SELECT id FROM branch WHERE parent_id=messages.id)
                    WHERE id IN (SELECT parent_id FROM branch)''', (active[0],))
                db.execute('UPDATE chats SET active_leaf=? WHERE id=?', (active[0], local[0]))
        db.execute('DELETE FROM lan_restore WHERE chat=?', (chat,))
