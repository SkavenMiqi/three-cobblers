"""The phone model delegates a bounded task, not the conversation transcript."""
import hashlib
import secrets

from . import harness_lan
from .app_tools import TEXT, function

NAME = 'delegate_to_harness'
TOOL = function(NAME, '用户明确要求在电脑上执行工程任务时才使用。只传必要的任务和项目背景，不传聊天原文或密钥。',
                {'task': TEXT}, ['task'])
STATUS_NAME = 'check_harness_task'
STATUS_TOOL = function(STATUS_NAME, '检查当前对话的 Harness 任务结果或待授权操作。不提交新任务。', {})


def scope(replica, chat_id):
    return hashlib.sha256(f'{replica}:{chat_id}'.encode()).hexdigest()[:32]


def snapshot(path):
    """Bound the latest branch text, without importing attachment contents."""
    rows, budget = [], 5600
    for node in reversed(path):
        if node['role'] not in ('user', 'assistant') or node.get('state') == 'generating':
            continue
        text = node['text'].strip()
        if not text:
            continue
        encoded = text.encode('utf-8')
        if budget <= 0 or len(rows) >= 20:
            break
        if len(encoded) > min(1600, budget):
            text = encoded[:min(1600, budget)].decode('utf-8', 'ignore')
        rows.append([node['role'], text])
        budget -= len(text.encode('utf-8'))
    return list(reversed(rows))


def observe(root, conversation, revision, rows):
    try:
        harness_lan.call(root, 'observe', scope=conversation, revision=revision, rows=rows)
    except (OSError, ValueError, KeyError):
        return False
    return True


def check(root, conversation):
    try:
        harness_lan.configure(root)
        state = harness_lan.call(root, 'read', scope=conversation)
    except (OSError, ValueError, KeyError):
        return {'error': '无法确认 Harness 任务状态'}
    if state['permission']:
        return {'status': '等待授权', 'permission': state['permission']}
    return {'status': state['finished'] or ('尚未确认完成' if state['latest_user'] else '暂无任务'),
            'answer': state['answer'][:2400]}


def delegate(root, conversation, args, cancel, *, observed=None):
    task = args.get('task') if isinstance(args, dict) else None
    if not isinstance(task, str) or not task.strip() or len(task.encode('utf-8')) > 8000:
        return {'error': '工程任务为空或太长'}
    try:
        harness_lan.configure(root)
        before = harness_lan.call(root, 'read', scope=conversation)
        if before['permission']:
            return {'status': '已有操作等待授权，不重复派单', 'permission': before['permission']}
        if before['latest_user'] and not before['finished']:
            return {'status': '当前任务尚未确认结束，不提交新任务'}
    except (ValueError, OSError, KeyError):
        return {'error': '电脑 Harness 未连接，任务没有发送'}
    try:
        if cancel.is_set():
            return {'status': '已停止，未发送'}
        payload = {'scope': conversation, 'id': secrets.token_hex(16), 'text': task.strip()}
        if observed is not None:
            payload.update(revision=observed[0], rows=observed[1])
        harness_lan.call(root, 'send', **payload)
        for _ in range(20):
            if cancel.wait(1.5):
                break
            state = harness_lan.call(root, 'read', scope=conversation)
            if state['permission']:
                return {'status': '等待授权，未确认完成', 'permission': state['permission']}
            if state['finished'] and state['latest_user'] != before['latest_user'] and state['latest_user']:
                return {'status': state['finished'], 'answer': state['answer'][:2400]}
        return {'status': '已提交，尚未确认完成；不重复发送'}
    except (OSError, ValueError, KeyError):
        return {'status': '未确认送达或结果；没有重发'}
