"""Fitness-inspired cold start terminal; cosmetic checks never fake connectivity."""
from pathlib import Path
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.uix.progressbar import ProgressBar
from kivy.graphics import Color, Rectangle, Line
from .legacy_widgets import surface
from . import theme
from utils import fx


class BootOverlay(FloatLayout):
    def __init__(self, configured=False, **kwargs):
        super().__init__(**kwargs)
        surface(self, theme.CHASSIS)
        fx.chassis(self)
        with self.canvas.after:
            self.scan_color = Color(0, .9, .8, 0)
            self.scan = Rectangle(pos=self.pos, size=(self.width, dp(2)))
        self.bind(size=self.draw_scan, pos=self.draw_scan)
        self.scan_position = 0
        panel = BoxLayout(orientation='vertical', size_hint=(.82, None), height=dp(340),
                          pos_hint={'center_x': .5, 'center_y': .52}, padding=dp(20), spacing=dp(12))
        fx.surface(panel, 'glass', theme.VFD_BLUE, cut=14)
        self.panel = panel
        self.emblem = Image(source=str(Path(__file__).resolve().parents[1] / 'assets/brand/badge.png'),
                            size_hint_y=None, height=dp(122), opacity=0)
        panel.add_widget(self.emblem)
        panel.add_widget(Label(text='TALK / PERSONAL AI', color=theme.TEXT_PRIMARY, font_size=dp(22),
                               size_hint_y=None, height=dp(32)))
        self.lines = Label(text='POWER ON  /  电源接通', color=theme.VFD_CYAN, font_size=dp(12),
                           halign='left', valign='middle')
        self.lines.bind(size=self.lines.setter('text_size'))
        panel.add_widget(self.lines)
        self.progress = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(5))
        panel.add_widget(self.progress)
        panel.add_widget(Label(text='BLACK TITANIUM  ·  BUILD 0.2', color=theme.TEXT_MUTED,
                               font_size=dp(9), size_hint_y=None, height=dp(16)))
        self.add_widget(panel)
        panel.opacity = 0
        Animation(opacity=1, duration=.1).start(panel)
        self.events = [Clock.schedule_once(self.ignite, .04),
                       Clock.schedule_once(lambda _: self.stage(18, 'CORE BUS        /   INITIALIZED'), .12),
                       Clock.schedule_once(lambda _: self.stage(42, 'LOCAL HISTORY   /   READY'), .25),
                       Clock.schedule_once(lambda _: self.stage(68, 'PROJECT & PST   /   READY'), .38),
                       Clock.schedule_once(lambda _: self.stage(88, 'AI CONFIG       /   ' + ('LOADED' if configured else 'NOT SET')), .52),
                       Clock.schedule_once(lambda _: self.stage(100, 'TERMINAL ONLINE /   对话终端就绪'), .67),
                       Clock.schedule_once(self.finish, .82)]
        self.scan_event = Clock.schedule_interval(self.sweep, 1 / 60)

    def ignite(self, *_):
        sequence = (Animation(opacity=.85, duration=.07) + Animation(opacity=.15, duration=.04) +
                    Animation(opacity=1, duration=.12))
        sequence.start(self.emblem)

    def draw_scan(self, *_):
        self.scan.pos = (self.x, self.y + self.height * self.scan_position)
        self.scan.size = (self.width, dp(2))

    def sweep(self, dt):
        self.scan_position = (self.scan_position + dt * 1.3) % 1
        self.scan_color.a = .22
        self.draw_scan()

    def stage(self, value, text):
        self.lines.text += '\n' + text
        Animation(value=value, duration=.1).start(self.progress)

    def finish(self, *_):
        self.scan_event.cancel()
        self.scan_color.a = 0
        Animation(height=dp(370), opacity=0, duration=.16, t='in_quad').start(self.panel)
        animation = Animation(opacity=0, duration=.18)
        animation.bind(on_complete=self.cleanup)
        animation.start(self)

    def cleanup(self, *_):
        for event in self.events:
            event.cancel()
        self.scan_event.cancel()
        if self.parent:
            self.parent.remove_widget(self)

    def on_touch_down(self, touch):
        return True
