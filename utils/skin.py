"""Global Button/TextInput/ScrollView skin via KV overlay.

Loaded once at app start (after Kivy's style.kv) to inject gradient faces,
bevel highlights, glow halos, and focus effects across all flat-styled widgets.

Transparent-background buttons (alpha=0) and buttons with atlas images
(background_normal set) remain unstyled. MechanicalButton and similar custom
widgets use alpha=0 so they keep their own drawing logic.
"""
from kivy.lang import Builder
from kivy.graphics import BorderImage
from utils import fx
from config import theme

# Language string loaded at app init (see main.py).
# Appends to stock <Button> rule, so BorderImage + text rendering stay intact.
# Canvas.after redraws face + text on top for gradient/bevel effect.

SKIN_KV = """
#:import fx utils.fx
#:import theme config.theme
#:import appearance utils.appearance.state

<Button>:
    canvas.after:
        # Halo glow (for bright keys, drawn behind face so center is covered).
        Color:
            rgba: (self.background_color[0], self.background_color[1], self.background_color[2], 0.5 if (appearance.enhanced and self.background_color[3] > 0.01 and not self.background_normal and sum(self.background_color[:3]) > 1.2 and self.state == 'down') else 0)
        BorderImage:
            pos: (self.x - dp(6), self.y - dp(6))
            size: (self.width + dp(12), self.height + dp(12))
            texture: fx.ring_texture(spread=8)
            border: (dp(8), dp(8), dp(8), dp(8))
        
        # Face gradient + bevel (only if background_normal is empty and alpha > 0).
        Color:
            rgba: (1, 1, 1, self.background_color[3] if (appearance.enhanced and self.background_color[3] > 0.01 and not self.background_normal) else 0)
        BorderImage:
            pos: self.pos
            size: self.size
            texture: fx.key_texture(self.background_color, pressed=(self.state == 'down'), disabled=self.disabled, border=2, size=16)
            border: (2, 2, 2, 2)
        
        # Redraw text on top (so it isn't covered by face).
        Color:
            rgba: (1, 1, 1, 1 if (appearance.enhanced and self.background_color[3] > 0.01 and not self.background_normal) else 0)
        Rectangle:
            texture: self.texture
            size: self.texture_size
            pos: (int(self.center_x - self.texture_size[0] / 2.), int(self.center_y - self.texture_size[1] / 2.))

<TextInput>:
    canvas.after:
        # Focus bar (left edge accent).
        Color:
            rgba: (theme.VFD_CYAN[0], theme.VFD_CYAN[1], theme.VFD_CYAN[2], 0.85 if appearance.enhanced and self.focus and not self.readonly else 0)
        Rectangle:
            pos: (self.x, self.y)
            size: (dp(2), self.height)
        
        # Outer edge line (cyan when focused, metal otherwise).
        Color:
            rgba: ((theme.VFD_CYAN if self.focus else theme.BORDER_DIM) if appearance.enhanced and not self.readonly and self.background_color[3] > 0 else (0, 0, 0, 0))
        Line:
            rectangle: (self.x, self.y, self.width, self.height)
            width: dp(1.2 if self.focus else 0.8)
        
        # Focus glow halo (outside bounds).
        Color:
            rgba: (theme.VFD_CYAN[0], theme.VFD_CYAN[1], theme.VFD_CYAN[2], 0.25 if appearance.enhanced and self.focus and not self.readonly else 0)
        BorderImage:
            pos: (self.x - dp(6), self.y - dp(6))
            size: (self.width + dp(12), self.height + dp(12))
            texture: fx.ring_texture(spread=8)
            border: (dp(8), dp(8), dp(8), dp(8))

<ScrollView>:
    bar_color: theme.VFD_CYAN[0], theme.VFD_CYAN[1], theme.VFD_CYAN[2], 0.45
    bar_width: dp(3) if appearance.enhanced else dp(2)
"""


_loaded = False


def load_skin():
    """Load KV skin overlay. Call once at app start after Window is created."""
    global _loaded
    if not _loaded:
        Builder.load_string(SKIN_KV)
        _loaded = True
