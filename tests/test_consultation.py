import json
import tempfile
import threading
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
from talkapp.storage import Config
from talkapp.collaboration import CollaborationConfig, review_answer


class ConsultationTests(unittest.TestCase):
    def test_old_full_collaboration_migrates_once_preserving_parser(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'TALKAPP_DATA_DIR': folder}):
            path = Path(folder) / 'collaboration.json'
            path.write_text(json.dumps({'enabled': True, 'review': True, 'members': ['a'], 'audio_parser': 'mimo'}))
            config = CollaborationConfig.load()
            self.assertFalse(config.enabled)
            self.assertEqual(config.audio_parser, 'mimo')
            self.assertEqual(config.members, ['a'])
            config.enabled = True
            config.save()
            self.assertTrue(CollaborationConfig.load().enabled)

    def test_review_exactly_one_call_no_tools_and_limited_output(self):
        calls = []
        def call(config, rows, delta, cancel, **kwargs):
            calls.append(kwargs)
            self.assertLessEqual(config.max_output_tokens, 1200)
            self.assertNotIn('tools', kwargs)
            return '基本可靠'
        self.assertEqual(review_answer(asdict(Config(api_key='test')), '问题', '答案', threading.Event(), call), '基本可靠')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['task'], 'answer_review')
