# Y2K Japanese Hi-Fi instrument system. Values are RGBA in 0..1.
CHASSIS = (0.020, 0.022, 0.024, 1)
PANEL = (0.047, 0.051, 0.055, 1)
PANEL_RAISED = (0.075, 0.080, 0.086, 1)
DISPLAY_GLASS = (0.010, 0.018, 0.019, 1)
DISPLAY_OFF = (0.018, 0.028, 0.028, 1)

METAL_DARK = (0.105, 0.112, 0.118, 1)
METAL = (0.36, 0.38, 0.39, 1)
METAL_LIGHT = (0.68, 0.70, 0.70, 1)
GLASS_HIGHLIGHT = (0.58, 0.68, 0.68, 0.12)

VFD_ORANGE = (1.0, 0.333, 0.0, 1)
VFD_ORANGE_DIM = (0.42, 0.11, 0.0, 1)
VFD_CYAN = (0.0, 1.0, 0.80, 1)
VFD_CYAN_DIM = (0.0, 0.28, 0.23, 1)
VFD_BLUE = (0.20, 0.80, 1.0, 1)
VFD_BLUE_DIM = (0.035, 0.24, 0.34, 1)
LED_RED = (1.0, 0.20, 0.06, 1)
LED_GREEN = (0.12, 0.88, 0.42, 1)

BG = CHASSIS
SURFACE = PANEL
SURFACE_LIGHT = PANEL_RAISED
SURFACE_HIGH = (0.10, 0.105, 0.11, 1)
BORDER = METAL
BORDER_DIM = METAL_DARK
HAIRLINE = (0.38, 0.40, 0.41, 0.45)

# Compatibility aliases retain behavior while mapping old semantic colors to VFD hardware.
GOLD = VFD_ORANGE
GOLD_DARK = VFD_ORANGE_DIM
CYAN = VFD_CYAN
ACCENT_CYAN = VFD_CYAN
LINK_BLUE = VFD_BLUE_DIM

ACCENT = GOLD
STRENGTH_ORANGE = (1.0, 0.55, 0.05, 1)
CARDIO_BLUE = CYAN
ACCENT_DIM = GOLD_DARK

TEXT_PRIMARY = (0.90, 0.91, 0.90, 1)
TEXT_SECONDARY = (0.66, 0.68, 0.67, 1)
TEXT_MUTED = (0.40, 0.42, 0.42, 1)

DANGER = LED_RED
OVERLAY = (0, 0, 0, 0.7)

TODAY_RING = METAL

# Compact machine typography (dp)
FONT_H1 = 22
FONT_H2 = 16
FONT_H3 = 14
FONT_BODY = 14
FONT_CAPTION = 12
FONT_LABEL = 12

# Precision module geometry
CARD_RADIUS = 2
CONTROL_RADIUS = 2
CARD_PADDING = 12
CARD_SPACING = 7
PAGE_MARGIN = 8
MODULE_HEADER = 18

# ---- V3 light & depth tokens (used by utils/fx.py) ----
# Chassis gradient: faint cool lift at top, deep at bottom.
CHASSIS_TOP = (0.040, 0.046, 0.052, 1)
CHASSIS_BOTTOM = (0.012, 0.013, 0.015, 1)
GRID_DOT = (0.30, 0.55, 0.60, 0.10)
# Titanium plate face gradient.
PLATE_TOP = (0.085, 0.092, 0.100, 1)
PLATE_BOTTOM = (0.040, 0.044, 0.048, 1)
PLATE_EDGE = (0.30, 0.33, 0.35, 0.85)
BEVEL_LIGHT = (0.85, 0.90, 0.92, 0.22)
BEVEL_DARK = (0.0, 0.0, 0.0, 0.55)
SHADOW = (0, 0, 0, 0.55)
# Smoked glass.
GLASS_TOP = (0.020, 0.040, 0.044, 1)
GLASS_BOTTOM = (0.006, 0.010, 0.011, 1)
SCANLINE = (0.55, 0.90, 0.95, 0.035)
# Chamfer cut size for sci-fi corners (dp).
CHAMFER = 9
GLOW_SPREAD = 10
