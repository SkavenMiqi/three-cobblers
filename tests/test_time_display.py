import unittest
from datetime import datetime, timezone

from talkapp.time_display import local_time, timestamp


class TimeDisplayTests(unittest.TestCase):
    def test_sqlite_utc_time_converted_to_local(self):
        expected = datetime(2026, 11, 5, 8, 30, tzinfo=timezone.utc).astimezone()
        self.assertEqual(local_time('2026-11-05 08:30:00'), expected)
        self.assertEqual(timestamp('2026-11-05 08:30:00', full=True), expected.strftime('%Y-%m-%d %H:%M'))

    def test_explicit_offset_and_unknown_value(self):
        self.assertEqual(local_time('2026-11-05T16:30:00+08:00'), local_time('2026-11-05 08:30:00'))
        self.assertEqual(timestamp(None), '时间未知')
