import threading
import unittest
from dataclasses import asdict
from talkapp.storage import Config
from talkapp.collaboration import CollaborationConfig, identity, discuss, synthesis_prompt
from talkapp.collaboration import parse_audio


class CollaborationTests(unittest.TestCase):
    def test_audio_is_routed_only_to_designated_parser(self):
        profile = asdict(Config(api_key='test', model='mimo-audio'))
        config = CollaborationConfig(audio_parser=identity(profile))
        calls = []
        def call(model, rows, delta, cancel, **kwargs):
            calls.append((model.model, rows, kwargs))
            return '请把计划加入步骤'
        result = parse_audio(config, [profile], 'audio-payload', threading.Event(), call)
        self.assertEqual(result, '请把计划加入步骤')
        self.assertEqual(calls[0][0], 'mimo-audio')
        self.assertEqual(calls[0][2]['task'], 'audio_parse')
        self.assertNotIn('tools', calls[0][2])
        with self.assertRaises(ValueError):
            parse_audio(config, [], 'audio', threading.Event(), call)
    def test_independent_then_review_without_tools(self):
        profiles = [asdict(Config(api_key='test', model=name)) for name in ('a', 'b')]
        config = CollaborationConfig(enabled=True, members=[identity(p) for p in profiles])
        calls = []
        def call(model, rows, delta, cancel, **kwargs):
            calls.append((model.model, kwargs))
            self.assertNotIn('tools', kwargs)
            return '建议' if kwargs['task'].endswith('proposal') else '检查分歧'
        results = discuss(config, profiles, [('user', '问题', None)], threading.Event(), call, lambda _: None)
        self.assertEqual([name for name, _ in calls], ['a', 'b', 'a', 'b'])
        self.assertEqual(len(results), 2)
        self.assertIn('检查分歧', synthesis_prompt(results))

    def test_partial_failure_cancel_and_missing_members(self):
        profiles = [asdict(Config(api_key='test', model=name)) for name in ('a', 'b')]
        config = CollaborationConfig(enabled=True, members=[identity(p) for p in profiles], review=False)
        def call(model, *args, **kwargs):
            if model.model == 'a':
                raise ValueError('failed')
            return '有效意见'
        values = discuss(config, profiles, [('user', '问题', None)], threading.Event(), call, lambda _: None)
        self.assertIn('error', values[0])
        self.assertEqual(values[1]['proposal'], '有效意见')
        cancel = threading.Event()
        cancel.set()
        self.assertEqual(discuss(config, profiles, [], cancel, call, lambda _: None), [])
        with self.assertRaises(ValueError):
            discuss(config, [], [], threading.Event(), call, lambda _: None)
