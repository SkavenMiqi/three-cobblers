"""Visual FX library: textures, gradients, glow, chamfered panels, scanlines.

Provides:
  - Texture generators (gradient, metal brush, scanlines, dot grid, glow ring, vignette)
  - Plate drawing primitive (chamfered titanium/glass panels with shadow/bevel/glow)
  - Button/key face textures (gradient + bevel, cached by color)
  - Chassis background helper (grid + vignette)
  - Tiled texture rectangle helper
  - LED segment glow helper

All textures are lazily created on first access and register reload observers
for Android GL context recovery. Plates rebuild their canvas on pos/size change
using in-place instruction updates where possible for scroll performance.
"""
import math
import array
from kivy.graphics import (Color, Rectangle, RoundedRectangle, Line, Mesh, Translate,
                           PushMatrix, PopMatrix, InstructionGroup)
from kivy.graphics.texture import Texture
from kivy.metrics import dp
from kivy.weakmethod import WeakMethod
from config import theme
from utils.appearance import state

# ---- Texture cache and reload registry ----
_TEX_CACHE = {}


def _make_texture(key, width, height, pixels_rgba, colorfmt='rgba', wrap='clamp_to_edge', mag='linear'):
    """Create or retrieve cached texture, register reload observer for GL context recovery."""
    if key in _TEX_CACHE:
        return _TEX_CACHE[key]
    tex = Texture.create(size=(width, height), colorfmt=colorfmt)
    tex.mag_filter = mag
    tex.min_filter = mag
    tex.wrap = wrap
    buf = array.array('B', pixels_rgba).tobytes()
    tex.blit_buffer(buf, colorfmt=colorfmt, bufferfmt='ubyte')
    # Register reload callback for Android pause/resume.
    def reload_texture(texture):
        texture.blit_buffer(buf, colorfmt=colorfmt, bufferfmt='ubyte')
    tex.add_reload_observer(reload_texture)
    _TEX_CACHE[key] = tex
    return tex


def _rgba_to_bytes(r, g, b, a):
    """Convert 0-1 float color to 0-255 bytes."""
    return (int(r * 255), int(g * 255), int(b * 255), int(a * 255))


# ---- Gradient textures ----

def gradient_texture(color_top, color_bottom, height=64):
    """Vertical gradient texture: v=0 (bottom row) → color_bottom, v=1 → color_top.
    
    Returns 1×height texture suitable for stretching across Rectangle.
    Kivy maps v=0 to bottom, so row 0 is the bottom color.
    """
    key = ('grad', tuple(round(c, 3) for c in color_top), 
           tuple(round(c, 3) for c in color_bottom), height)
    if key in _TEX_CACHE:
        return _TEX_CACHE[key]
    
    pixels = []
    for row in range(height):
        t = row / max(1, height - 1)
        r = color_bottom[0] + t * (color_top[0] - color_bottom[0])
        g = color_bottom[1] + t * (color_top[1] - color_bottom[1])
        b = color_bottom[2] + t * (color_top[2] - color_bottom[2])
        a = color_bottom[3] + t * (color_top[3] - color_bottom[3])
        pixels.extend(_rgba_to_bytes(r, g, b, a))
    
    return _make_texture(key, 1, height, pixels, wrap='clamp_to_edge')


# ---- Brushed metal texture ----

def brushed_metal_texture(size=128, alpha=0.08):
    """Horizontal-brushed metal noise: per-row random streaks, low alpha white over panel.
    
    Returns size×size tileable texture with horizontal grain.
    """
    key = ('metal', size, round(alpha, 3))
    if key in _TEX_CACHE:
        return _TEX_CACHE[key]
    
    import random
    rng = random.Random(42)  # Local RNG must not change application randomness.
    pixels = []
    for row in range(size):
        # Per-row noise from sum of sines with random phase.
        phase = rng.uniform(0, 2 * math.pi)
        base = 0.5 + 0.25 * math.sin(6 * math.pi * row / size + phase)
        for col in range(size):
            # Horizontal streaks: noise varies slowly with column.
            val = base + 0.15 * math.sin(2 * math.pi * col / size + phase)
            val = max(0, min(1, val))
            pixels.extend(_rgba_to_bytes(1, 1, 1, val * alpha))
    
    return _make_texture(key, size, size, pixels, wrap='repeat', mag='linear')


# ---- Scanlines texture ----

