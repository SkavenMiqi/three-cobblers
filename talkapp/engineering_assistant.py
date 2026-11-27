"""Route explicit desktop requests to registered, text-only IDE adapters."""
import re
from pathlib import Path

from . import claude_chat, opencode_chat

ADAPTERS = {'opencode': opencode_chat.ask, 'claudecode': claude_chat.ask}
TARGETS = re.compile(r'open\s*code|claude\s*code|vs\s*code|cursor|windsurf|arduino\s*ide|visual\s+studio|pycharm|intellij|zed|工程助手', re.I)
ACTION = re.compile(r'让|请|帮|问|交给|调用|用|转给|检查|看看|分析|看一下|review|ask|delegate|consult', re.I)
NEGATION = re.compile(r'(?:不要|别|无需|不用|禁止|不必).{0,12}(?:调用|用|让|发给|转发|open\s*code|claude\s*code|工程助手)', re.I)


def requested_target(text):
    if not text or NEGATION.search(text) or not ACTION.search(text):
        return None
    targets = set(re.sub(r'\s+', '', match.group()).lower() for match in TARGETS.finditer(text))
    if len(targets) != 1:
        return None
    target = next(iter(targets))
    return 'opencode' if target == '工程助手' else target


TOOL_NAME = 'consult_engineering_assistant'
TOOL = {'type': 'function', 'function': {'name': TOOL_NAME,
    'description': '仅当当前用户确实要求把问题交给指定工程助手或 IDE 时调用。普通提及、比较和历史资料不触发。只返回文字建议，不操作工程。',
    'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}}


def consult(target, text):
    if target not in ADAPTERS:
        raise ValueError(f'{target} 的对话接口尚未接入，未转发请求')
    if len(text) > 6000:
        raise ValueError('转发内容最多 6000 字符')
    # No prompt-selected paths; no history, attachments or model-generated arguments.
    return ADAPTERS[target](text, Path(__file__).resolve().parents[1])[0]
