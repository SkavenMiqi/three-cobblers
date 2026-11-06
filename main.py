from pathlib import Path
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
        self.chat.progress_meter = header._system_bus.progress_meter
        self.chat.progress_meter.open_progress = self.chat.open_progress
        self.chat.refresh_progress()
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