def scanlines_texture(line_height=4):
    """Horizontal scanlines: 1px lit white line every line_height rows, low alpha.
    
    Returns 1×line_height tileable texture for VFD/CRT glass shimmer.
    Size in dp for device-independent thickness.
    """
    key = ('scanlines', line_height)
    if key in _TEX_CACHE:
        return _TEX_CACHE[key]
    
    h = 4
    pixels = []
    for row in range(h):
        # Only first row is lit.
        a = theme.SCANLINE[3] if row == 0 else 0
        pixels.extend(_rgba_to_bytes(*theme.SCANLINE[:3], a))
    
    return _make_texture(key, 1, h, pixels, wrap='repeat', mag='linear')


# ---- Dot grid texture ----

def dot_grid_texture(spacing=32):
    """Engineering dot grid: small dot at origin of spacing×spacing tile.
    
    Returns spacing×spacing tileable texture for chassis background.
    """
    key = ('grid', spacing)
    if key in _TEX_CACHE:
        return _TEX_CACHE[key]
    
    s = 32
    pixels = []
    for row in range(s):
        for col in range(s):
            # 2×2 dot at origin.
            if row < 2 and col < 2:
                pixels.extend(_rgba_to_bytes(*theme.GRID_DOT))
            else:
                pixels.extend((0, 0, 0, 0))
    
    return _make_texture(key, s, s, pixels, wrap='repeat', mag='nearest')


# ---- Glow ring texture (9-patch BorderImage for halos) ----

def ring_texture(spread=12):
    """Hollow glow ring: transparent center, gaussian falloff outward from edge.
    
    Returns (spread*2)×(spread*2) texture with border=spread for BorderImage.
    Center stays transparent so glow only appears outside widget bounds.
    """
    key = ('ring', spread)
    if key in _TEX_CACHE:
        return _TEX_CACHE[key]
    
    s = max(2, int(spread))
    size = s * 2 + 2
    pixels = []
    for row in range(size):
        for col in range(size):
            # Distance from edge (negative inside, positive outside).
            dx = max(s - col, col - (s + 1), 0)
            dy = max(s - row, row - (s + 1), 0)
            dist = math.sqrt(dx * dx + dy * dy)
            # Gaussian falloff starting at edge.
            alpha = math.exp(-(dist * dist) / (s * s * 0.18))
            # Zero alpha inside (dist ≤ 0).
            if s <= col <= s + 1 and s <= row <= s + 1:
                alpha = 0
            pixels.extend(_rgba_to_bytes(1, 1, 1, alpha))
    
    return _make_texture(key, size, size, pixels, wrap='clamp_to_edge', mag='linear')


# ---- Vignette texture ----

def vignette_texture(size=128):
    """Radial darkening from center to edges for screen depth effect.
    
    Returns size×size texture: alpha 0 at center, increasing toward corners.
    """
    key = ('vignette', size)
    if key in _TEX_CACHE:
        return _TEX_CACHE[key]
    
    pixels = []
    center = (size - 1) / 2.0
    max_dist = math.sqrt(2) * center
    for row in range(size):
        for col in range(size):
            dx = col - center
            dy = row - center
            dist = math.sqrt(dx * dx + dy * dy)
            t = dist / max_dist
            # Smoothstep falloff.
            alpha = t * t * (3 - 2 * t) * 0.55
            pixels.extend(_rgba_to_bytes(0, 0, 0, alpha))
    
    return _make_texture(key, size, size, pixels, wrap='clamp_to_edge', mag='linear')


# ---- Button key face textures (9-patch with bevel) ----

_KEY_TEX_CACHE = {}
_KEY_TEX_MAX = 64


