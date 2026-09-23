"""
config.py — App-wide constants and default values.
"""
from __future__ import annotations

import math
from pathlib import Path

# Tool checkout root (passages_tool/), not src/passages_tool/.
TOOL_ROOT = Path(__file__).resolve().parents[2]
EDITOR_STATE_PATH = TOOL_ROOT / "editor_state.json"

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

GRID_CELL:        float = 1.0          # fallback if snap_grid is missing/zero
GRID_COLOR_MINOR: tuple = (0.25, 0.25, 0.30, 1.0)
GRID_COLOR_MAJOR: tuple = (0.40, 0.40, 0.50, 1.0)
GRID_MAJOR_EVERY: int   = 8            # every N cells gets the major line

# ── Viewport picking ──────────────────────────────────────────────────────────

PICK_RADIUS_PX: float = 12.0           # screen-space vertex/edge hit radius

# ── Bake camera ───────────────────────────────────────────────────────────────

CAMERA_NEAR: float = 0.1
CAMERA_FAR: float = 100.0
HEADLIGHT_ATTENUATION: tuple = (0.0, 0.0, 0.03)

# ── Polylines ─────────────────────────────────────────────────────────────────

POLYLINE_THICKNESS: float  = 2.0
POLYLINE_COLOR_DEFAULT     = (0.9, 0.8, 0.2, 1.0)   # yellow
POLYLINE_COLOR_SELECTED    = (0.2, 0.9, 0.4, 1.0)   # green
POLYLINE_COLOR_HOVER       = (1.0, 0.5, 0.1, 1.0)   # orange

VERTEX_HANDLE_RADIUS: float = 0.18    # world units
VERTEX_HANDLE_COLOR         = (1.0, 1.0, 1.0, 1.0)
VERTEX_HANDLE_SEL_COLOR     = (1.0, 1.0, 0.3, 1.0)   # bright yellow when polyline selected
VERTEX_HANDLE_ACTIVE_COLOR  = (1.0, 1.0, 1.0, 1.0)   # the picked vertex on that polyline

# ── Per-type polyline colours ─────────────────────────────────────────────────
# Wall: warm yellow; Arch: cyan; EyePath: spring green; Anchor: blue-violet.
# Selected variants are slightly brighter / more saturated.
# NOTE: anchor colour is kept clear of the red family so it never reads as the
# error-red (1.0, 0.2, 0.2) that the visibility validator paints on edge-on arches.

COLOR_WALL          = (0.91, 0.78, 0.25, 1.0)
COLOR_WALL_SELECTED = (1.00, 0.95, 0.40, 1.0)
COLOR_ARCH          = (0.25, 0.82, 0.91, 1.0)
COLOR_ARCH_SELECTED = (0.45, 0.97, 1.00, 1.0)
COLOR_EYEPATH       = (0.28, 0.91, 0.50, 1.0)
COLOR_EYEPATH_SEL   = (0.50, 1.00, 0.68, 1.0)
COLOR_ANCHOR        = (0.55, 0.45, 1.00, 1.0)   # blue-violet
COLOR_ANCHOR_SELECTED = (0.72, 0.64, 1.00, 1.0)

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

# Palette panel width in ImGui pixels (at UI scale 100%).
PALETTE_PANEL_W: int = 300

# Properties panel width in ImGui pixels (at UI scale 100%).
PROPS_PANEL_W: int = 320

# Editor overlay scale (Feature 12). Viewport world units are not scaled.
UI_SCALE_PRESETS: tuple[float, ...] = (1.0, 1.25, 1.5, 2.0)
UI_SCALE_MIN: float = 1.0
UI_SCALE_MAX: float = 2.0

# Thumbnail display size in the palette grid (the cached resolution is
# THUMBNAIL_W x THUMBNAIL_H; this is the displayed size per cell).
THUMBNAIL_DISPLAY_SIZE: int = 88

# Arch kind=volume (pilaster). Place Arch still defaults to a 4 m door;
# switching to Volume shrinks door-sized widths down to these.
VOLUME_DEFAULT_WIDTH_M: float = 0.55
VOLUME_DEFAULT_DEPTH_M: float = 0.45
VOLUME_DOOR_WIDTH_M: float = 2.5

# ── Level file ────────────────────────────────────────────────────────────────

LEVEL_FILE_VERSION: int = 2
LEVEL_FILE_EXT: str     = ".passages.json"


# ── Level & Camera Defaults ───────────────────────────────────────────────────

DEFAULT_WALL_HEIGHT: float      = 4.0      # world units; also ceiling height
DEFAULT_EYE_HEIGHT: float       = 1.7      # camera height above floor (world units)
DEFAULT_FOV_H: float            = 91.5     # derived default: 60° VFOV at 1024×576
DEFAULT_FOV_V: float            = 60.0     # vertical field of view (degrees); HFOV is derived


def derived_fov_h(fov_v_deg: float, width: int, height: int) -> float:
    """Horizontal FOV implied by vertical FOV and render aspect ratio.

    Matches the baker lens: ``2 * atan(aspect * tan(fov_v / 2))``.
    ``fov_h`` is not independently authored.
    """
    aspect = float(width) / float(max(1, height))
    return 2.0 * math.degrees(
        math.atan(aspect * math.tan(math.radians(fov_v_deg * 0.5)))
    )
DEFAULT_PIXELS_PER_METER: float = 256.0    # texture pixels per world meter
DEFAULT_FOG_START: float        = 20.0     # distance where fog begins
DEFAULT_FOG_END: float          = 40.0     # distance where fog becomes fully opaque
DEFAULT_SNAP_GRID: float        = 0.25     # default snap grid size (world units)
DEFAULT_RENDER_WIDTH: int       = 1024     # default width for baked images (pixels)
DEFAULT_RENDER_HEIGHT: int      = 576      # default height for baked images (pixels)


