import os
import sys
from pathlib import Path

# SDL suppresses the native Windows IME candidate window by default. This
# must be set before Kivy initializes its SDL window and text input.
if sys.platform == 'win32':
    os.environ['SDL_IME_SHOW_UI'] = '1'

from kivy.app import App
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout


def register_font():
    fonts = Path(__file__).parent / 'assets' / 'fonts'
    LabelBase.register('Roboto', fn_regular=str(fonts / 'roboto_regular.ttf'))
    LabelBase.register('Symbols', fn_regular=str(fonts / 'symbols.ttf'))


class TalkApp(App):
    title = 'TalkApp'
    icon = str(Path(__file__).parent / 'assets/brand/icon.png')

    def build(self):
        register_font()
        from utils.skin import load_skin
        load_skin()
        from talkapp.ui import ChatView
        from topbar import TopBar
        Window.clearcolor = (.020, .022, .024, 1)
        Window.softinput_mode = 'below_target'
        root = FloatLayout()
        layout = BoxLayout(orientation='vertical')
        self.chat = ChatView()
        header = TopBar('AI ASSISTANT\nAI 助手')
        layout.add_widget(header)
        layout.add_widget(self.chat)
        root.add_widget(layout)
        from talkapp.safe_area import SafeArea
        self.safe_area = SafeArea(layout)
        self.chat.output_slider = header.output_slider
        header.output_slider.on_change = self.chat.set_output_mode
        self.chat.refresh_output_mode()
        from talkapp.boot import BootOverlay
        root.add_widget(BootOverlay(configured=self.chat.config.is_configured))
        return root

    def on_pause(self):
        self.chat.pause()
        return True

    def on_resume(self):
        self.chat.resume()

    def on_stop(self):
        self.safe_area.close()
        self.chat.shutdown()


if __name__ == '__main__':
    TalkApp().run()
