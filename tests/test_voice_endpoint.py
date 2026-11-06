import array
import sys
import threading
import types
import unittest
from unittest.mock import patch

from talkapp.voice_chat import record_until_silence


class EndpointTests(unittest.TestCase):
    def test_force_finish_submits_even_below_detection_threshold(self):
        elapsed = [0.0]
        finish = threading.Event()
        class Stream:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, count):
                elapsed[0] += .1
                if elapsed[0] >= .5:
                    finish.set()
                return array.array('h', [50, -50] * (count // 2)).tobytes(), False
        with patch.dict(sys.modules, {'sounddevice': types.SimpleNamespace(RawInputStream=lambda **kw: Stream())}), \
             patch('talkapp.voice_chat.time.monotonic', side_effect=lambda: elapsed[0]):
            result = record_until_silence(threading.Event(), finish)
        self.assertIsNotNone(result)
        self.assertLess(elapsed[0], 1)
