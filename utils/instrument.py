"""Reusable hardware-style controls: chamfered panels, smoked glass, mechanical keys, status lamps."""

from kivy.animation import Animation
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle, BorderImage
from kivy.metrics import dp
from kivy.properties import ListProperty, NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from config import theme
from utils import fx
from utils.appearance import state as appearance


class InstrumentPanel(BoxLayout):
    """Black-titanium equipment module: chamfered plate with shadow, gradient, brushed metal."""

    def __init__(self, label="MODULE", accent=None, **kwargs):
        self.label = label
        self.accent = accent or theme.VFD_ORANGE
        super().__init__(orientation="vertical", **kwargs)
        self._plate = fx.Plate(style='panel', accent_color=self.accent)
        self.canvas.before.add(self._plate.group)
        self.bind(pos=self._update_plate, size=self._update_plate)
        self._update_plate()

    def _update_plate(self, *_):
        self._plate.update(self.x, self.y, self.width, self.height)


class SmokedDisplay(BoxLayout):
    """Inset smoked-glass data window: recessed, scanlines, cyan edge accent."""

    def __init__(self, accent=None, **kwargs):
        super().__init__(**kwargs)
        self.accent = accent or theme.VFD_CYAN
        self._plate = fx.Plate(style='glass', accent_color=self.accent)
        self.canvas.before.add(self._plate.group)
        self.bind(pos=self._update_plate, size=self._update_plate)
        self._update_plate()

    def _update_plate(self, *_):
        self._plate.update(self.x, self.y, self.width, self.height)


