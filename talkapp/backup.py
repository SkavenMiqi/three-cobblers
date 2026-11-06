"""Portable authenticated backups: SQLite snapshot + settings, local/WebDAV."""
import base64
import io
import json
import os
import sqlite3
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from .storage import data_dir

MAGIC = b'TALKBACK1'
SETTINGS = ('llm.json', 'profiles.json', 'reading.json', 'speech.json', 'appearance.json', 'collaboration.json', 'prompts.json')


@dataclass
class BackupConfig:
    enabled: bool = False
    folder: str = ''
    webdav_url: str = ''
    username: str = ''
    password: str = ''
    passphrase: str = ''
    interval_hours: int = 24
    keep: int = 7

    @classmethod
    def load(cls):
        try:
            raw = json.loads((data_dir() / 'backup.json').read_text(encoding='utf-8'))
            return cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self):
        if self.enabled and len(self.passphrase) < 8:
            raise ValueError('备份口令至少8个字符，恢复时必须使用相同口令')
        if not 1 <= self.interval_hours <= 720 or not 1 <= self.keep <= 100:
            raise ValueError('间隔需为1–720小时，保留份数需为1–100')
        if self.webdav_url:
            from urllib.parse import urlparse
            parsed = urlparse(self.webdav_url)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('WebDAV需填写HTTPS目录地址，不在URL内写账号')
        path = data_dir() / 'backup.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(asdict(self), ensure_ascii=False), encoding='utf-8')
        temporary.chmod(0o600)
        temporary.replace(path)


def encrypt(data, passphrase):
    if len(passphrase) < 8:
        raise ValueError('备份口令至少8个字符')
    salt, nonce = os.urandom(16), os.urandom(12)
    key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode())
    return MAGIC + salt + nonce + AESGCM(key).encrypt(nonce, data, MAGIC)


def decrypt(data, passphrase):
    if not data.startswith(MAGIC) or len(data) < 60:
        raise ValueError('不是有效的TalkApp备份')
    from cryptography.exceptions import InvalidTag
    offset = len(MAGIC)
    salt, nonce = data[offset:offset + 16], data[offset + 16:offset + 28]
    key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode())
    try:
        return AESGCM(key).decrypt(nonce, data[offset + 28:], MAGIC)
    except InvalidTag:
        raise ValueError('备份口令错误或文件已损坏') from None


def archive(root=None):
    root = Path(root or data_dir())
    output = io.BytesIO()
    with tempfile.TemporaryDirectory(dir=root) as folder:
        snapshot = Path(folder) / 'history.db'
        source = sqlite3.connect(root / 'history.db')
        target = sqlite3.connect(snapshot)
        try:
            source.backup(target)
        finally:
            source.close()
            target.close()
        # Temporary conversations never enter a backup, even while active.
        db = sqlite3.connect(snapshot)
        db.execute('PRAGMA foreign_keys=ON')
        columns = {row[1] for row in db.execute('PRAGMA table_info(chats)')}
        if 'temporary' in columns:
            db.execute('DELETE FROM chats WHERE temporary=1')
            db.commit()
            db.execute('VACUUM')
        db.close()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as package:
            package.write(snapshot, 'history.db')
            for name in SETTINGS:
                if (root / name).is_file():
                    package.write(root / name, name)
            package.writestr('manifest.json', json.dumps({'version': 1, 'created': datetime.now(timezone.utc).isoformat()}))
    return output.getvalue()


def restore(payload, passphrase, root=None):
    root = Path(root or data_dir())
    raw = decrypt(payload, passphrase)
    with zipfile.ZipFile(io.BytesIO(raw)) as package:
        allowed = {'history.db', 'manifest.json', *SETTINGS}
        if set(package.namelist()) - allowed or sum(i.file_size for i in package.infolist()) > 512 * 1024 * 1024:
            raise ValueError('备份内容无效或超过512MB')
        manifest = json.loads(package.read('manifest.json'))
        if manifest.get('version') != 1:
            raise ValueError('不支持此备份版本')
        with tempfile.TemporaryDirectory(dir=root) as folder:
            candidate = Path(folder) / 'history.db'
            candidate.write_bytes(package.read('history.db'))
            db = sqlite3.connect(candidate)
            try:
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('备份数据库已损坏')
                for table in ('chats', 'messages'):
                    db.execute(f'SELECT id FROM {table} LIMIT 1')
            finally:
                db.close()
            # Validate settings before changing any live files.
            values = {name: package.read(name) for name in SETTINGS if name in package.namelist()}
            for value in values.values():
                if not isinstance(json.loads(value), (dict, list)):
                    raise ValueError('备份设置无效')
            destination = sqlite3.connect(root / 'history.db')
            source = sqlite3.connect(candidate)
            try:
                source.backup(destination)
            finally:
                source.close()
                destination.close()
            for name, value in values.items():
                path = root / name
                temporary = path.with_suffix('.restore')
                temporary.write_bytes(value)
                temporary.chmod(0o600)
                temporary.replace(path)


class BackupService:
    def __init__(self, notify):
        self.notify = notify
        self.lock = threading.Lock()

    def run(self, force=False):
        config = BackupConfig.load()
        if not config.enabled and not force:
            return
        if len(config.passphrase) < 8:
            return self.notify('请先设置至少8位备份口令')
        stamp = data_dir() / 'backup-state.json'
        try:
            last = json.loads(stamp.read_text()).get('time', 0)
        except (OSError, ValueError):
            last = 0
        if not force and time.time() - last < config.interval_hours * 3600:
            return
        if not self.lock.acquire(blocking=False):
            return
        def worker():
            try:
                payload = encrypt(archive(), config.passphrase)
                folder = Path(config.folder) if config.folder else data_dir() / 'backups'
                folder.mkdir(parents=True, exist_ok=True)
                name = 'talkapp-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.talkbackup'
                path = folder / name
                temporary = path.with_suffix('.tmp')
                temporary.write_bytes(payload)
                temporary.replace(path)
                if config.webdav_url:
                    with httpx.Client(timeout=90, follow_redirects=False) as client:
                        response = client.put(config.webdav_url.rstrip('/') + '/' + name, content=payload,
                                              auth=(config.username, config.password))
                        response.raise_for_status()
                for old in sorted(folder.glob('talkapp-*.talkbackup'), reverse=True)[config.keep:]:
                    old.unlink()
                stamp.write_text(json.dumps({'time': time.time(), 'file': str(path)}))
                if force:
                    self.notify('加密备份已完成')
            except Exception:
                self.notify('备份未完成，请检查目录、口令和WebDAV配置')
            finally:
                self.lock.release()
        threading.Thread(target=worker, daemon=True).start()
