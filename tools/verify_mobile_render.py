"""Bounded long-chat rendering check; uses isolated data and no network."""
import os
import sys
import tempfile
import time
import gc
import weakref
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with tempfile.TemporaryDirectory() as folder:
    os.environ['TALKAPP_DATA_DIR'] = folder
    from main import register_font
    register_font()
    from talkapp.ui import ChatView
    from talkapp.legacy_widgets import Bubble
    from kivy.clock import Clock
    with patch('talkapp.ui.Speaker'), patch('talkapp.ui.BackupService'):
        view = ChatView()
        parent = None
        for index in range(120):
            parent = view.history.append(view.chat_id, 'user' if index % 2 == 0 else 'assistant',
                                         'long chat message ' * 12, parent=parent)
        start = time.perf_counter()
        view.render()
        count = sum(isinstance(child, Bubble) for child in view.messages.children)
        print('render seconds:', round(time.perf_counter() - start, 3), 'bubbles:', count)
        assert count <= 30, f'long chat created {count} bubbles'
        discarded = [weakref.ref(child) for child in view.messages.children if isinstance(child, Bubble)]
        view.render(focus_id=parent - 80)
        assert sum(isinstance(child, Bubble) for child in view.messages.children) <= 30
        view.jump_bottom()
        assert view.visible_message_ids[-1] == parent
        for _ in range(3):
            Clock.tick()
        gc.collect()
        assert not any(ref() for ref in discarded), 'discarded bubbles are still retained'
        before = tuple(view.messages.children)
        view.resume()
        assert tuple(view.messages.children) == before, 'resume rebuilt the message list'
        view.shutdown()
    print('mobile render checks passed')
