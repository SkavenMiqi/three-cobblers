"""Render representative narrow-screen layouts using isolated sample history."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as folder:
    os.environ['TALKAPP_DATA_DIR'] = folder
    from kivy.clock import Clock
    from kivy.core.window import Window
    from main import TalkApp
    from talkapp.storage import History
    history = History()
    chat = history.create()
    history.append(chat, 'user', '我想把学习 Python 安排得更有条理，能给些建议吗？')
    history.append(chat, 'assistant', '可以先从一个小目标开始：\n\n- 每天用 20 分钟完成一个练习。\n- 把遇到的问题记下来，第二天回顾。\n- 每周做一个能运行的小工具。\n\n**先坚持一周，再调整节奏。**', model='GPT · 示例', provider='example.com')
    history.rename(chat, 'Python 学习计划')
    other = history.create()
    history.append(other, 'user', '周末去哪里散步比较好？')
    history.rename(other, '周末散步')
    history.db.execute("UPDATE chats SET updated='2026-10-28 08:30:00' WHERE id=?", (other,))
    history.db.commit()
    history.pin(chat)
    history.close()
    Window.size = (420, 780)
    app = TalkApp()
    def main_preview(_):
        app.chat.chat_id = chat
        app.chat.render()
        Clock.schedule_once(capture_main, .5)
    def capture_main(_):
        Window.screenshot(name=str(root / 'backups/compact-chat.png'))
        app.chat.open_history()
        Clock.schedule_once(capture_history, .5)
    def capture_history(_):
        Window.screenshot(name=str(root / 'backups/compact-history.png'))
        app.stop()
        print('COMPACT_UI_PREVIEW_OK')
    Clock.schedule_once(main_preview, .5)
    app.run()