class MechanicalButton(Button):
    """Physical key with gradient, bevel, glowing lamp and pressed offset.

    Kind modes: inset (gray), command (brass), danger (red), system (cyan).
    """

    glow_color = ListProperty(theme.VFD_ORANGE)
    kind = StringProperty("inset")

    def __init__(self, kind="inset", glow_color=None, **kwargs):
        self.kind = kind
        if glow_color is not None:
            self.glow_color = glow_color
        super().__init__(background_normal="", background_down="",
                         background_color=(0, 0, 0, 0), **kwargs)
        self._pressed = False
        # Canvas drawing managed manually (global Button skin skipped due to alpha=0).
        with self.canvas.before:
            # Outer glow ring (drawn first, before face).
            self._halo_color = Color(1, 1, 1, 0)
            self._halo = BorderImage(pos=self.pos, size=self.size,
                                     texture=fx.ring_texture(spread=10),
                                     border=(dp(10), dp(10), dp(10), dp(10)))
            # Shadow base.
            self._shadow_color = Color(*theme.SHADOW)
            self._shadow = Rectangle(pos=self.pos, size=self.size)
            # Face with gradient.
            self._face_color = Color(1, 1, 1, 1)
            self._face = Rectangle(pos=self.pos, size=self.size)
            # Top bevel highlight.
            self._bevel_light_color = Color(*theme.BEVEL_LIGHT)
            self._bevel_light = Rectangle(pos=self.pos, size=(self.width, dp(1)))
            # Bottom bevel shadow.
            self._bevel_dark_color = Color(*theme.BEVEL_DARK)
            self._bevel_dark = Rectangle(pos=self.pos, size=(self.width, dp(1)))
            # Edge outline.
            self._edge_color = Color(*theme.METAL)
            self._edge = Line(rectangle=(*self.pos, *self.size), width=dp(1.2))
            # Left lamp strip with glow.
            self._lamp_glow_color = Color(1, 1, 1, 0)
            self._lamp_glow = BorderImage(pos=self.pos, size=(dp(8), self.height),
                                          texture=fx.ring_texture(spread=6),
                                          border=(dp(6), dp(6), dp(6), dp(6)))
            self._lamp_color = Color(*self.glow_color)
            self._lamp = Rectangle(pos=self.pos, size=(dp(2), self.height))
        self.bind(pos=self._draw_key, size=self._draw_key, state=self._state_changed,
                  glow_color=self._draw_key, kind=self._draw_key)
        self._draw_key()
        appearance.bind(enhanced=self._draw_key)

    def _state_changed(self, _, state):
        self._pressed = state == "down"
        self._draw_key()

    def _draw_key(self, *_):
        # Kind-specific colors.
        if self.kind == "command":
            face_top = (0.36, 0.12, 0.03, 1)
            face_bot = (0.24, 0.07, 0.02, 1)
            edge = self.glow_color
        elif self.kind == "danger":
            face_top = (0.26, 0.05, 0.03, 1)
            face_bot = (0.14, 0.02, 0.02, 1)
            edge = theme.LED_RED
        elif self.kind == "system":
            face_top = (0.03, 0.13, 0.17, 1)
            face_bot = (0.02, 0.07, 0.10, 1)
            edge = theme.VFD_BLUE
        else:
            face_top = theme.PLATE_TOP
            face_bot = theme.PLATE_BOTTOM
            edge = theme.METAL

        if not appearance.enhanced:
            face_top = face_bot = {
                'command': (0.30, 0.095, 0.025, 1),
                'danger': (0.20, 0.035, 0.025, 1),
                'system': (0.025, 0.10, 0.14, 1),
            }.get(self.kind, theme.PANEL_RAISED)

        # Pressed: shift down, darken, boost glow.
        offset = 0 if self._pressed else (dp(2) if self.kind in ("command", "system", "danger") else dp(1))
        if self._pressed:
            face_top = tuple(max(0, c * 0.75) if i < 3 else c for i, c in enumerate(face_top))
            face_bot = tuple(max(0, c * 0.75) if i < 3 else c for i, c in enumerate(face_bot))

        # Outer halo (bright keys only, stronger when pressed).
        luma = sum(self.glow_color[:3])
        halo_alpha = (0.50 if self._pressed else 0.30) if luma > 1.0 else 0
        self._halo_color.rgba = (*self.glow_color[:3], halo_alpha)
        spread = dp(10)
        self._halo.pos = (self.x - spread, self.y + offset - spread)
        self._halo.size = (self.width + 2 * spread, self.height - offset + 2 * spread)

        # Shadow base (under face).
        self._shadow_color.rgba = theme.SHADOW
        self._shadow.pos = (self.x, self.y)
        self._shadow.size = self.size

        # Face gradient.
        grad_tex = fx.gradient_texture(face_top, face_bot, height=32)
        self._face_color.rgba = (1, 1, 1, 1)
        self._face.texture = grad_tex
        self._face.pos = (self.x, self.y + offset)
        self._face.size = (self.width, max(1, self.height - offset))

        # Bevel: top highlight, bottom shadow (unless pressed, then reverse).
        if not self._pressed:
            self._bevel_light_color.rgba = theme.BEVEL_LIGHT
            self._bevel_light.pos = (self.x + dp(1), self.top - dp(1.5))
            self._bevel_light.size = (max(0, self.width - dp(2)), dp(1))
            self._bevel_dark_color.rgba = theme.BEVEL_DARK
            self._bevel_dark.pos = (self.x + dp(1), self.y + offset + dp(0.5))
            self._bevel_dark.size = (max(0, self.width - dp(2)), dp(1))
        else:
            self._bevel_light_color.rgba = theme.BEVEL_DARK
            self._bevel_light.pos = (self.x + dp(1), self.top - dp(1.5))
            self._bevel_light.size = (max(0, self.width - dp(2)), dp(1))
            self._bevel_dark_color.rgba = theme.BEVEL_LIGHT
            self._bevel_dark.pos = (self.x + dp(1), self.y + offset + dp(0.5))
            self._bevel_dark.size = (max(0, self.width - dp(2)), dp(1))

        # Edge outline.
        self._edge_color.rgba = edge
        self._edge.rectangle = (self.x, self.y + offset, self.width, max(1, self.height - offset))

        # Lamp strip glow (left edge).
        lamp_alpha = 0.65 if self._pressed else 0.40
        self._lamp_glow_color.rgba = (*self.glow_color[:3], lamp_alpha)
        lamp_spread = dp(6)
        self._lamp_glow.pos = (self.x + dp(2) - lamp_spread, self.y + offset + dp(4) - lamp_spread)
        self._lamp_glow.size = (dp(2) + 2 * lamp_spread, max(1, self.height - dp(8) - offset + 2 * lamp_spread))

        # Lamp solid.
        self._lamp_color.rgba = self.glow_color
        self._lamp.pos = (self.x + dp(2), self.y + dp(4) + offset)
        self._lamp.size = (dp(2), max(1, self.height - dp(8) - offset))
        if not appearance.enhanced:
            self._halo_color.a = 0
            self._lamp_glow_color.a = 0
            self._bevel_light_color.a = 0
            self._bevel_dark_color.a = 0
            self._shadow_color.rgba = theme.METAL_DARK
            offset = 0 if self._pressed else dp(2) if self.kind in ('command', 'system') else dp(1)
            self._face.texture = None
            self._face_color.rgba = {
                'command': (0.30, 0.095, 0.025, 1),
                'danger': (0.20, 0.035, 0.025, 1),
                'system': (0.025, 0.10, 0.14, 1),
            }.get(self.kind, theme.PANEL_RAISED)
            self._face.pos = self.x, self.y + offset
            self._face.size = self.width, max(0, self.height - offset)
            self._edge.rectangle = self.x, self.y + offset, self.width, max(0, self.height - offset)
            self._edge.width = dp(1)
            self._lamp.pos = self.x + dp(3), self.y + dp(4) + offset
            self._lamp.size = dp(2), max(0, self.height - dp(8) - offset)
        else:
            self._edge.width = dp(1.2)


