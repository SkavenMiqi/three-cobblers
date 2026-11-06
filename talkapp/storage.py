import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime


def data_dir():
    if "ANDROID_ARGUMENT" in os.environ:
        from android.storage import app_storage_path
        root = Path(app_storage_path())
    else:
        root = Path(os.environ.get("TALKAPP_DATA_DIR", Path.home() / ".talkapp"))
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass
class Config:
    api_key: str = ""
    api_base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    system_prompt: str = "你是一个友好、可靠的日常聊天助手。默认用中文回答，按用户需要调整详细程度。"
    context_tokens: int = 16000
    model_context_limit: int = 272000
    max_output_tokens: int = 2048
    memory_enabled: bool = True
    auxiliary_model: str = ''
    input_price: float = 0.0
    output_price: float = 0.0

    @property
    def is_configured(self):
        return bool(self.api_key and self.api_base_url and self.model)

    @classmethod
    def load(cls):
        try:
            raw = json.loads((data_dir() / "llm.json").read_text(encoding="utf-8"))
            return cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})
        except (OSError, ValueError, TypeError, AttributeError):
            return cls()

    def validate(self):
        url = urlparse(self.api_base_url)
        local = url.hostname in ('localhost', '127.0.0.1', '::1')
        if (url.scheme != "https" and not (url.scheme == 'http' and local)) or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("API 地址必须使用 HTTPS（本机接口允许 HTTP），且不含账号和查询参数")
        if not self.api_key.strip() or not self.model.strip():
            raise ValueError("请填写 API Key 和模型名称")
        if not isinstance(self.context_tokens, int) or not 4000 <= self.context_tokens <= 1000000:
            raise ValueError('上下文预算需为 4000–1000000 tokens')
        if not isinstance(self.model_context_limit, int) or not 4000 <= self.model_context_limit <= 2000000:
            raise ValueError('模型窗口上限无效')
        if not isinstance(self.max_output_tokens, int) or not 256 <= self.max_output_tokens < min(self.context_tokens, self.model_context_limit):
            raise ValueError('输出预留至少256且必须小于上下文预算和模型窗口')

    def save(self):
        self.validate()
        path = data_dir() / "llm.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        tmp.replace(path)
        profiles = self.profiles()
        identity = (self.api_base_url.rstrip('/'), self.model)
        profiles = [item for item in profiles if (item['api_base_url'].rstrip('/'), item['model']) != identity]
        profiles.insert(0, asdict(self))
        target = data_dir() / 'profiles.json'
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding='utf-8')
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        temporary.replace(target)

    @classmethod
    def profiles(cls):
        try:
            values = json.loads((data_dir() / 'profiles.json').read_text(encoding='utf-8'))
            return [value for value in values if isinstance(value, dict) and
                    all(key in value for key in ('api_base_url', 'model', 'api_key'))]
        except (OSError, ValueError, TypeError):
            return []