def key_texture(color, pressed=False, disabled=False, border=2, size=16):
    """Generate small 9-patch button face: gradient + bevel highlight/shadow.
    
    Args:
        color: (r, g, b, a) base background color
        pressed: invert gradient for pressed look
        disabled: desaturate and dim
        border: edge thickness for crisp bevel (default 2px)
        size: texture dimension (default 16×16)
    
    Returns texture suitable for BorderImage with border=border.
    Caches by rounded color to bound memory (max 64 entries).
    """
    key = (tuple(round(c, 2) for c in color), pressed, disabled, border, size)
    if key in _KEY_TEX_CACHE:
        return _KEY_TEX_CACHE[key]
    
    r, g, b, a = color
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    
    if disabled:
        # Desaturate toward gray, dim.
        gray = luma * 0.5
        r = r * 0.3 + gray * 0.7
        g = g * 0.3 + gray * 0.7
        b = b * 0.3 + gray * 0.7
        luma = gray
    
    # Gradient: lighten top, darken bottom (or reverse if pressed).
    if luma < 0.4:
        top_lift = 0.18 if not pressed else -0.08
        bot_drop = -0.08 if not pressed else 0.10
    else:
        top_lift = 0.10 if not pressed else -0.12
        bot_drop = -0.12 if not pressed else 0.08
    
    r_top = max(0, min(1, r + top_lift))
    g_top = max(0, min(1, g + top_lift))
    b_top = max(0, min(1, b + top_lift))
    r_bot = max(0, min(1, r + bot_drop))
    g_bot = max(0, min(1, g + bot_drop))
    b_bot = max(0, min(1, b + bot_drop))
    
    pixels = []
    for row in range(size):
        for col in range(size):
            # Bevel edges.
            if row >= size - border:
                # Top edge: highlight unless pressed.
                if not pressed:
                    pixels.extend(_rgba_to_bytes(1, 1, 1, 0.28 * a))
                else:
                    pixels.extend(_rgba_to_bytes(0, 0, 0, 0.35 * a))
            elif row < border:
                # Bottom edge: shadow unless pressed.
                if not pressed:
                    pixels.extend(_rgba_to_bytes(0, 0, 0, 0.35 * a))
                else:
                    pixels.extend(_rgba_to_bytes(1, 1, 1, 0.18 * a))
            elif col < border or col >= size - border:
                # Left/right edge: neutral.
                pixels.extend(_rgba_to_bytes(r, g, b, a))
            else:
                # Interior gradient.
                t = (row - border) / max(1, size - 2 * border - 1)
                rr = r_bot + t * (r_top - r_bot)
                gg = g_bot + t * (g_top - g_bot)
                bb = b_bot + t * (b_top - b_bot)
                pixels.extend(_rgba_to_bytes(rr, gg, bb, a))
    
    tex = _make_texture(('key', key), size, size, pixels, wrap='clamp_to_edge', mag='linear')
    _KEY_TEX_CACHE[key] = tex
    
    # Evict oldest if cache grows too large.
    if len(_KEY_TEX_CACHE) > _KEY_TEX_MAX:
        oldest = next(iter(_KEY_TEX_CACHE))
        del _KEY_TEX_CACHE[oldest]
        _TEX_CACHE.pop(('key', oldest), None)
    
    return tex


# ---- Chamfered polygon helper ----

def chamfered_rect_points(x, y, w, h, cut_tr=0, cut_bl=0):
    """Return counter-clockwise corner points for chamfered rectangle.
    
    Args:
        x, y, w, h: rectangle bounds
        cut_tr: top-right chamfer size (cuts corner diagonally)
        cut_bl: bottom-left chamfer size
    
    Returns list of (x, y) tuples starting at bottom-left, moving CCW.
    """
    points = []
    # Bottom-left corner (cut or square).
    if cut_bl > 0:
        points.append((x + cut_bl, y))
        points.append((x, y + cut_bl))
    else:
        points.append((x, y))
    
    # Top-left (always square).
    points.append((x, y + h))
    
    # Top-right (cut or square).
    if cut_tr > 0:
        points.append((x + w - cut_tr, y + h))
        points.append((x + w, y + h - cut_tr))
    else:
        points.append((x + w, y + h))
    
    # Bottom-right (always square).
    points.append((x + w, y))
    
    return points


def chamfered_mesh(x, y, w, h, cut_tr=0, cut_bl=0, texture=None):
    """Build triangle-fan Mesh for chamfered rectangle with optional gradient texture.
    
    Returns Mesh instruction. If texture provided, maps v coords from bottom (0) to top (1).
    """
    pts = chamfered_rect_points(x, y, w, h, cut_tr, cut_bl)
    n = len(pts)
    
    # Triangle fan: center vertex + perimeter.
    cx, cy = x + w / 2, y + h / 2
    vertices = []
    indices = []
    
    # Center vertex: u=0.5, v=0.5.
    vertices.extend([cx, cy, 0.5, 0.5])
    for i, (px, py) in enumerate(pts):
        u = (px - x) / max(1, w)
        v = (py - y) / max(1, h)
        vertices.extend([px, py, u, v])
        # Triangle: center, current, next.
        indices.extend([0, i + 1, (i + 1) % n + 1])
    
    mesh = Mesh(vertices=vertices, indices=indices, mode='triangles')
    if texture:
        mesh.texture = texture
    return mesh


# ---- Plate drawing primitive ----

