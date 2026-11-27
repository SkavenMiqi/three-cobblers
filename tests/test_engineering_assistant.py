import json
import tempfile
import unittest
from unittest.mock import patch

from talkapp import claude_chat, engineering_assistant, opencode_chat


class EngineeringAssistantTests(unittest.TestCase):
    def test_current_text_identifies_target_without_defaulting_unknown_ide(self):
        target = engineering_assistant.requested_target
        self.assertEqual(target('让 OpenCode 看一下这个方案'), 'opencode')
        self.assertEqual(target('请 Cursor 帮看看'), 'cursor')
        self.assertEqual(target('请 Claude Code 看一下'), 'claudecode')
        self.assertIsNone(target('不要调用 Claude Code'))
        self.assertEqual(target('让工程助手检查这个思路'), 'opencode')
        self.assertIsNone(target('不要调用 OpenCode'))
        self.assertIsNone(target('OpenCode 是什么？'))
        self.assertIsNone(target('比较 Cursor 和 OpenCode'))
        with self.assertRaisesRegex(ValueError, '尚未接入'):
            engineering_assistant.consult('cursor', '请 Cursor 帮看看')

    def test_dispatch_preserves_user_text_and_uses_fixed_workspace(self):
        with patch.dict(engineering_assistant.ADAPTERS, {'opencode': lambda text, path: (text, None)}):
            self.assertEqual(engineering_assistant.consult('opencode', '让 OpenCode 给点建议'), '让 OpenCode 给点建议')

    def test_opencode_uses_literal_argument_and_denies_tools(self):
        event = {'type': 'text', 'part': {'text': '建议'}, 'sessionID': 'ses_test'}
        with tempfile.TemporaryDirectory() as folder, patch.object(opencode_chat, 'executable', return_value='opencode.exe'), \
                patch.object(opencode_chat.subprocess, 'run') as run:
            run.return_value.stdout = json.dumps(event)
            run.return_value.returncode = 0
            self.assertEqual(opencode_chat.ask('--auto & example', folder), ('建议', 'ses_test'))
            self.assertEqual(run.call_args.args[0][-2:], ['--', '--auto & example'])
            self.assertEqual(run.call_args.kwargs['env']['OPENCODE_PERMISSION'], '{"*": "deny"}')

    def test_provider_failure_is_not_a_reply(self):
        with self.assertRaisesRegex(ValueError, 'offline'):
            opencode_chat.parse_result('{"type":"error","error":{"data":{"message":"offline"}}}')

    def test_claude_code_has_no_tools_and_receives_prompt_on_stdin(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-only'}), \
                patch.object(claude_chat, 'executable', return_value='claude.exe'), \
                patch.object(claude_chat.subprocess, 'run') as run:
            run.return_value.stdout = json.dumps({'result': '建议'})
            run.return_value.returncode = 0
            self.assertEqual(engineering_assistant.consult('claudecode', '--resume & 示例'), '建议')
            args = run.call_args.args[0]
            self.assertEqual(args[args.index('--tools') + 1], '')
            self.assertIn('--strict-mcp-config', args)
            self.assertIn('--bare', args)
            self.assertIn('--no-session-persistence', args)
            self.assertEqual(run.call_args.kwargs['input'], '--resume & 示例')
            self.assertNotIn('--resume & 示例', args)

    def test_claude_without_key_does_not_launch(self):
        with patch.dict('os.environ', clear=True), patch.object(claude_chat.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'ANTHROPIC_API_KEY'):
                engineering_assistant.consult('claudecode', '请 Claude Code 看一下')
            run.assert_not_called()