class StatusLamp(Widget):
    """Rectangular hardware LED: solid bar plus soft outer glow halo, optional breathing."""

    color = ListProperty(theme.VFD_BLUE)
    _alpha = NumericProperty(1.0)

    def __init__(self, breathe=False, glow=True, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(12), dp(4)))
        super().__init__(**kwargs)
        self._glow = glow
        self._alpha = 1.0
        with self.canvas:
            # Outer glow halo (behind solid bar).
            self._halo_color = Color(1, 1, 1, 0)
            self._halo = BorderImage(pos=self.pos, size=self.size,
                                     texture=fx.ring_texture(spread=6),
                                     border=(dp(6), dp(6), dp(6), dp(6)))
            # Solid LED bar.
            self._color = Color(*self.color)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._draw, size=self._draw, color=self._draw, _alpha=self._draw)
        self._draw()
        appearance.bind(enhanced=self._draw)
        if breathe:
            self._breathe_down()

    def _draw(self, *_):
        # Halo: soft glow around bar.
        halo_alpha = self._alpha * 0.55 if self._glow and appearance.enhanced else 0
        self._halo_color.rgba = (*self.color[:3], halo_alpha)
        spread = dp(6)
        self._halo.pos = (self.x - spread, self.y - spread)
        self._halo.size = (self.width + 2 * spread, self.height + 2 * spread)

        # Solid bar.
        self._color.rgba = (*self.color[:3], self._alpha)
        self._rect.pos = self.pos
        self._rect.size = self.size

    def _breathe_down(self, *_):
        animation = Animation(_alpha=0.35, duration=1.1)
        animation.bind(on_complete=self._breathe_up)
        animation.start(self)

    def _breathe_up(self, *_):
        animation = Animation(_alpha=1.0, duration=1.1)
        animation.bind(on_complete=self._breathe_down)
        animation.start(self)

    def on_parent(self, _widget, parent):
        if parent is None:
            self.stop()

    def stop(self):
        Animation.cancel_all(self, "_alpha")


def machine_label(text, color=None, **kwargs):
    """Create a compact uppercase equipment label."""
    label = Label(text=text.upper(), color=color or theme.TEXT_MUTED,
                  font_size=dp(theme.FONT_CAPTION), halign="left", valign="middle", **kwargs)
    label.bind(size=label.setter("text_size"))
    return label
