"""
config.py — App-wide constants and default values.
"""
from __future__ import annotations

# ── Window ────────────────────────────────────────────────────────────────────

WINDOW_TITLE = "Passages Level Editor"
WINDOW_W     = 1440
WINDOW_H     = 900

# ── Viewport ──────────────────────────────────────────────────────────────────

# World units visible along the horizontal axis at default zoom.
VIEWPORT_DEFAULT_FILM_W: float = 30.0

# Zoom limits (world-unit film width).
ZOOM_MIN: float = 2.0
ZOOM_MAX: float = 200.0

# Fraction of film width added/removed per scroll click.
ZOOM_STEP: float = 0.10

# ── Grid ──────────────────────────────────────────────────────────────────────

GRID_CELL:        float = 1.0          # world-unit cell size
GRID_COLOR_MINOR: tuple = (0.25, 0.25, 0.30, 1.0)
GRID_COLOR_MAJOR: tuple = (0.40, 0.40, 0.50, 1.0)
GRID_MAJOR_EVERY: int   = 8            # every N cells gets the major line

# ── Polylines ─────────────────────────────────────────────────────────────────

POLYLINE_THICKNESS: float  = 2.0
POLYLINE_COLOR_DEFAULT     = (0.9, 0.8, 0.2, 1.0)   # yellow
POLYLINE_COLOR_SELECTED    = (0.2, 0.9, 0.4, 1.0)   # green
POLYLINE_COLOR_HOVER       = (1.0, 0.5, 0.1, 1.0)   # orange

VERTEX_HANDLE_RADIUS: float = 0.18    # world units
VERTEX_HANDLE_COLOR         = (1.0, 1.0, 1.0, 1.0)
VERTEX_HANDLE_SEL_COLOR     = (1.0, 1.0, 0.3, 1.0)   # bright yellow when selected

# ── Per-type polyline colours ─────────────────────────────────────────────────
# Wall: warm yellow; Arch: cyan; EyePath: spring green
# Selected variants are slightly brighter / more saturated.

COLOR_WALL          = (0.91, 0.78, 0.25, 1.0)
COLOR_WALL_SELECTED = (1.00, 0.95, 0.40, 1.0)
COLOR_ARCH          = (0.25, 0.82, 0.91, 1.0)
COLOR_ARCH_SELECTED = (0.45, 0.97, 1.00, 1.0)
COLOR_EYEPATH       = (0.28, 0.91, 0.50, 1.0)
COLOR_EYEPATH_SEL   = (0.50, 1.00, 0.68, 1.0)

# ── Wall interior-side hatch ticks ────────────────────────────────────────────

# Length of each exterior hatch tick, in world units.
HATCH_LENGTH:  float = 0.30
# Minimum edge length below which no hatch is drawn.
HATCH_MIN_EDGE: float = 0.05

# ── EyePath arrowheads ────────────────────────────────────────────────────────

ARROW_HEAD_SIZE: float = 0.28   # length of each wing in world units

# ── Wall texture-interval colour cycling ────────────────────────────────────────────
# Applied in sequence to adjacent intervals so they are visually distinguishable.
# Intentionally softer / lower-saturation than the type colours above.

INTERVAL_COLORS: list = [
    (0.45, 0.65, 0.95, 1.0),  # soft blue
    (0.95, 0.68, 0.30, 1.0),  # soft amber
    (0.72, 0.40, 0.88, 1.0),  # soft purple
    (0.30, 0.88, 0.78, 1.0),  # soft teal
]
# Edges not covered by any interval when at least one interval is defined.
COLOR_WALL_NO_INTERVAL = (0.45, 0.45, 0.45, 0.80)  # dim grey

# ── Textures / Palette ────────────────────────────────────────────────────────

THUMBNAIL_W: int = 96
THUMBNAIL_H: int = 96

# Palette panel width in ImGui pixels.
PALETTE_PANEL_W: int = 300

# Properties panel width in ImGui pixels.
PROPS_PANEL_W: int = 320

# Thumbnail display size in the palette grid (the cached resolution is
# THUMBNAIL_W x THUMBNAIL_H; this is the displayed size per cell).
THUMBNAIL_DISPLAY_SIZE: int = 88

# ── Level file ────────────────────────────────────────────────────────────────

LEVEL_FILE_VERSION: int = 2
LEVEL_FILE_EXT: str     = ".passages.json"


# ── Level & Camera Defaults ───────────────────────────────────────────────────

DEFAULT_WALL_HEIGHT: float      = 4.0      # world units; also ceiling height
DEFAULT_EYE_HEIGHT: float       = 1.7      # camera height above floor (world units)
DEFAULT_FOV_H: float            = 90.0     # horizontal field of view (degrees)
DEFAULT_FOV_V: float            = 60.0     # vertical field of view (degrees)
DEFAULT_PIXELS_PER_METER: float = 256.0    # texture pixels per world meter
DEFAULT_FOG_START: float        = 20.0     # distance where fog begins
DEFAULT_FOG_END: float          = 40.0     # distance where fog becomes fully opaque
DEFAULT_SNAP_GRID: float        = 0.25     # default snap grid size (world units)
DEFAULT_RENDER_WIDTH: int       = 1024     # default width for baked images (pixels)
DEFAULT_RENDER_HEIGHT: int      = 768      # default height for baked images (pixels)