class Plate:
    """Chamfered panel with shadow, gradient face, metal brush, bevel, edge line.
    
    Styles:
      - 'panel': titanium face, brushed overlay, raised bevel
      - 'glass': recessed smoked glass with scanlines, darker and inset
    
    Usage:
        plate = Plate(style='panel', accent_color=theme.VFD_CYAN)
        widget.canvas.before.add(plate.group)
        plate.update(widget.x, widget.y, widget.width, widget.height)
        widget.bind(pos=lambda *_: plate.update(...), size=lambda *_: plate.update(...))
    """
    
    def __init__(self, style='panel', accent_color=None, cut_tr=None, cut_bl=None,
                 bg=None, border=True):
        """
        Args:
            style: 'panel' (raised titanium) or 'glass' (recessed display)
            accent_color: optional (r,g,b,a) tint for glass or glow
            cut_tr, cut_bl: chamfer cuts in dp (default theme.CHAMFER)
        """
        self.style = style
        self.bg = bg
        self.border = border
        self.overlay = False
        state.bind(enhanced=self._theme_changed)
        self.accent = accent_color or theme.VFD_CYAN
        self.cut_tr = dp(cut_tr if cut_tr is not None else theme.CHAMFER)
        self.cut_bl = dp(cut_bl if cut_bl is not None else theme.CHAMFER)
        self.group = InstructionGroup()
        self._translation = None
        self._x = self._y = self._w = self._h = 0

    def _theme_changed(self, *_):
        bounds = self._x, self._y, self._w, self._h
        self._w = -1
        self.update(*bounds)
    
    def update(self, x, y, w, h):
        """Rebuild plate drawing at new position/size."""
        if (x, y, w, h) == (self._x, self._y, self._w, self._h):
            return
        if (w, h) == (self._w, self._h) and self._translation is not None:
            self._x, self._y = x, y
            self._translation.x, self._translation.y = x, y
            return
        self._x, self._y, self._w, self._h = x, y, w, h
        
        self.group.clear()
        if w <= 0 or h <= 0:
            return

        if not state.enhanced:
            if not self.overlay:
                self.group.add(Color(*(self.bg or theme.PANEL)))
                self.group.add(Rectangle(pos=(x, y), size=(w, h)))
                if self.border:
                    self.group.add(Color(*theme.BORDER))
                    self.group.add(Line(rectangle=(x, y, w, h), width=dp(1)))
                self.group.add(Color(*theme.METAL_LIGHT))
                self.group.add(Rectangle(pos=(x + dp(1), y + h - dp(2)),
                                         size=(max(0, w - dp(2)), dp(1))))
            self._translation = None
            return

        self.group.add(PushMatrix())
        self._translation = Translate(x, y)
        self.group.add(self._translation)
        x, y = 0, 0
        
        cut_tr = min(self.cut_tr, w / 2, h / 2)
        cut_bl = min(self.cut_bl, w / 2, h / 2)
        pts = chamfered_rect_points(x, y, w, h, cut_tr, cut_bl)
        if self.style == 'panel':
            self._draw_panel(x, y, w, h, cut_tr, cut_bl, pts)
        elif self.style == 'glass':
            self._draw_glass(x, y, w, h, cut_tr, cut_bl, pts)
        self.group.add(PopMatrix())
    
    def _draw_panel(self, x, y, w, h, cut_tr, cut_bl, pts):
        """Raised titanium panel: shadow, gradient face, brushed metal, bevel, edge."""
        g = self.group
        
        # 1. Soft drop shadow (offset down slightly).
        shadow_offset = dp(3)
        g.add(Color(*theme.SHADOW))
        g.add(chamfered_mesh(x, y - shadow_offset, w, h, cut_tr, cut_bl))
        
        # 2. Face gradient: PLATE_TOP at top, PLATE_BOTTOM at bottom.
        top = theme.PLATE_TOP if self.bg is None else tuple(
            min(1, c + 0.035) if i < 3 else c for i, c in enumerate(self.bg))
        bottom = theme.PLATE_BOTTOM if self.bg is None else self.bg
        grad_tex = gradient_texture(top, bottom, height=64)
        g.add(Color(1, 1, 1, 1))
        g.add(chamfered_mesh(x, y, w, h, cut_tr, cut_bl, texture=grad_tex))
        
        # 3. Brushed metal overlay (tiled, low alpha).
        metal_tex = brushed_metal_texture()
        metal_size = 128  # Texture size.
        g.add(Color(1, 1, 1, 1))
        g.add(chamfered_mesh(x, y, w, h, cut_tr, cut_bl, texture=metal_tex))

        if not self.border:
            return
        
        # 4. Outer edge line (metal color, slightly transparent).
        g.add(Color(*theme.PLATE_EDGE))
        edge_points = [coord for pt in pts for coord in pt]
        edge_points.extend(pts[0])  # Close loop.
        g.add(Line(points=edge_points, width=dp(1.2), cap='none', joint='miter'))
        
        # 5. Inner bevel: top-left highlight, bottom-right shadow.
        inset = dp(1.5)
        inner_pts = chamfered_rect_points(x + inset, y + inset, w - 2 * inset, h - 2 * inset, 
                                          max(0, cut_tr - inset), max(0, cut_bl - inset))
        # Top + left edges: highlight.
        if len(inner_pts) >= 3:
            highlight_pts = [coord for pt in inner_pts[:3] for coord in pt]
            g.add(Color(*theme.BEVEL_LIGHT))
            g.add(Line(points=highlight_pts, width=dp(1.0), cap='none'))
        
        # Bottom + right edges: shadow.
        if len(inner_pts) >= 5:
            shadow_pts = [coord for pt in inner_pts[2:] for coord in pt]
            g.add(Color(*theme.BEVEL_DARK))
            g.add(Line(points=shadow_pts, width=dp(1.0), cap='none'))

        # Short calibrated channel marker, rather than a full neon outline.
        g.add(Color(*self.accent[:3], 0.8))
        g.add(Line(points=(x + dp(12), y + h - dp(1),
                           x + min(w * 0.24, dp(48)), y + h - dp(1)), width=dp(1)))
    
    def _draw_glass(self, x, y, w, h, cut_tr, cut_bl, pts):
        """Recessed smoked glass: dark edges (inset look), glass gradient, scanlines."""
        g = self.group
        
        # 1. Recessed rim: dark top-left, lighter bottom-right (inverse bevel).
        inset = dp(2)
        inner_pts = chamfered_rect_points(x + inset, y + inset, w - 2 * inset, h - 2 * inset,
                                          max(0, cut_tr - inset), max(0, cut_bl - inset))
        # Outer edge: dark.
        g.add(Color(*theme.BEVEL_DARK))
        outer_edge = [coord for pt in pts for coord in pt]
        outer_edge.extend(pts[0])
        g.add(Line(points=outer_edge, width=dp(1.5), cap='none', joint='miter'))
        
        # 2. Inner glass face: gradient with accent tint at top.
        glass_top = (theme.GLASS_TOP[0] + self.accent[0] * 0.08,
                     theme.GLASS_TOP[1] + self.accent[1] * 0.08,
                     theme.GLASS_TOP[2] + self.accent[2] * 0.08, 1)
        grad_tex = gradient_texture(glass_top, theme.GLASS_BOTTOM, height=32)
        g.add(Color(1, 1, 1, 1))
        if len(inner_pts) > 2:
            g.add(chamfered_mesh(x + inset, y + inset, w - 2 * inset, h - 2 * inset,
                                 max(0, cut_tr - inset), max(0, cut_bl - inset), texture=grad_tex))
        
        # 3. Scanlines overlay (tiled).
        scan_tex = scanlines_texture()
        g.add(Color(1, 1, 1, 1))
        # Tile scanlines: repeat texture coordinates.
        tile_h = int(dp(4))
        repeats = max(1, int(h / tile_h))
        scan_rect = Rectangle(pos=(x + inset, y + inset), size=(w - 2 * inset, h - 2 * inset),
                              texture=scan_tex)
        scan_rect.tex_coords = (0, 0, 1, 0, 1, repeats, 0, repeats)
        g.add(scan_rect)
        
        # 4. Inner edge: subtle highlight.
        g.add(Color(*theme.GLASS_HIGHLIGHT))
        if len(inner_pts) > 0:
            inner_edge = [coord for pt in inner_pts for coord in pt]
            inner_edge.extend(inner_pts[0])
            g.add(Line(points=inner_edge, width=dp(0.8), cap='none', joint='miter'))


