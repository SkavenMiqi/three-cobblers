"""Original fitness AI panel geometry, colors and selectable message bubbles."""
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from . import theme
from utils import fx
from utils.appearance import state as appearance


def surface(widget, color, edge=None, top=False):
    with widget.canvas.before:
        Color(*color)
        rect = Rectangle(pos=widget.pos, size=widget.size)
        if edge:
            Color(*edge)
            line = Rectangle()
    def update(*_):
        rect.pos, rect.size = widget.pos, widget.size
        if edge:
            line.pos = (widget.x, widget.top - dp(1) if top else widget.y)
            line.size = (widget.width, dp(1))
    widget.bind(pos=update, size=update)
    update()


class Bubble(BoxLayout):
    def __init__(self, kind, text, **kwargs):
        bg, fg = (theme.VFD_BLUE, theme.CHASSIS) if kind == "user" else (theme.DISPLAY_GLASS, theme.TEXT_PRIMARY)
        super().__init__(orientation="vertical", size_hint_y=None,
                         padding=[dp(12), dp(8)], spacing=dp(2), **kwargs)
        self.bind(minimum_height=self.setter("height"))
        surface(self, bg)
        fx.surface(self, 'glass', theme.VFD_BLUE if kind == 'user' else theme.VFD_CYAN, cut=8)
        with self.canvas.before:
            Color(*(theme.VFD_BLUE if kind == "user" else theme.BORDER_DIM))
            edge = Rectangle(pos=self.pos, size=(dp(2), self.height))
        self.bind(pos=lambda _, p: setattr(edge, "pos", p),
                  size=lambda _, s: setattr(edge, "size", (dp(2), s[1])))
        source = Label(text="LOCAL TX" if kind == "user" else "AI DATA RX",
                              color=theme.CHASSIS if kind == "user" else theme.VFD_CYAN,
                              font_size=dp(9), size_hint_y=None, height=dp(12),
                              halign="left", valign="middle")
        self.add_widget(source)
        self.source_label = source
        self.content = TextInput(text=text, readonly=True, font_size=dp(15) * appearance.font_scale, foreground_color=fg,
                                 background_normal="", background_active="", background_color=(0, 0, 0, 0),
                                 cursor_color=(0, 0, 0, 0), padding=[dp(2), dp(2)], size_hint_y=None)
        def resize(*_):
            Clock.schedule_once(lambda _: setattr(self.content, "height", max(dp(28),
                len(self.content._lines) * self.content.line_height + dp(6))))
        self.content.bind(width=resize, text=resize)
        self.add_widget(self.content)
        def update_theme(*_):
            if kind == 'user':
                self.content.foreground_color = theme.TEXT_PRIMARY if appearance.enhanced else theme.CHASSIS
                source.color = theme.VFD_BLUE if appearance.enhanced else theme.CHASSIS
        appearance.bind(enhanced=update_theme)
        update_theme()
        resize()
