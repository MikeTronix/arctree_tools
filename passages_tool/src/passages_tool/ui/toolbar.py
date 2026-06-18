"""
ui/toolbar.py
─────────────
Dear ImGui top menu bar.

Tool modes
──────────
  SELECT        — click/drag vertex handles; click empty to deselect
  DRAW_WALL     — left-click adds Wall vertices; Enter/RMB finishes + auto-selects (W key)
  DRAW_ARCH     — single left-click places Arch + auto-selects            (A key)
  DRAW_EYEPATH  — left-click adds EyePath vertices; Enter/RMB finishes    (E key)

Active tool is highlighted in its type-matching colour so it's obvious at a glance.
"""
from __future__ import annotations

from enum import Enum, auto
from typing import Callable


class ToolMode(Enum):
    SELECT       = auto()
    DRAW_WALL    = auto()
    DRAW_ARCH    = auto()
    DRAW_EYEPATH = auto()


# Colour shown in the menu bar for each active draw mode (matches Phase-2 colours).
_MODE_COLORS = {
    ToolMode.SELECT:       (1.00, 1.00, 1.00, 1.0),   # white
    ToolMode.DRAW_WALL:    (1.00, 0.92, 0.35, 1.0),   # warm yellow
    ToolMode.DRAW_ARCH:    (0.35, 0.95, 1.00, 1.0),   # cyan
    ToolMode.DRAW_EYEPATH: (0.40, 1.00, 0.60, 1.0),   # spring green
}


class Toolbar:
    def __init__(self, callbacks: dict[str, Callable]) -> None:
        self._cb = callbacks

    def draw(
        self,
        current_tool: ToolMode,
        can_undo: bool,
        can_redo: bool,
        is_dirty: bool,
        snap_enabled: bool,
        snap_grid: float,
    ) -> None:
        """Render the top menu bar. Must be called inside an imgui frame."""
        try:
            from imgui_bundle import imgui
        except ImportError:
            return

        if not imgui.begin_main_menu_bar():
            return

        # ── File menu ─────────────────────────────────────────────────────────
        if imgui.begin_menu("File"):
            activated, _ = imgui.menu_item("New",   "Ctrl+N", False)
            if activated:
                self._cb.get("new", lambda: None)()

            activated, _ = imgui.menu_item("Open…", "Ctrl+O", False)
            if activated:
                self._cb.get("open", lambda: None)()

            label = "Save *" if is_dirty else "Save"
            activated, _ = imgui.menu_item(label,   "Ctrl+S", False)
            if activated:
                self._cb.get("save", lambda: None)()

            imgui.separator()
            activated, _ = imgui.menu_item("Exit", "Alt+F4", False)
            if activated:
                self._cb.get("exit", lambda: None)()

            imgui.end_menu()

        # ── Edit menu ─────────────────────────────────────────────────────────
        if imgui.begin_menu("Edit"):
            activated, _ = imgui.menu_item("Undo", "Ctrl+Z", False, can_undo)
            if activated:
                self._cb.get("undo", lambda: None)()

            activated, _ = imgui.menu_item("Redo", "Ctrl+Y", False, can_redo)
            if activated:
                self._cb.get("redo", lambda: None)()

            imgui.end_menu()

        # ── Tool buttons (inline in menu bar, colour-coded) ───────────────────
        imgui.separator()

        _tools = [
            (ToolMode.SELECT,       "Select",       "S"),
            (ToolMode.DRAW_WALL,    "Draw Wall",    "W"),
            (ToolMode.DRAW_ARCH,    "Place Arch",   "A"),
            (ToolMode.DRAW_EYEPATH, "Draw EyePath", "E"),
        ]

        for mode, label, shortcut in _tools:
            is_active = current_tool == mode
            color     = _MODE_COLORS[mode]

            # Tint text colour and the header (hover/selected) background.
            if is_active:
                imgui.push_style_color(imgui.Col_.text.value,   color)
                imgui.push_style_color(
                    imgui.Col_.header.value,
                    (color[0]*0.35, color[1]*0.35, color[2]*0.35, 0.9),
                )

            activated, _ = imgui.menu_item(
                f"[{label}]" if is_active else label,
                shortcut,
                is_active,
            )

            if is_active:
                imgui.pop_style_color(2)

            if activated:
                self._cb.get("set_tool", lambda t: None)(mode)

        # ── Snap Grid toggle / status ─────────────────────────────────────────
        imgui.separator()
        snap_label = f"Snap: ON ({snap_grid:.3f})" if snap_enabled else f"Snap: OFF ({snap_grid:.3f})"
        if snap_enabled:
            imgui.push_style_color(imgui.Col_.text.value, (0.50, 1.00, 0.68, 1.0)) # light green
        activated, _ = imgui.menu_item(snap_label, "G", snap_enabled)
        if snap_enabled:
            imgui.pop_style_color()
        if activated:
            self._cb.get("toggle_snap", lambda: None)()

        # ── Validate Level ────────────────────────────────────────────────────
        imgui.separator()
        activated_val, _ = imgui.menu_item("Validate", "V", False)
        if activated_val:
            self._cb.get("run_validation", lambda: None)()


        # ── FPS counter (right-aligned) ────────────────────────────────────────
        fps      = imgui.get_io().framerate
        fps_text = f"{fps:.0f} fps"
        fps_w    = imgui.calc_text_size(fps_text).x
        bar_w    = imgui.get_io().display_size.x
        imgui.set_cursor_pos_x(bar_w - fps_w - 8)
        imgui.text_disabled(fps_text)

        imgui.end_main_menu_bar()