# ---- Chassis background helper ----

class Chassis:
    """Global chassis background: gradient + dot grid + vignette.
    
    Usage:
        chassis = Chassis()
        screen.canvas.before.add(chassis.group)
        chassis.update(screen.x, screen.y, screen.width, screen.height)
        screen.bind(pos=..., size=...)
    """
    
    def __init__(self):
        self.group = InstructionGroup()
        self._x = self._y = self._w = self._h = 0
        state.bind(enhanced=self._theme_changed)

    def _theme_changed(self, *_):
        bounds = self._x, self._y, self._w, self._h
        self._w = -1
        self.update(*bounds)
    
    def update(self, x, y, w, h):
        if (x, y, w, h) == (self._x, self._y, self._w, self._h):
            return
        self._x, self._y, self._w, self._h = x, y, w, h
        
        self.group.clear()
        if w <= 0 or h <= 0:
            return

        if not state.enhanced:
            self.group.add(Color(*theme.CHASSIS))
            self.group.add(Rectangle(pos=(x, y), size=(w, h)))
            return
        
        g = self.group
        
        # 1. Background gradient.
        grad_tex = gradient_texture(theme.CHASSIS_TOP, theme.CHASSIS_BOTTOM, height=64)
        g.add(Color(1, 1, 1, 1))
        grad_rect = Rectangle(pos=(x, y), size=(w, h), texture=grad_tex)
        g.add(grad_rect)

        grid_tex = dot_grid_texture(spacing=32)
        grid_size = int(dp(32))
        repeat_x = max(1, int(w / grid_size) + 1)
        repeat_y = max(1, int(h / grid_size) + 1)
        g.add(Color(1, 1, 1, 1))
        grid_rect = Rectangle(pos=(x, y), size=(w, h), texture=grid_tex)
        grid_rect.tex_coords = (0, 0, repeat_x, 0, repeat_x, repeat_y, 0, repeat_y)
        g.add(grid_rect)
        g.add(Color(1, 1, 1, 1))
        g.add(Rectangle(pos=(x, y), size=(w, h), texture=vignette_texture(size=128)))
        


