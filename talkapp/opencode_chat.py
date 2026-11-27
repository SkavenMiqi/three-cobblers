"""Windows desktop TalkApp -> OpenCode, explicitly submitted text-only turns."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

MODEL = '4router/gpt-6.2-sol'


def executable():
    path = shutil.which('opencode.exe')
    if path:
        return path
    # Windows npm installs a shell shim. Use its native executable, never a
    # .cmd shim that could interpret shell characters in the user's prompt.
    path = Path(os.environ.get('APPDATA', '')) / 'npm/node_modules/opencode-ai/bin/opencode.exe'
    if path.is_file():
        return str(path)
    raise ValueError('找不到 OpenCode 可执行文件')


def parse_result(output):
    chunks, session, error = [], None, None
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        session = event.get('sessionID') or session
        part = event.get('part')
        part = part if isinstance(part, dict) else {}
        if event.get('type') == 'text' and isinstance(part.get('text'), str):
            chunks.append(part['text'])
        if event.get('type') == 'error':
            problem = event.get('error')
            data = problem.get('data') if isinstance(problem, dict) else None
            error = (data.get('message') if isinstance(data, dict) else None) or 'OpenCode 请求失败'
    if error:
        raise ValueError(str(error)[:800])
    text = '\n\n'.join(chunks).strip()
    if not text:
        raise ValueError('OpenCode 没有返回文字，请检查模型与服务配置')
    if not isinstance(session, str) or not re.fullmatch(r'ses_[a-zA-Z0-9]+', session):
        session = None
    return text[:16000], session


def ask(prompt, project, session=None):
    project = Path(project).resolve()
    if not project.is_dir():
        raise ValueError('工程目录不存在')
    argv = [executable(), 'run', '--pure', '--format', 'json', '--agent', 'plan', '--model', MODEL]
    if session:
        argv.extend(['--session', session])
    argv.extend(['--', prompt])
    # Deny native tools, shell and MCP in this entry point. This is not a
    # replacement for a sandbox; do not use it as a remote task runner.
    env = dict(os.environ)
    env['OPENCODE_PERMISSION'] = json.dumps({'*': 'deny'})
    env['OPENCODE_CONFIG_CONTENT'] = json.dumps({'permission': {'*': 'deny'},
        'agent': {'plan': {'permission': {'*': 'deny'}}}})
    result = subprocess.run(argv, cwd=project, env=env, capture_output=True, encoding='utf-8',
                            errors='replace', timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    text, session_id = parse_result(result.stdout)
    if result.returncode:
        raise ValueError('OpenCode 未能完成，请检查本机配置和模型连接')
    return text, session_id
