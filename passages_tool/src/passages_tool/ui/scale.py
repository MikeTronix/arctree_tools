"""Editor UI scale (Feature 12).

Dear ImGui 1.92 (imgui-bundle) dropped ``io.font_global_scale``. The live
equivalents are ``style.font_scale_main`` (fonts) and ``style.scale_all_sizes``
(padding / widget chrome). Viewport world units are not scaled here.
"""
from __future__ import annotations

import sys
from typing import Any, Optional

from passages_tool.config import (
    PALETTE_PANEL_W,
    PROPS_PANEL_W,
    UI_SCALE_MAX,
    UI_SCALE_MIN,
    UI_SCALE_PRESETS,
)

_DPI_REFERENCE = 96.0


def clamp_ui_scale(value: float) -> float:
    return max(UI_SCALE_MIN, min(UI_SCALE_MAX, float(value)))


def snap_ui_scale_preset(value: float) -> float:
    """Nearest of 100/125/150/200%. Ties prefer the larger preset."""
    clamped = clamp_ui_scale(value)
    return min(UI_SCALE_PRESETS, key=lambda p: (abs(p - clamped), -p))


def ui_scale_from_state(state: object) -> Optional[float]:
    """Return a clamped scale if ``editor_state.json`` stored one, else None."""
    if not isinstance(state, dict):
        return None
    raw = state.get("ui_scale")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return clamp_ui_scale(float(raw))


def _windows_dpi() -> Optional[int]:
    if sys.platform != "win32":
        return None
    try:
        dpi = int(ctypes_get_dpi_for_system())
    except Exception:
        dpi = 0
    return dpi if dpi > 0 else None


def ctypes_get_dpi_for_system() -> int:
    """Windows 10+ system DPI. Split out so tests can monkeypatch."""
    import ctypes

    return int(ctypes.windll.user32.GetDpiForSystem())


def detect_os_ui_scale() -> float:
    """Physical scale from OS DPI, or 1.0 if unknown. Not snapped to presets."""
    dpi = _windows_dpi()
    if dpi is None:
        return 1.0
    return dpi / _DPI_REFERENCE


def resolve_ui_scale(state: object) -> float:
    saved = ui_scale_from_state(state)
    if saved is not None:
        return saved
    return snap_ui_scale_preset(detect_os_ui_scale())


def style_sizes_scale_factor(target: float, applied: float) -> Optional[float]:
    """Relative factor for ``style.scale_all_sizes``. None = no change.

    ``scale_all_sizes`` is multiplicative; never call it with the absolute
    scale on every frame.
    """
    t = clamp_ui_scale(target)
    a = applied if applied > 1e-6 else 1.0
    if abs(t - a) < 1e-6:
        return None
    return t / a


def apply_imgui_ui_scale(style: Any, *, target: float, applied: float) -> float:
    """Set font scale and, if needed, resize style padding. Returns applied."""
    target = clamp_ui_scale(target)
    if hasattr(style, "font_scale_main"):
        style.font_scale_main = target
    factor = style_sizes_scale_factor(target, applied)
    if factor is not None:
        style.scale_all_sizes(factor)
    return target


def overlay_top_px(imgui: Any, scale: float) -> float:
    """Y of side panels: just below the main menu bar."""
    try:
        h = float(imgui.get_frame_height())
        if h > 1.0:
            return h
    except Exception:
        pass
    return 20.0 * clamp_ui_scale(scale)


def scaled_px(base: float, scale: float) -> float:
    return float(base) * clamp_ui_scale(scale)


def overlay_layout(
    display_w: float,
    display_h: float,
    ui_scale: float,
    menu_bar_h: float,
) -> tuple[float, float, float, float]:
    """Menu-bar height, palette width, properties width, side-panel height.

    Side panels keep their scaled width until they would overflow the window.
    """
    dw = max(1.0, float(display_w))
    dh = max(1.0, float(display_h))
    scale = clamp_ui_scale(ui_scale)
    if float(menu_bar_h) > 1.0:
        bar_h = float(menu_bar_h)
    else:
        bar_h = 20.0 * scale
    pal = scaled_px(PALETTE_PANEL_W, scale)
    props = scaled_px(PROPS_PANEL_W, scale)
    budget = max(1.0, dw * 0.85)
    total = pal + props
    if total > budget:
        f = budget / total
        pal *= f
        props *= f
    panel_h = max(64.0, dh - bar_h)
    return bar_h, pal, props, panel_h


def pixel2d_scale(win_w: int, win_h: int) -> tuple[float, float, float]:
    """Panda ``pixel2d`` scale so 1 unit is 1 framebuffer pixel."""
    w = max(1, int(win_w))
    h = max(1, int(win_h))
    return (2.0 / w, 1.0, 2.0 / h)