# ---- LED segment glow helper ----

def draw_segment_glow(canvas_group, x, y, w, h, color, alpha=1.0, glow=True):
    """Draw LED segment: solid fill + optional outer glow halo.
    
    Args:
        canvas_group: InstructionGroup or canvas to add to
        x, y, w, h: segment rectangle
        color: (r, g, b, a) LED color
        alpha: master alpha multiplier
        glow: if True, add ring halo around segment
    """
    if glow and alpha > 0.1 and state.enhanced:
        spread = int(dp(theme.GLOW_SPREAD))
        ring_tex = ring_texture(spread=spread)
        canvas_group.add(Color(color[0], color[1], color[2], alpha * 0.6))
        from kivy.graphics import BorderImage
        canvas_group.add(BorderImage(pos=(x - spread, y - spread),
            size=(w + 2 * spread, h + 2 * spread), texture=ring_tex,
            border=(spread, spread, spread, spread)))
    # Solid segment face.
    canvas_group.add(Color(color[0], color[1], color[2], alpha))
    canvas_group.add(Rectangle(pos=(x, y), size=(w, h)))


# ---- Tiled texture rectangle helper ----

def tiled_rect(canvas_group, texture, x, y, w, h, tile_w, tile_h):
    """Draw rectangle with tiled texture using repeated tex_coords.
    
    Args:
        canvas_group: InstructionGroup or canvas
        texture: Kivy Texture with wrap='repeat'
        x, y, w, h: rectangle bounds
        tile_w, tile_h: size of one tile in pixels (for repeat calculation)
    """
    repeat_x = max(1, w / tile_w)
    repeat_y = max(1, h / tile_h)
    canvas_group.add(Color(1, 1, 1, 1))
    rect = Rectangle(pos=(x, y), size=(w, h), texture=texture)
    rect.tex_coords = (0, 0, repeat_x, 0, repeat_x, repeat_y, 0, repeat_y)
    canvas_group.add(rect)


def surface(widget, style='panel', accent=None, cut=7, bg=None, border=True):
    """Attach a visual surface without replacing children, handlers or layout."""
    plate = Plate(style=style, accent_color=accent, cut_tr=cut, cut_bl=cut,
                  bg=bg, border=border)
    plate.overlay = True
    widget.canvas.before.add(plate.group)

    def sync(*_):
        plate.update(widget.x, widget.y, widget.width, widget.height)

    widget.bind(pos=sync, size=sync)
    sync()
    return plate


def chassis(widget):
    """Attach a static engineering-grid backdrop, with no animation timer."""
    drawing = Chassis()
    widget.canvas.before.add(drawing.group)

    def sync(*_):
        drawing.update(widget.x, widget.y, widget.width, widget.height)

    widget.bind(pos=sync, size=sync)
    sync()
    return drawing