class History:
    def __init__(self, path=None):
        self.db = sqlite3.connect(path or data_dir() / "history.db")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY, title TEXT NOT NULL,
                updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                role TEXT NOT NULL, text TEXT NOT NULL, image TEXT,
                created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        """)
        self._migrate()

    def _migrate(self):
        additions = {
            'chats': {'active_leaf': 'INTEGER', 'pinned': 'INTEGER NOT NULL DEFAULT 0',
                      'manual_title': 'INTEGER NOT NULL DEFAULT 0', 'temporary': 'INTEGER NOT NULL DEFAULT 0',
                       'goal': "TEXT NOT NULL DEFAULT ''", 'project_id': 'INTEGER'},
            'messages': {'parent_id': 'INTEGER', 'selected_child': 'INTEGER',
                         'state': "TEXT NOT NULL DEFAULT 'complete'", 'model': "TEXT NOT NULL DEFAULT ''",
                         'provider': "TEXT NOT NULL DEFAULT ''", 'error': "TEXT NOT NULL DEFAULT ''"}}
        # Transactional migration: old linear history becomes the initial branch.
        with self.db:
            old = 'parent_id' not in {row[1] for row in self.db.execute('PRAGMA table_info(messages)')}
            for table, columns in additions.items():
                existing = {row[1] for row in self.db.execute(f'PRAGMA table_info({table})')}
                for name, declaration in columns.items():
                    if name not in existing:
                        self.db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {declaration}')
            if old:
                for chat in self.db.execute('SELECT id FROM chats').fetchall():
                    parent = None
                    for node in self.db.execute('SELECT id FROM messages WHERE chat_id=? ORDER BY id', (chat[0],)).fetchall():
                        self.db.execute('UPDATE messages SET parent_id=? WHERE id=?', (parent, node[0]))
                        if parent:
                            self.db.execute('UPDATE messages SET selected_child=? WHERE id=?', (node[0], parent))
                        parent = node[0]
                    self.db.execute('UPDATE chats SET active_leaf=? WHERE id=?', (parent, chat[0]))
            self.db.execute('''CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                through_id INTEGER NOT NULL, text TEXT NOT NULL, model TEXT NOT NULL,
                created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
            self.db.execute('CREATE INDEX IF NOT EXISTS message_parent ON messages(chat_id,parent_id)')
            self.db.executescript('''CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY, text TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                source_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
                created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(text));
                CREATE TABLE IF NOT EXISTS recall_sources (
                reply_id INTEGER PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
                sources TEXT NOT NULL, memories TEXT NOT NULL);''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS internal_digests (
                chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                chunk_key TEXT NOT NULL, text TEXT NOT NULL,
                PRIMARY KEY(chat_id,chunk_key))''')
            self.db.executescript('''CREATE TABLE IF NOT EXISTS usage_log (
                id INTEGER PRIMARY KEY, task TEXT, model TEXT, provider TEXT,
                input_tokens INTEGER, output_tokens INTEGER, reported INTEGER, cost REAL,
                created TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY, message_id INTEGER REFERENCES messages(id) ON DELETE CASCADE,
                name TEXT, content TEXT);
                CREATE TABLE IF NOT EXISTS web_sources (
                reply_id INTEGER PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE, content TEXT);''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS progress_steps (
                id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                source_id INTEGER REFERENCES messages(id) ON DELETE CASCADE,
                title TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', done INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 0, position INTEGER NOT NULL,
                created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY, reply_id INTEGER REFERENCES messages(id) ON DELETE CASCADE,
                name TEXT NOT NULL, result TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP)''')
            self.db.executescript('''CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, goal TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS project_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                title TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', done INTEGER DEFAULT 0,
                active INTEGER DEFAULT 0, position INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS library (
                id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL, content TEXT NOT NULL, version INTEGER DEFAULT 1,
                updated TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(project_id,name));
                CREATE TABLE IF NOT EXISTS context_reports (
                reply_id INTEGER PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE, report TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS model_capabilities (
                provider TEXT NOT NULL, model TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(provider,model));''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS collaborations (
                reply_id INTEGER PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE, content TEXT NOT NULL)''')
            self.db.execute('CREATE TABLE IF NOT EXISTS drafts (chat_id INTEGER PRIMARY KEY REFERENCES chats(id) ON DELETE CASCADE,text TEXT NOT NULL)')
            self.db.execute('''CREATE TABLE IF NOT EXISTS audio_parses (
                message_id INTEGER PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
                text TEXT NOT NULL, parser TEXT NOT NULL)''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS answer_reviews (
                id INTEGER PRIMARY KEY, message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                model TEXT NOT NULL, provider TEXT NOT NULL, text TEXT NOT NULL,
                created TEXT DEFAULT CURRENT_TIMESTAMP)''')
            self.db.executescript('''CREATE TABLE IF NOT EXISTS memory_processed (
                message_id INTEGER PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE, fingerprint TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS long_memory (
                id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                category TEXT NOT NULL, semantic_key TEXT NOT NULL, text TEXT NOT NULL,
                operation TEXT NOT NULL, scope INTEGER NOT NULL DEFAULT 0,
                UNIQUE(source_id,category,semantic_key));''')

            columns = {row[1] for row in self.db.execute('PRAGMA table_info(action_log)')}
            for name, declaration in {'before_state': 'TEXT', 'after_state': 'TEXT', 'undone': 'INTEGER DEFAULT 0'}.items():
                if name not in columns:
                    self.db.execute(f'ALTER TABLE action_log ADD COLUMN {name} {declaration}')
            for chat in self.db.execute('SELECT * FROM chats WHERE project_id IS NULL').fetchall():
                project = self.db.execute('INSERT INTO projects(name,goal) VALUES (?,?)', (chat['title'], chat['goal'])).lastrowid
                self.db.execute('UPDATE chats SET project_id=? WHERE id=?', (project, chat['id']))
                for step in self.db.execute('SELECT * FROM progress_steps WHERE chat_id=? ORDER BY position', (chat['id'],)).fetchall():
                    self.db.execute('INSERT INTO project_steps(project_id,title,detail,done,active,position) VALUES (?,?,?,?,?,?)',
                                    (project, step['title'], step['detail'], step['done'], step['active'], step['position']))
            columns = {row[1] for row in self.db.execute('PRAGMA table_info(project_steps)')}
            if 'chat_id' not in columns:
                self.db.execute('ALTER TABLE project_steps ADD COLUMN chat_id INTEGER REFERENCES chats(id) ON DELETE CASCADE')
                for project in self.db.execute('SELECT id FROM projects').fetchall():
                    chats = self.db.execute('SELECT id,goal FROM chats WHERE project_id=? ORDER BY id', (project[0],)).fetchall()
                    if not chats:
                        continue
                    owner = chats[0]['id']
                    project_goal = self.db.execute('SELECT goal FROM projects WHERE id=?', (project[0],)).fetchone()[0]
                    if project_goal and not chats[0]['goal']:
                        self.db.execute('UPDATE chats SET goal=? WHERE id=?', (project_goal, owner))
                    for step in self.db.execute('SELECT id,title FROM project_steps WHERE project_id=?', (project[0],)).fetchall():
                        original = self.db.execute('''SELECT s.chat_id FROM progress_steps s JOIN chats c ON c.id=s.chat_id
                            WHERE c.project_id=? AND s.title=? ORDER BY s.id LIMIT 1''', (project[0], step['title'])).fetchone()
                        self.db.execute('UPDATE project_steps SET chat_id=? WHERE id=?', (original[0] if original else owner, step['id']))

    def save_draft(self, chat_id, text):
        if not self.db.execute('SELECT 1 FROM chats WHERE id=?', (chat_id,)).fetchone():
            return
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO drafts VALUES (?,?)', (chat_id, text))

    def draft(self, chat_id):
        row = self.db.execute('SELECT text FROM drafts WHERE chat_id=?', (chat_id,)).fetchone()
        return row[0] if row else ''

    def memory_jobs(self):
        import hashlib
        jobs = []
        for chat in self.db.execute('SELECT id,project_id FROM chats WHERE temporary=0 ORDER BY id'):
            path = self.path(chat['id'])
            for index, node in enumerate(path):
                if node['role'] != 'user' or index + 1 >= len(path) or path[index + 1]['state'] != 'complete':
                    continue
                parsed = self.db.execute('SELECT text FROM audio_parses WHERE message_id=?', (node['id'],)).fetchone()
                text = parsed[0] if parsed else node['text']
                if text == '（语音消息）':
                    continue
                fingerprint = hashlib.sha256(text.encode()).hexdigest()
                done = self.db.execute('SELECT fingerprint FROM memory_processed WHERE message_id=?', (node['id'],)).fetchone()
                if not done or done[0] != fingerprint:
                    jobs.append(dict(source_id=node['id'], chat_id=chat['id'], project_id=chat['project_id'], text=text,
                                     fingerprint=fingerprint))
        return jobs

    def apply_memory(self, job, facts):
        # Recheck selected branch, deletion, completion and changed transcript.
        current = next((item for item in self.memory_jobs() if item['source_id'] == job['source_id']), None)
        if not current or current['fingerprint'] != job['fingerprint']:
            return False
        with self.db:
            self.db.execute('DELETE FROM long_memory WHERE source_id=?', (job['source_id'],))
            for fact in facts:
                self.db.execute('''INSERT OR REPLACE INTO long_memory(source_id,category,semantic_key,text,operation,scope)
                    VALUES (?,?,?,?,?,?)''', (job['source_id'], fact['category'], fact['key'], fact['text'], fact['operation'],
                                            job['project_id'] if fact['category'] == 'project' else 0))
            self.db.execute('INSERT OR REPLACE INTO memory_processed VALUES (?,?)', (job['source_id'], job['fingerprint']))
        return True

    def long_memories(self, chat_id, query='', budget=3500):
        from .memory import terms
        valid = {node['id'] for chat in self.db.execute('SELECT id FROM chats WHERE temporary=0') for node in self.path(chat[0])}
        project = self.project(chat_id)
        project_id = project['id'] if project else -1
        latest = {}
        for row in self.db.execute('SELECT * FROM long_memory ORDER BY source_id,id'):
            if row['source_id'] not in valid or (row['scope'] and row['scope'] != project_id):
                continue
            latest[(row['category'], row['semantic_key'], row['scope'])] = dict(row)
        values = [dict(item, key=item['semantic_key']) for item in latest.values() if item['operation'] == 'set']
        tokens = set(terms(query))
        values.sort(key=lambda item: (item['category'] == 'user', len(tokens & set(terms(item['text']))), item['source_id']), reverse=True)
        selected, size, seen = [], 0, set()
        for item in values:
            normalized = ''.join(item['text'].lower().split())
            if normalized in seen or size + len(item['text']) + len(item['key']) > budget:
                continue
            selected.append(item)
            size += len(item['text']) + len(item['key'])
            seen.add(normalized)
        return selected

    def project(self, chat_id):
        row = self.db.execute('SELECT p.* FROM projects p JOIN chats c ON c.project_id=p.id WHERE c.id=?', (chat_id,)).fetchone()
        return dict(row) if row else None

    def projects(self):
        return [dict(row) for row in self.db.execute('SELECT * FROM projects ORDER BY id DESC')]

    def create_project(self, name):
        with self.db:
            return self.db.execute('INSERT INTO projects(name) VALUES (?)', (name.strip()[:100] or '新项目',)).lastrowid

    def move_chat(self, chat_id, project_id):
        if not self.db.execute('SELECT 1 FROM projects WHERE id=?', (project_id,)).fetchone():
            raise ValueError('项目不存在')
        with self.db:
            self.db.execute('UPDATE chats SET project_id=? WHERE id=?', (project_id, chat_id))

    def project_snapshot(self, chat_id):
        project = self.project(chat_id)
        chat = self.db.execute('SELECT title,manual_title FROM chats WHERE id=?', (chat_id,)).fetchone()
        return {'project_id': project['id'], 'goal': self.goal(chat_id), 'steps': self.steps(chat_id),
                'title': chat['title'], 'manual_title': chat['manual_title']}

    def undo_action(self, action_id):
        row = self.db.execute('SELECT a.*,m.chat_id FROM action_log a JOIN messages m ON m.id=a.reply_id WHERE a.id=?', (action_id,)).fetchone()
        if not row or row['undone'] or not row['before_state']:
            raise ValueError('该操作不能撤销')
        before, after = json.loads(row['before_state']), json.loads(row['after_state'])
        if self.project_snapshot(row['chat_id']) != after:
            raise ValueError('之后已有其他修改，为避免覆盖请让AI修改具体步骤')
        with self.db:
            self.db.execute('UPDATE chats SET goal=? WHERE id=?', (before['goal'], row['chat_id']))
            self.db.execute('DELETE FROM project_steps WHERE chat_id=?', (row['chat_id'],))
            for step in before['steps']:
                step['chat_id'] = row['chat_id']
                self.db.execute('INSERT INTO project_steps(id,project_id,title,detail,done,active,position,chat_id) VALUES (:id,:project_id,:title,:detail,:done,:active,:position,:chat_id)', step)
            self.db.execute('UPDATE chats SET title=?,manual_title=? WHERE id=?', (before['title'], before['manual_title'], row['chat_id']))
            self.db.execute('UPDATE action_log SET undone=1 WHERE id=?', (action_id,))

    def library(self, chat_id):
        project = self.project(chat_id)
        return [dict(row) for row in self.db.execute('SELECT * FROM library WHERE project_id=? ORDER BY updated DESC,id DESC', (project['id'],))] if project else []

    def save_library(self, chat_id, name, content):
        if self.is_temporary(chat_id):
            raise ValueError('临时对话不能写入项目资料库')
        project = self.project(chat_id)
        with self.db:
            self.db.execute('''INSERT INTO library(project_id,name,content) VALUES (?,?,?)
                ON CONFLICT(project_id,name) DO UPDATE SET content=excluded.content,version=version+1,updated=CURRENT_TIMESTAMP''',
                (project['id'], name[:200], content[:120000]))

    def goal(self, chat_id):
        row = self.db.execute('SELECT goal FROM chats WHERE id=?', (chat_id,)).fetchone()
        return row[0] if row else ''

    def set_goal(self, chat_id, goal):
        with self.db:
            self.db.execute('UPDATE chats SET goal=? WHERE id=?', (goal, chat_id))

    def steps(self, chat_id):
        return [dict(row) for row in self.db.execute('SELECT * FROM project_steps WHERE chat_id=? ORDER BY position,id', (chat_id,))]

    def merge_steps(self, chat_id, source_id, values):
        if not self.node(source_id):
            return
        with self.db:
            existing = {item['title']: item for item in self.steps(chat_id)}
            position = max((item['position'] for item in existing.values()), default=-1) + 1
            for item in values:
                if item['title'] in existing:
                    continue
                self.db.execute('INSERT INTO project_steps(project_id,chat_id,title,detail,position) VALUES (?,?,?,?,?)',
                                (self.project(chat_id)['id'], chat_id, item['title'], item['detail'], position))
                existing[item['title']] = item
                position += 1

    def step_state(self, step_id, done=None, active=None):
        row = self.db.execute('SELECT chat_id FROM project_steps WHERE id=?', (step_id,)).fetchone()
        if not row:
            return
        with self.db:
            if done is not None:
                self.db.execute('UPDATE project_steps SET done=?,active=0 WHERE id=?', (int(done), step_id))
            if active is not None:
                self.db.execute('UPDATE project_steps SET active=0 WHERE chat_id=?', (row[0],))
                self.db.execute('UPDATE project_steps SET active=? WHERE id=?', (int(active), step_id))

    def usage(self, record):
        with self.db:
            self.db.execute('''INSERT INTO usage_log(task,model,provider,input_tokens,output_tokens,reported,cost)
                VALUES (:task,:model,:provider,:input_tokens,:output_tokens,:reported,:cost)''', record)

    def attach(self, message_id, files):
        with self.db:
            for item in files:
                self.db.execute('INSERT INTO attachments(message_id,name,content) VALUES (?,?,?)',
                                (message_id, item['name'], item['content']))

    def files(self, message_id):
        return [dict(row) for row in self.db.execute('SELECT name,content FROM attachments WHERE message_id=?', (message_id,))]

    def matching_message(self, chat_id, query):
        return next((dict(row) for row in self.db.execute('SELECT * FROM messages WHERE chat_id=? ORDER BY id DESC', (chat_id,))
                     if query.lower() in row['text'].lower()), None)

    def digest_work(self):
        from .memory import digest_chunks
        ready, pending = [], []
        for chat in self.search():
            for key, content in digest_chunks(self.path(chat['id'])):
                row = self.db.execute('SELECT text FROM internal_digests WHERE chat_id=? AND chunk_key=?',
                                      (chat['id'], key)).fetchone()
                item = {'chat_id': chat['id'], 'key': key, 'text': row[0] if row else content}
                (ready if row else pending).append(item)
        return ready, pending

    def save_digest(self, chat_id, key, text):
        from .memory import digest_chunks
        # A response arriving after deletion/edit must not restore stale history.
        if key not in {value[0] for value in digest_chunks(self.path(chat_id))}:
            return
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO internal_digests VALUES (?,?,?)', (chat_id, key, text))

    def memories(self, status=None):
        sql = 'SELECT * FROM memories' + (' WHERE status=?' if status else '') + ' ORDER BY id DESC'
        return [dict(row) for row in self.db.execute(sql, (status,) if status else ())]

    def propose_memory(self, text, source_id):
        if not self.node(source_id):
            return
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO memories(text,source_id) VALUES (?,?)', (text.strip()[:240], source_id))

    def update_memory(self, memory_id, status, text=None):
        if status not in ('pending', 'accepted', 'rejected'):
            raise ValueError('Unknown memory status')
        with self.db:
            if text is not None:
                self.db.execute('UPDATE memories SET text=?,status=? WHERE id=?', (text.strip()[:240], status, memory_id))
            else:
                self.db.execute('UPDATE memories SET status=? WHERE id=?', (status, memory_id))

    def forget_memory(self, memory_id):
        # Keep a rejected tombstone so automatic extraction will not immediately re-add it.
        self.update_memory(memory_id, 'rejected')

    def save_recall(self, reply_id, sources, memories):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO recall_sources VALUES (?,?,?)',
                            (reply_id, json.dumps(sources, ensure_ascii=False), json.dumps(memories, ensure_ascii=False)))

    def recall(self, reply_id):
        row = self.db.execute('SELECT sources,memories FROM recall_sources WHERE reply_id=?', (reply_id,)).fetchone()
        return (json.loads(row[0]), json.loads(row[1])) if row else ([], [])

    def recover_interrupted(self):
        with self.db:
            self.db.execute("UPDATE messages SET state='interrupted', error='应用关闭或中断，可重新生成' WHERE state='generating'")
            self.db.execute('DELETE FROM chats WHERE temporary=1')

    def create(self, temporary=False, project_id=None):
        with self.db:
            if project_id is None:
                project_id = self.create_project('临时项目' if temporary else '新项目')
            return self.db.execute("INSERT INTO chats(title,temporary,project_id) VALUES (?,?,?)", ('临时对话' if temporary else '新对话', int(temporary), project_id)).lastrowid

    def is_temporary(self, chat_id):
        row = self.db.execute('SELECT temporary FROM chats WHERE id=?', (chat_id,)).fetchone()
        return bool(row and row[0])

    def chats(self):
        return [tuple(row) for row in self.db.execute("SELECT id,title FROM chats ORDER BY pinned DESC,updated DESC,id DESC")]

    def search(self, query=''):
        pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        return [dict(row) for row in self.db.execute('''SELECT c.* FROM chats c WHERE c.temporary=0 AND (
            c.title LIKE ? ESCAPE '\\' OR EXISTS (SELECT 1 FROM messages m WHERE m.chat_id=c.id
            AND m.text LIKE ? ESCAPE '\\')) ORDER BY c.pinned DESC,c.updated DESC,c.id DESC''', (pattern, pattern))]

    def node(self, message_id):
        row = self.db.execute('SELECT * FROM messages WHERE id=?', (message_id,)).fetchone()
        return dict(row) if row else None

    def path(self, chat_id, leaf=None):
        if leaf is None:
            row = self.db.execute('SELECT active_leaf FROM chats WHERE id=?', (chat_id,)).fetchone()
            leaf = row[0] if row else None
        result, seen = [], set()
        while leaf and leaf not in seen:
            seen.add(leaf)
            node = self.node(leaf)
            if not node or node['chat_id'] != chat_id:
                break
            result.append(node)
            leaf = node['parent_id']
        return list(reversed(result))

    def siblings(self, node):
        return [row[0] for row in self.db.execute('SELECT id FROM messages WHERE chat_id=? AND parent_id IS ? ORDER BY id',
                                                (node['chat_id'], node['parent_id']))]

    def select(self, message_id):
        node = self.node(message_id)
        if not node:
            return
        with self.db:
            for item in self.path(node['chat_id'], message_id):
                if item['parent_id']:
                    self.db.execute('UPDATE messages SET selected_child=? WHERE id=?', (item['id'], item['parent_id']))
            leaf = node
            seen = set()
            while leaf['selected_child'] and leaf['id'] not in seen:
                seen.add(leaf['id'])
                child = self.node(leaf['selected_child'])
                if not child or child['parent_id'] != leaf['id']:
                    break
                leaf = child
            self.db.execute('UPDATE chats SET active_leaf=? WHERE id=?', (leaf['id'], node['chat_id']))

    def messages(self, chat_id):
        return [(node['role'], node['text'], node['image']) for node in self.path(chat_id)]

    def append(self, chat_id, role, text, image=None, *, parent='active', state='complete', model='', provider=''):
        if parent == 'active':
            path = self.path(chat_id)
            parent = path[-1]['id'] if path else None
        if parent is not None:
            ancestor = self.node(parent)
            if not ancestor or ancestor['chat_id'] != chat_id:
                raise ValueError('消息不属于当前对话')
        with self.db:
            if role == "user" and not self.messages(chat_id):
                self.db.execute("UPDATE chats SET title=? WHERE id=?", ((text or "图片对话")[:24], chat_id))
            message_id = self.db.execute('''INSERT INTO messages(chat_id,role,text,image,parent_id,state,model,provider)
                VALUES (?,?,?,?,?,?,?,?)''', (chat_id, role, text, image, parent, state, model, provider)).lastrowid
            if parent:
                self.db.execute('UPDATE messages SET selected_child=? WHERE id=?', (message_id, parent))
            self.db.execute('UPDATE chats SET active_leaf=? WHERE id=?', (message_id, chat_id))
            self.db.execute("UPDATE chats SET updated=CURRENT_TIMESTAMP WHERE id=?", (chat_id,))
        return message_id

    def checkpoint(self, message_id, text, state='generating', error=''):
        with self.db:
            self.db.execute('UPDATE messages SET text=?,state=?,error=? WHERE id=?', (text, state, error, message_id))
            if state != 'generating':
                self.db.execute('UPDATE chats SET updated=CURRENT_TIMESTAMP WHERE id=(SELECT chat_id FROM messages WHERE id=?)', (message_id,))

    def pin(self, chat_id):
        with self.db:
            self.db.execute('UPDATE chats SET pinned=1-pinned WHERE id=?', (chat_id,))

    def remove_branch(self, message_id):
        node = self.node(message_id)
        if not node:
            return
        with self.db:
            # Summaries may contain removed branch content; invalidate chat summaries.
            self.db.execute('DELETE FROM summaries WHERE chat_id=?', (node['chat_id'],))
            self.db.execute('''WITH RECURSIVE branch(id) AS (SELECT ? UNION ALL
                SELECT m.id FROM messages m JOIN branch b ON m.parent_id=b.id)
                DELETE FROM messages WHERE id IN (SELECT id FROM branch)''', (message_id,))
            siblings = self.siblings(node)
            replacement = siblings[-1] if siblings else node['parent_id']
            if node['parent_id']:
                self.db.execute('UPDATE messages SET selected_child=? WHERE id=?',
                                (siblings[-1] if siblings else None, node['parent_id']))
            self.db.execute('UPDATE chats SET active_leaf=? WHERE id=?', (replacement, node['chat_id']))
        if replacement:
            self.select(replacement)

    def save_summary(self, chat_id, through_id, text, model):
        with self.db:
            self.db.execute('INSERT INTO summaries(chat_id,through_id,text,model) VALUES (?,?,?,?)',
                            (chat_id, through_id, text, model))

    def summary(self, chat_id, path):
        ids = {node['id'] for node in path}
        for row in self.db.execute('SELECT * FROM summaries WHERE chat_id=? ORDER BY id DESC', (chat_id,)):
            if row['through_id'] in ids:
                return dict(row)

    def clear_summaries(self, chat_id):
        with self.db:
            self.db.execute('DELETE FROM summaries WHERE chat_id=?', (chat_id,))

    def rename(self, chat_id, title):
        with self.db:
            self.db.execute("UPDATE chats SET title=?,manual_title=1 WHERE id=?", (title.strip()[:80] or "新对话", chat_id))

    def auto_title(self, chat_id, text):
        title = ' '.join(text.split()).strip('"“”')[:32]
        if title:
            with self.db:
                self.db.execute('UPDATE chats SET title=? WHERE id=? AND manual_title=0', (title, chat_id))

    def delete(self, chat_id):
        with self.db:
            # Legacy recall snapshots may contain quotations from deleted chats.
            self.db.execute('DELETE FROM recall_sources')
            self.db.execute("DELETE FROM chats WHERE id=?", (chat_id,))

    def close(self):
        self.db.close()
