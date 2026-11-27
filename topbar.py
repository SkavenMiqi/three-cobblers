from datetime import datetime, timedelta
import os

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle, Line
from kivy.metrics import dp
from config import theme
from utils.instrument import StatusLamp
from talkapp import header_data as db
from talkapp.output_modes import DEFAULT_MODE, MODES
import sounds


class HamburgerButton(Button):
    def __init__(self, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(44), dp(44)),
                         background_normal="", background_color=(0, 0, 0, 0), **kwargs)
        self._line_color = theme.TEXT_SECONDARY
        self.bind(pos=self._draw, size=self._draw)
        self.bind(on_press=self._on_down, on_release=self._on_up)

    def _on_down(self, *_):
        sounds.play_click()
        self._line_color = sounds.lighten(theme.TEXT_SECONDARY)
        self._draw()

    def _on_up(self, *_):
        self._line_color = theme.TEXT_SECONDARY
        self._draw()

    def _draw(self, *args):
        self.canvas.after.clear()
        x = self.x + self.width * 0.18
        w = self.width * 0.64
        h = dp(2)
        gap = dp(5)
        cy = self.y + self.height / 2
        with self.canvas.after:
            Color(*self._line_color)
            for i in range(3):
                Rectangle(pos=(x, cy + (i - 1) * (h + gap)), size=(w, h))


