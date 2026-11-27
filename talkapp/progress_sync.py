"""Field-wise progress merge, scoped to an already shared conversation."""
import json
import unicodedata

from . import chat_sync


def step_key(title):
    return ' '.join(unicodedata.normalize('NFKC', title).split()).casefold()


def _local(db, cid):
    goal = db.execute('SELECT goal FROM chats WHERE id=?', (cid,)).fetchone()[0]
    values = {'goal': goal, 'active': ''}
    rows = {}
    for row in db.execute('SELECT * FROM project_steps WHERE chat_id=? ORDER BY position,id', (cid,)):
        key = step_key(row['title'])
        if not key or key in rows:
            continue
        rows[key] = row
        values['step:' + key] = [row['title'], row['detail'] or '']
        values['done:' + key] = bool(row['done'])
        if row['active'] and not row['done']:
            values['active'] = key
    return values, rows


def _load(db, chat):
    row = db.execute('SELECT registers,seen,hidden FROM lan_progress WHERE chat=?', (chat,)).fetchone()
    return tuple(map(json.loads, row)) if row else ({}, {}, [])


def _save(db, chat, regs, seen, hidden):
    data = tuple(json.dumps(v, ensure_ascii=False, sort_keys=True) for v in (regs, seen, sorted(hidden)))
    db.execute('''INSERT INTO lan_progress VALUES (?,?,?,?) ON CONFLICT(chat) DO UPDATE SET
        registers=excluded.registers,seen=excluded.seen,hidden=excluded.hidden
        WHERE registers!=excluded.registers OR seen!=excluded.seen OR hidden!=excluded.hidden''', (chat, *data))


def _capture(db, chat, cid):
    regs, seen, hidden = _load(db, chat)
    values, rows = _local(db, cid)
    hidden = set(hidden)
    hidden.update(key[5:] for key in seen if key.startswith('step:') and key not in values)
    hidden.difference_update(rows)
    clock = max((entry[0] for entry in regs.values()), default=0)
    own = chat_sync.identity(db)
    for field, value in values.items():
        if field not in regs:
            regs[field] = [0, own, value]
        elif field in seen and seen[field] != value:
            if field == 'active' and not value and seen[field] in hidden:
                continue  # Deleting the local active step must not clear the peer's selection.
            regs[field] = [clock + 1, own, value]
        elif field not in seen and field.startswith(('step:', 'done:')):
            regs[field] = [clock + 1, own, value]
    _save(db, chat, regs, values, hidden)
    return regs, rows, hidden


def _rank(field, entry):
    rev, source, value = entry
    # Old devices have no edit clocks: completed wins, and useful text beats blanks.
    initial = bool(value[1]) if field.startswith('step:') else bool(value)
    return rev, initial if rev == 0 else False, source


def _valid(field, entry):
    if not isinstance(entry, list) or len(entry) != 3 or not chat_sync.valid_seq(entry[0]) or not chat_sync.valid_id(entry[1]):
        return False
    value = entry[2]
    if field in ('goal', 'active'):
        return isinstance(value, str) and len(value) <= 4000
    if field.startswith('done:'):
        return type(value) is bool
    return (field.startswith('step:') and isinstance(value, list) and len(value) == 2
            and all(isinstance(part, str) and len(part) <= 4000 for part in value)
            and step_key(value[0]) == field[5:] and bool(field[5:]))


def outgoing(db, after):
    if after != '' and not chat_sync.valid_id(after):
        raise ValueError('无效的进度游标')
    rows = db.execute('''SELECT k.uuid,c.id FROM lan_chats k JOIN chats c ON c.id=k.local_id
        WHERE c.temporary=0 AND k.uuid>? AND (c.goal!='' OR EXISTS(SELECT 1 FROM project_steps s WHERE s.chat_id=c.id)
        OR EXISTS(SELECT 1 FROM lan_progress p WHERE p.chat=k.uuid)) ORDER BY k.uuid LIMIT 12''', (after,)).fetchall()
    batch = {}
    size = 0
    for chat, cid in rows:
        regs, _, hidden = _capture(db, chat, cid)
        payload = {f: e for f, e in regs.items() if _valid(f, e)
                   and not (f.startswith(('step:', 'done:')) and f[5:] in hidden)}
        length = len(json.dumps(payload, ensure_ascii=False).encode())
        if length > 2 * 1024 * 1024:
            batch[chat] = {}
            continue
        if size + length > 2 * 1024 * 1024:
            break
        batch[chat] = payload
        size += length
    return batch


def scan(db, peer):
    row = db.execute('SELECT sent,received FROM lan_progress_scan WHERE peer=?', (peer,)).fetchone()
    return tuple(row) if row else ('', '')


def checkpoint(db, peer, sent, received):
    cursors = (max(sent, default=''), max(received, default=''))
    if scan(db, peer) != cursors:
        db.execute('INSERT OR REPLACE INTO lan_progress_scan VALUES (?,?,?)', (peer, *cursors))


def receive(db, batch):
    if not isinstance(batch, dict) or len(batch) > 12:
        raise ValueError('无效的进度同步数据')
    for chat, incoming in batch.items():
        if not chat_sync.valid_id(chat) or not isinstance(incoming, dict) or not all(_valid(f, e) for f, e in incoming.items()):
            raise ValueError('无效的进度同步数据')
        target = db.execute('''SELECT c.id,c.project_id FROM chats c JOIN lan_chats k ON k.local_id=c.id
            WHERE k.uuid=? AND c.temporary=0''', (chat,)).fetchone()
        if not target or not incoming:
            continue
        cid, project = target
        regs, rows, hidden = _capture(db, chat, cid)
        hidden.update(row[0] for row in db.execute('SELECT key FROM deleted_steps WHERE chat_id=?', (cid,)) if row[0] not in rows)
        for field, entry in incoming.items():
            if field not in regs or _rank(field, entry) > _rank(field, regs[field]):
                regs[field] = entry
        active = regs['active'][2]
        db.execute('UPDATE chats SET goal=? WHERE id=? AND goal IS NOT ?', (regs['goal'][2], cid, regs['goal'][2]))
        position = max((row['position'] for row in rows.values()), default=-1) + 1
        for field, entry in regs.items():
            key = field[5:]
            if not field.startswith('step:') or key in hidden:
                continue
            title, detail = entry[2]
            done = int(regs.get('done:' + key, [0, '', False])[2])
            is_active = int(key == active and not done)
            row = rows.get(key)
            if row is None:
                db.execute('INSERT INTO project_steps(project_id,chat_id,title,detail,position,done,active) VALUES (?,?,?,?,?,?,?)',
                           (project, cid, title, detail, position, done, is_active))
                position += 1
            elif (title, detail, done, is_active) != (row['title'], row['detail'], row['done'], row['active']):
                db.execute('UPDATE project_steps SET title=?,detail=?,done=?,active=? WHERE id=?',
                           (title, detail, done, is_active, row['id']))
        _save(db, chat, regs, _local(db, cid)[0], hidden)
