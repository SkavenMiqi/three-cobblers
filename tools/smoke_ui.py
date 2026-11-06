"""Start the real Kivy UI with isolated data and close automatically."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with tempfile.TemporaryDirectory() as folder:
    os.environ["TALKAPP_DATA_DIR"] = folder
    from kivy.clock import Clock
    from main import TalkApp

    app = TalkApp()

    def check(_):
        app.chat.new_chat()
        app.chat.settings()
        app.chat.open_history()
        print("UI_SMOKE_OK")
        app.stop()

    Clock.schedule_once(check, 2)
    app.run()
