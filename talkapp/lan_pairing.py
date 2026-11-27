"""Explicit LAN pairing and authenticated, opt-in chat exchange over pinned TLS."""
import base64
import hashlib
import ipaddress
import json
import os
import secrets
import socket
import ssl
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hmac import compare_digest
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from . import chat_sync
from . import progress_sync

PORT = 47631
TTL = 300
PREFIX = 'TALKAPP1-'
PRIVATE = tuple(ipaddress.ip_network(value) for value in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16'))


def lan_address(value):
    address = ipaddress.IPv4Address(value)
    if not any(address in network for network in PRIVATE):
        raise ValueError('请输入电脑的局域网 IPv4 地址')
    return str(address)


def local_address():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(('192.0.2.1', 9))  # routing lookup only; no datagram sent
            return lan_address(sock.getsockname()[0])
        except (OSError, ValueError):
            return ''


def _save(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    with os.fdopen(os.open(tmp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600), 'wb') as stream:
        stream.write(value)
    tmp.replace(path)


def _load(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def auto_sync(root, mobile):
    """Return the startup setting only while a local pairing exists."""
    root = Path(root)
    peer = root / ('lan-computer.json' if mobile else 'lan-phone.json')
    if not peer.is_file():
        return None
    value = _load(root / 'lan-auto-sync.json')
    if mobile:
        return True if value is True else None
    if isinstance(value, str):
        try:
            return lan_address(value)
        except ValueError:
            pass
    return None


def set_auto_sync(root, value=None):
    path = Path(root) / 'lan-auto-sync.json'
    if value is None:
        path.unlink(missing_ok=True)
    else:
        if value is not True:
            value = lan_address(value)
        _save(path, json.dumps(value).encode('ascii'))


def _write(connection, data):
    connection.sendall(json.dumps(data, separators=(',', ':')).encode('ascii') + b'\n')


def _read(connection):
    deadline = time.monotonic() + 3
    line = bytearray()
    while len(line) < 2048 and b'\n' not in line:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('配对消息超时')
        connection.settimeout(remaining)
        chunk = connection.recv(2048 - len(line))
        if not chunk:
            break
        line.extend(chunk)
    if not line.endswith(b'\n'):
        raise ValueError('无效的配对消息')
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError('无效的配对消息')
    return value


def _hex(value, size):
    return isinstance(value, str) and len(value) == size and all(char in '0123456789abcdef' for char in value)


def _frame(connection, value=None, *, limit=chat_sync.FRAME):
    connection.settimeout(15)
    if value is not None:
        data = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        if len(data) > limit:
            raise ValueError('同步批次过大')
        connection.sendall(len(data).to_bytes(4, 'big') + data)
        return None
    deadline = time.monotonic() + 15

    def read(size):
        buffer = bytearray()
        while len(buffer) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('同步超时')
            connection.settimeout(remaining)
            data = connection.recv(min(size - len(buffer), 65536))
            if not data:
                raise OSError('同步连接中断')
            buffer.extend(data)
        return buffer

    size = int.from_bytes(read(4), 'big')
    if not 0 < size <= limit:
        raise ValueError('同步批次大小无效')
    result = json.loads(read(size))
    if not isinstance(result, dict):
        raise ValueError('无效同步数据')
    return result


def _identity(root):
    pem = root / 'lan-identity.pem'
    if not pem.exists():
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'TalkApp LAN')])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
                .not_valid_after(now + timedelta(days=3650)).sign(key, hashes.SHA256()))
        _save(pem, cert.public_bytes(serialization.Encoding.PEM) + key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    certificate = pem.read_bytes().split(b'-----END CERTIFICATE-----', 1)[0] + b'-----END CERTIFICATE-----\n'
    return pem, x509.load_pem_x509_certificate(certificate).fingerprint(hashes.SHA256()).hex()


class PairingHost:
    def __init__(self, root, address, port=PORT):
        self.root = Path(root)
        self.address = lan_address(address)
        self.peer_file = self.root / 'lan-phone.json'
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.invite = ''
        self.deadline = 0
        self.sync_enabled = False
        identity, self.fingerprint = _identity(self.root)
        self.tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.tls.minimum_version = ssl.TLSVersion.TLSv1_2
        self.tls.load_cert_chain(str(identity))
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.listener.bind((self.address, port))
            self.listener.listen(3)
            self.listener.settimeout(.4)
        except OSError:
            self.listener.close()
            raise
        self.port = self.listener.getsockname()[1]
        self.worker = threading.Thread(target=self._serve, daemon=True)
        self.worker.start()

    def invitation(self):
        with self.lock:
            if self.peer_file.exists():
                raise ValueError('已有配对手机，请先解除配对')
            self.invite = secrets.token_hex(24)
            self.deadline = time.monotonic() + TTL
            raw = json.dumps([self.address, self.port, self.fingerprint, self.invite], separators=(',', ':'))
            return PREFIX + base64.urlsafe_b64encode(raw.encode('ascii')).decode('ascii')

    def paired(self):
        return self.peer_file.is_file()

    def invitation_active(self):
        with self.lock:
            return bool(self.invite) and time.monotonic() < self.deadline

    def forget(self):
        with self.lock:
            self.invite = ''
            self.peer_file.unlink(missing_ok=True)

    def close(self):
        with self.lock:
            self.invite = ''
            self.stop.set()
        self.listener.close()

    def _serve(self):
        while not self.stop.is_set():
            try:
                conn, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with conn:
                conn.settimeout(3)
                try:
                    with self.tls.wrap_socket(conn, server_side=True) as secure:
                        request = _read(secure)
                        with self.lock:
                            reply = self._respond(request) if not self.stop.is_set() else {'ok': False}
                        if request.get('op') == 'sync' and reply.get('ok'):
                            self._sync(secure, request)
                            continue
                        _write(secure, reply)
                except (OSError, ValueError, KeyError, TypeError, RecursionError, sqlite3.Error):
                    continue

    def _sync(self, connection, request):
        peer = request.get('replica')
        if not chat_sync.valid_id(peer):
            _write(connection, {'ok': False})
            return
        path = self.root / 'history.db'
        recovery = request.get('restore_v') == 1
        progress = request.get('progress_v') == 1
        with chat_sync.database(path) as db:
            own = chat_sync.identity(db)
            received = chat_sync.cursors(db, peer)
            wanted = chat_sync.restore_request(db) if recovery else None
        if peer == own:
            _write(connection, {'ok': False, 'error': '两台设备使用同一份数据库副本，暂不能同步'})
            return
        _write(connection, {'ok': True, 'replica': own, 'received': received, 'restore_v': 1, 'want': wanted, 'progress_v': 1,
                            'opencode_v': 3})
        batch = _frame(connection)
        recovery_batch = _frame(connection) if recovery else {}
        progress_batch = _frame(connection) if progress else {}
        with self.lock:
            if self.stop.is_set() or not self._respond(request).get('ok'):
                return
            with chat_sync.database(path) as db:
                v = request.get('opencode_v')
                chat_sync.receive(db, peer, batch['events'], opencode=v in (2, 3), execution=v == 3)
                if recovery:
                    chat_sync.receive_restore(db, wanted, recovery_batch.get('offer'))
                    recovery_reply = {'offer': chat_sync.restore_offer(db, recovery_batch.get('want'))}
                reply = {'events': chat_sync.outgoing(db, batch['after'])}
                if progress:
                    progress_sync.receive(db, progress_batch['values'])
                    progress_reply = {'values': progress_sync.outgoing(db, progress_batch['after'])}
        _frame(connection, reply)
        if recovery:
            _frame(connection, recovery_reply)
        if progress:
            _frame(connection, progress_reply)

    def _respond(self, request):
        secret = request.get('secret')
        if request.get('op') == 'pair' and _hex(secret, 48) and self.invite and time.monotonic() < self.deadline:
            if compare_digest(self.invite, secret):
                token = secrets.token_hex(32)
                _save(self.peer_file, json.dumps({'token_hash': hashlib.sha256(token.encode('ascii')).hexdigest()}).encode())
                self.invite = ''
                return {'ok': True, 'token': token}
        if (request.get('op') == 'ping' or (request.get('op') == 'sync' and self.sync_enabled)) and _hex(secret, 64):
            peer = _load(self.peer_file)
            digest = peer.get('token_hash') if isinstance(peer, dict) else None
            if _hex(digest, 64) and compare_digest(digest, hashlib.sha256(secret.encode('ascii')).hexdigest()):
                return {'ok': True}
        return {'ok': False}


@contextmanager
def _connected(address, port, fingerprint):
    address = lan_address(address)
    if type(port) is not int or not 1024 <= port <= 65535 or not _hex(fingerprint, 64):
        raise ValueError('配对地址无效')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE  # explicit pin is checked before any credential is sent
    with socket.create_connection((address, port), timeout=4) as conn, context.wrap_socket(conn) as secure:
        actual = hashlib.sha256(secure.getpeercert(binary_form=True)).hexdigest()
        if not compare_digest(fingerprint, actual):
            raise ValueError('电脑身份不匹配，请重新配对')
        yield secure


def _call(address, port, fingerprint, op, secret):
    with _connected(address, port, fingerprint) as secure:
        _write(secure, {'op': op, 'secret': secret})
        reply = _read(secure)
    if reply.get('ok') is not True:
        raise ValueError('配对串已过期、已使用，或配对已解除')
    return reply


def pair(root, code):
    code = code.strip()
    if not code.startswith(PREFIX) or len(code) > 512:
        raise ValueError('请粘贴电脑生成的完整配对串')
    try:
        address, port, fingerprint, invite = json.loads(base64.urlsafe_b64decode(code[len(PREFIX):]))
        if not isinstance(address, str) or not _hex(invite, 48):
            raise ValueError()
    except (ValueError, TypeError, RecursionError) as exc:
        raise ValueError('配对串格式错误，请重新复制') from exc
    token = _call(address, port, fingerprint, 'pair', invite).get('token')
    if not _hex(token, 64):
        raise ValueError('电脑未返回有效凭据')
    _save(Path(root) / 'lan-computer.json', json.dumps([address, port, fingerprint, token]).encode())


def _computer(root):
    value = _load(Path(root) / 'lan-computer.json')
    if not isinstance(value, list) or len(value) != 4 or not _hex(value[3], 64):
        raise ValueError('尚未配对电脑')
    return value


def check(root):
    value = _computer(root)
    _call(*value[:3], 'ping', value[3])


def sync(root, cancel=None):
    value = _computer(root)
    path = Path(root) / 'history.db'
    with chat_sync.database(path) as db:
        own = chat_sync.identity(db)
    with _connected(*value[:3]) as secure:
        _write(secure, {'op': 'sync', 'secret': value[3], 'replica': own, 'restore_v': 1, 'progress_v': 1, 'opencode_v': 3})
        hello = _read(secure)
        if hello.get('ok') is not True:
            raise ValueError(hello.get('error', '请在电脑开启同步，或检查配对'))
        peer = hello.get('replica')
        if not chat_sync.valid_id(peer) or peer == own:
            raise ValueError('电脑同步身份无效')
        with chat_sync.database(path) as db:
            after = chat_sync.cursors(db, peer)
            events = chat_sync.outgoing(db, hello.get('received'), opencode=True)
            if hello.get('opencode_v') != 3:
                # Send ordinary history up to the first request; an old host
                # must not acknowledge a request it cannot put in the inbox.
                for index, event in enumerate(events):
                    if event.get('opencode_execution') or (event.get('opencode_request') and hello.get('opencode_v') != 2):
                        events = events[:index]
                        break
            wanted = chat_sync.restore_request(db)
        if cancel and cancel.is_set():
            return
        _frame(secure, {'after': after, 'events': events})
        recovery = hello.get('restore_v') == 1
        progress = hello.get('progress_v') == 1
        if recovery:
            with chat_sync.database(path) as db:
                offer = chat_sync.restore_offer(db, hello.get('want'))
            _frame(secure, {'want': wanted, 'offer': offer})
        if progress:
            with chat_sync.database(path) as db:
                sent, received = progress_sync.scan(db, peer)
                progress_out = progress_sync.outgoing(db, sent)
            _frame(secure, {'after': received, 'values': progress_out})
        incoming = _frame(secure).get('events')
        recovery_reply = _frame(secure) if recovery else {}
        progress_reply = _frame(secure) if progress else {}
        if cancel and cancel.is_set():
            return
        with chat_sync.database(path) as db:
            chat_sync.receive(db, peer, incoming)
            if recovery:
                chat_sync.receive_restore(db, wanted, recovery_reply.get('offer'))
            if progress:
                progress_in = progress_reply['values']
                progress_sync.receive(db, progress_in)
                progress_sync.checkpoint(db, peer, progress_out, progress_in)
    if wanted and not recovery:
        raise ValueError('请先更新电脑版，再恢复对话')
