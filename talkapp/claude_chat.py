"""Call Claude Code without workspace context, tools or saved sessions."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def executable():
    path = shutil.which('claude.exe')
    if path:
        return path
    path = Path(os.environ.get('APPDATA', '')) / 'npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe'
    if path.is_file():
        return str(path.resolve())
    raise ValueError('找不到 Claude Code 可执行文件')


def ask(prompt, _project):
    if not os.environ.get('ANTHROPIC_API_KEY'):
        raise ValueError('Claude Code 文字桥接需要启动 TalkApp 时设置 ANTHROPIC_API_KEY')
    argv = [executable(), '--print', '--bare', '--output-format', 'json', '--tools', '',
            '--setting-sources', '', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
            '--disable-slash-commands', '--no-session-persistence',
            '--system-prompt', '你是文字工程顾问。只根据用户这次发来的文字提供建议；不要声称执行了任何操作。']
    with tempfile.TemporaryDirectory(prefix='talkapp-claude-') as folder:
        env = dict(os.environ, CLAUDE_CONFIG_DIR=folder)
        env.pop('CLAUDECODE', None)
        result = subprocess.run(argv, input=prompt, cwd=folder, env=env, capture_output=True,
                                encoding='utf-8', errors='replace', timeout=180,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        data = json.loads(result.stdout)
    except ValueError:
        data = None
    if result.returncode or not isinstance(data, dict) or data.get('is_error'):
        raise ValueError('Claude Code 请求失败，请检查本机版本、API 密钥与网络')
    text = data.get('result')
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Claude Code 没有返回文字')
    return text.strip()[:16000], None