class OutputModeSlider(Widget):
    COLORS = (theme.VFD_BLUE, theme.LED_GREEN, theme.VFD_ORANGE, (.78, .55, 1, 1))

    def __init__(self, status_label, **kwargs):
        super().__init__(**kwargs)
        self.mode = DEFAULT_MODE
        self.on_change = None
        self.status_label = status_label
        with self.canvas:
            Color(*theme.DISPLAY_GLASS)
            self._bg = Rectangle(pos=self.pos, size=self.size)
            Color(*theme.METAL_DARK)
            self._edge = Line(rectangle=(*self.pos, *self.size), width=dp(0.8))
            self._segments = []
            for _ in MODES:
                self._segments.append((Color(*theme.METAL_DARK), Rectangle()))
        self.bind(pos=self._draw, size=self._draw)
        self.set_mode(DEFAULT_MODE)

    def set_mode(self, mode):
        self.mode = mode
        self.status_label.text = MODES[mode][0]
        self.status_label.color = self.COLORS[mode]
        self._draw()

    def _select_at(self, x):
        mode = int((x - self.x) * len(MODES) / max(1, self.width))
        mode = min(len(MODES) - 1, max(0, mode))
        if mode != self.mode:
            self.set_mode(mode)
            if self.on_change:
                self.on_change(mode)

    def on_touch_down(self, touch):
        if not touch.is_mouse_scrolling and self.collide_point(*touch.pos):
            touch.grab(self)
            self._select_at(touch.x)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self._select_at(touch.x)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self._select_at(touch.x)
            return True
        return super().on_touch_up(touch)

    def _draw(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._edge.rectangle = (*self.pos, *self.size)
        gap = dp(2)
        segment_w = max(0, (self.width - gap * (len(MODES) - 1) - dp(6)) / len(MODES))
        segment_h = max(dp(2), self.height - dp(6))
        x = self.x + dp(3)
        y = self.y + dp(3)
        for index, (color, rect) in enumerate(self._segments):
            color.rgba = self.COLORS[self.mode] if index <= self.mode else theme.METAL_DARK
            rect.pos = (x, y)
            rect.size = (segment_w, segment_h)
            x += segment_w + gap


class SystemBus(BoxLayout):
    """Persistent compact equipment-status group for the right side of TopBar."""

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", size_hint=(None, None),
                         size=(dp(136), dp(46)), padding=[dp(5), dp(3)],
                         spacing=dp(2), **kwargs)
        with self.canvas.before:
            Color(*theme.PANEL)
            self._bg = Rectangle(pos=self.pos, size=self.size)
            Color(*theme.METAL)
            self._border = Line(rectangle=(*self.pos, *self.size), width=dp(0.8))
            Color(*theme.GLASS_HIGHLIGHT)
            self._highlight = Rectangle(pos=self.pos, size=(self.width, dp(1)))
        self.bind(pos=self._draw_frame, size=self._draw_frame)

        top = BoxLayout(size_hint_y=None, height=dp(10), spacing=dp(4))
        bus_label = Label(text="SYSTEM BUS", color=theme.METAL_LIGHT, font_size=dp(8),
                          halign="left", valign="middle")
        bus_label.bind(size=bus_label.setter("text_size"))
        top.add_widget(bus_label)
        self._time = Label(text="--:--:--", color=theme.VFD_ORANGE, font_size=dp(9),
                           size_hint_x=None, width=dp(52), halign="right", valign="middle")
        self._time.bind(size=self._time.setter("text_size"))
        top.add_widget(self._time)
        self.add_widget(top)

        rails = BoxLayout(size_hint_y=None, height=dp(11), spacing=dp(3))
        for label_text, color, breathe in (
                ("LNK", theme.VFD_BLUE, False),
                ("AI", theme.VFD_ORANGE, True),
                ("SYN", theme.LED_GREEN, False)):
            rail = BoxLayout(spacing=dp(2))
            label = Label(text=label_text, color=theme.TEXT_MUTED, font_size=dp(8),
                          size_hint_x=None, width=dp(18), halign="left", valign="middle")
            label.bind(size=label.setter("text_size"))
            rail.add_widget(label)
            lamp = StatusLamp(color=color, breathe=breathe,
                              size=(dp(15), dp(3)), pos_hint={"center_y": 0.5})
            if label_text == "AI":
                self._ai_lamp = lamp
            rail.add_widget(lamp)
            rails.add_widget(rail)
        self.add_widget(rails)

        mode_row = BoxLayout(size_hint_y=None, height=dp(15), spacing=dp(4))
        mode_label = Label(font_size=dp(10), size_hint_x=None, width=dp(24),
                           halign="left", valign="middle")
        mode_label.bind(size=mode_label.setter("text_size"))
        mode_row.add_widget(mode_label)
        self.output_slider = OutputModeSlider(mode_label)
        mode_row.add_widget(self.output_slider)
        self.add_widget(mode_row)
        self._timer = Clock.schedule_interval(self._refresh_time, 1.0)
        self._refresh_time()

    def _refresh_time(self, *_):
        self._refresh_ai_state()
        session = db.get_today_training_session()
        if not session:
            self._time.text = "--:--:--"
            self._time.color = theme.TEXT_MUTED
            return True
        if session.get("duration_seconds") is not None:
            elapsed = int(session["duration_seconds"])
            self._time.color = theme.LED_GREEN
        else:
            try:
                started = datetime.fromisoformat(session["started_at"])
                elapsed = max(0, int((datetime.now() - started).total_seconds()))
            except (TypeError, ValueError):
                elapsed = 0
            self._time.color = theme.VFD_ORANGE
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        self._time.text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return True

    def _refresh_ai_state(self):
        try:
            from talkapp.storage import Config as LLMConfig
            counter = getattr(self, "_ai_cfg_counter", 0) + 1
            self._ai_cfg_counter = counter
            cfg = getattr(self, "_ai_cfg_cache", None)
            if cfg is None or counter % 10 == 0:
                # 每 10 秒重读一次，避免每次刷新都读文件（Android 卡顿）
                cfg = LLMConfig.load()
                self._ai_cfg_cache = cfg
            self._ai_lamp.color = theme.LED_GREEN if cfg.is_configured else theme.VFD_ORANGE
        except Exception:
            self._ai_lamp.color = theme.VFD_ORANGE

    def _draw_frame(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rectangle = (*self.pos, *self.size)
        self._highlight.pos = (self.x + dp(2), self.top - dp(2))
        self._highlight.size = (max(0, self.width - dp(4)), dp(1))

    def on_parent(self, _widget, parent):
        if parent is not None:
            return
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        for widget in self.walk():
            if isinstance(widget, StatusLamp):
                widget.stop()


class ChannelDisplay(BoxLayout):
    """Framed active-page display balancing the SystemBus module."""

    def __init__(self, title_text, **kwargs):
        super().__init__(orientation="vertical", padding=[dp(5), dp(3)],
                         spacing=dp(2), size_hint_x=None, width=dp(158), **kwargs)
        with self.canvas.before:
            Color(*theme.DISPLAY_GLASS)
            self._bg = Rectangle(pos=self.pos, size=self.size)
            Color(*theme.METAL)
            self._border = Line(rectangle=(*self.pos, *self.size), width=dp(0.8))
            Color(*theme.VFD_ORANGE_DIM)
            self._channel = Rectangle(pos=self.pos, size=(dp(2), self.height))
            Color(*theme.GLASS_HIGHLIGHT)
            self._highlight = Rectangle(pos=self.pos, size=(self.width, dp(1)))
        self.bind(pos=self._draw_frame, size=self._draw_frame)

        english, _, chinese = title_text.partition("\n")
        top = BoxLayout(size_hint_y=None, height=dp(10), spacing=dp(4))
        channel_label = Label(text="ACTIVE CHANNEL", color=theme.VFD_ORANGE,
                              font_size=dp(8), halign="left", valign="middle")
        channel_label.bind(size=channel_label.setter("text_size"))
        top.add_widget(channel_label)
        self._date_label = Label(text="", color=theme.VFD_BLUE, font_size=dp(8),
                                 size_hint_x=None, width=dp(58), halign="right", valign="middle")
        self._date_label.bind(size=self._date_label.setter("text_size"))
        top.add_widget(self._date_label)
        self.add_widget(top)

        page = Label(text=f"[b]{english} / {chinese or english}[/b]", markup=True,
                     color=theme.TEXT_PRIMARY, font_size=dp(9),
                     size_hint_y=None, height=dp(11), halign="left", valign="middle")
        page.bind(size=page.setter("text_size"))
        self.add_widget(page)
        self._schedule = MiniSchedule(size_hint_y=None, height=dp(11))
        self.add_widget(self._schedule)
        self._date_timer = Clock.schedule_interval(self._refresh_date, 60)
        self._refresh_date()

    def _refresh_date(self, *_):
        self._date_label.text = datetime.now().strftime("%Y.%m.%d")
        self._schedule.refresh()
        return True

    def _draw_frame(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rectangle = (*self.pos, *self.size)
        self._channel.pos = (self.x + dp(2), self.y + dp(3))
        self._channel.size = (dp(2), max(0, self.height - dp(6)))
        self._highlight.pos = (self.x + dp(2), self.top - dp(2))
        self._highlight.size = (max(0, self.width - dp(4)), dp(1))

    def on_parent(self, _widget, parent):
        if parent is None and self._date_timer is not None:
            self._date_timer.cancel()
            self._date_timer = None


class MiniSchedule(Widget):
    """Seven-slot rectangular week schedule: history cyan, today orange."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._active_dates = {}
        with self.canvas:
            self._slots = []
            for _ in range(7):
                color = Color(*theme.METAL_DARK)
                rect = Rectangle(pos=self.pos, size=(0, 0))
                self._slots.append((color, rect))
        self.bind(pos=self._draw, size=self._draw)
        self.refresh()

    def refresh(self):
        self._active_dates = db.get_active_dates()
        self._draw()

    def _draw(self, *_):
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
        gap = dp(3)
        slot_w = max(dp(3), (self.width - gap * 6) / 7)
        x = self.x
        for index, (color, rect) in enumerate(self._slots):
            day = week_start + timedelta(days=index)
            if day == today:
                color.rgba = theme.VFD_ORANGE
            elif day.isoformat() in self._active_dates:
                color.rgba = theme.VFD_CYAN
            elif day > today:
                color.rgba = theme.DISPLAY_OFF
            else:
                color.rgba = theme.METAL_DARK
            rect.pos = (x, self.y + dp(2))
            rect.size = (slot_w, max(dp(2), self.height - dp(4)))
            x += slot_w + gap


class TopBar(BoxLayout):
    def __init__(self, title_text, on_menu=None, **kwargs):
        super().__init__(size_hint_y=None, height=dp(54), padding=[dp(8), dp(4)], **kwargs)
        with self.canvas.before:
            Color(*theme.CHASSIS)
            self._rect = Rectangle(size=self.size, pos=self.pos)
            Color(*theme.METAL_DARK)
            self._metal = Rectangle(size=self.size, pos=self.pos)
            Color(*theme.HAIRLINE)
            self._line = Rectangle(pos=(self.x, self.y), size=(self.width, dp(1)))
        self.bind(size=self._update_rect, pos=self._update_rect)
        if on_menu:
            burger = HamburgerButton()
            burger.bind(on_release=lambda _: on_menu())
            self.add_widget(burger)
        self._channel_display = ChannelDisplay(title_text)
        self.add_widget(self._channel_display)
        logo_holder = BoxLayout(size_hint_x=1, padding=[dp(2), dp(3)])
        logo_holder.add_widget(Image(source=os.path.join(os.path.dirname(__file__), 'assets', 'brand', 'badge.png'),
                                     allow_stretch=True, keep_ratio=True))
        self.add_widget(logo_holder)
        self._system_bus = SystemBus()
        self.output_slider = self._system_bus.output_slider
        self.add_widget(self._system_bus)
        self.bind(width=self._resize_modules)
        self._resize_modules()
        from utils import fx
        fx.surface(self, 'panel', theme.VFD_BLUE, cut=6)

    def _resize_modules(self, *_):
        available = max(0, self.width - dp(16))
        module_width = min(dp(158), max(dp(132), (available - dp(24)) / 2))
        self._channel_display.width = module_width
        self._system_bus.width = min(dp(136), module_width)

    def _update_rect(self, *args):
        self._rect.size = self.size
        self._rect.pos = self.pos
        self._metal.pos = (self.x + dp(2), self.y + dp(2))
        self._metal.size = (max(0, self.width - dp(4)), max(0, self.height - dp(4)))
        self._line.pos = (self.x, self.y)
        self._line.size = (self.width, dp(1))
