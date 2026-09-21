"""
main.py
───────
Passages Level Editor — application shell.

PassagesApp (ShowBase) mixes in:
  InputMixin     — mouse/keyboard, draw, pick
  CommandsMixin  — file, undo, properties callbacks
  PreviewMixin   — in-editor 3D viewpoint peek
"""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from typing import Optional

from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    WindowProperties,
    loadPrcFileData,
)

from passages_tool.app.commands import CommandsMixin
from passages_tool.app.input import InputMixin
from passages_tool.app.preview import PreviewMixin
from passages_tool.config import (
    EDITOR_STATE_PATH,
    TOOL_ROOT,
    WINDOW_H,
    WINDOW_TITLE,
    WINDOW_W,
)
from passages_tool.editor.history import History
from passages_tool.editor.level import Level
from passages_tool.editor.polyline import PolylineManager
from passages_tool.log import configure_editor, get_logger
from passages_tool.textures.manager import TextureManager
from passages_tool.ui.palette import TexturePalette
from passages_tool.ui.properties import PropertiesPanel
from passages_tool.ui.scale import (
    apply_imgui_ui_scale,
    clamp_ui_scale,
    resolve_ui_scale,
    scaled_px,
)
from passages_tool.ui.toolbar import ToolMode, Toolbar
from passages_tool.viewport.camera import ViewportCamera
from passages_tool.viewport.grid import BackgroundGrid

log = get_logger("main")

# ── Panda3D config (must be set before ShowBase.__init__) ────────────────────
loadPrcFileData("", f"window-title {WINDOW_TITLE}")
loadPrcFileData("", f"win-size {WINDOW_W} {WINDOW_H}")
loadPrcFileData("", "sync-video false")
loadPrcFileData("", "show-frame-rate-meter false")
loadPrcFileData("", "notify-level warning")


class PassagesApp(InputMixin, CommandsMixin, PreviewMixin, ShowBase):
    def __init__(self) -> None:
        super().__init__()

        self._level    = Level()
        self._history  = History(max_size=100)
        self._tool     = ToolMode.SELECT
        self._active_polyline_id: Optional[str] = None
        self._drag_pid: Optional[str]  = None
        self._drag_idx: Optional[int]  = None
        self._drag_last: tuple[float, float] = (0.0, 0.0)
        self._file_path: Optional[Path] = None
        self._panning  = False
        self._pan_last: tuple[float, float] = (0.0, 0.0)
        self._snap_enabled = False
        self._arch_snap_pending = False
        self._pending_arch_id: Optional[str] = None
        self._validation_warnings: list = []
        self._saved_snapshot: dict = self._level.to_dict()
        self._history_edit_key: Optional[str] = None

        self.setBackgroundColor(0.12, 0.12, 0.15, 1.0)

        self._cam   = ViewportCamera(self, WINDOW_W, WINDOW_H)
        self._grid  = BackgroundGrid(self.render)
        self._pm    = PolylineManager(self.render)
        self._pm.level = self._level
        self._tex   = TextureManager()
        editor_state = self._load_editor_state()
        self._ui_scale = resolve_ui_scale(editor_state)
        self._imgui_scale_applied = 1.0
        self._restore_texture_dir(editor_state)

        self._rebuild_grid()
        self._refresh_title()

        self._imgui_active = False
        self._init_imgui()

        self._toolbar = Toolbar(callbacks={
            "new":      self.cmd_new,
            "open":     self.cmd_open,
            "save":     self.cmd_save,
            "save_as":  self._cmd_save_as,
            "undo":     self.cmd_undo,
            "redo":     self.cmd_redo,
            "set_tool": self.set_tool,
            "toggle_snap": self._toggle_snap,
            "run_validation": self._run_validation,
            "exit":     self.cmd_exit,
            "set_ui_scale": self._set_ui_scale,
        })
        self._palette = TexturePalette(
            self._tex,
            callbacks={"browse": self.cmd_browse_textures},
        )
        self._props = PropertiesPanel(callbacks={
            "set_closed":              self._cb_set_closed,
            "set_texture":             self._cb_set_texture,
            "set_type":                self._cb_set_type,
            "set_field":               self._cb_set_field,
            "move_vertex":             self._cb_move_vertex,
            "del_vertex":              self._cb_del_vertex,
            "insert_vertex":           self._cb_insert_vertex,
            "del_polyline":            self._cb_del_polyline,
            "set_interval_texture":    self._cb_set_interval_texture,
            "set_interval_x_offset":   self._cb_set_interval_x_offset,
            "add_texture_interval":    self._cb_add_texture_interval,
            "remove_texture_interval": self._cb_remove_texture_interval,
            "split_texture_interval":  self._cb_split_texture_interval,
            "add_eyepath_edge":        self._cb_add_eyepath_edge,
            "remove_eyepath_edge":     self._cb_remove_eyepath_edge,
            "set_meta_field":          self._cb_set_meta_field,
            "list_styles":             self._cb_list_styles,
            "render_preview":          self._cb_render_preview,
        })

        self._init_input()
        if self.win is not None:
            self.win.setCloseRequestEvent("passages-close")
        self.accept("passages-close", self.cmd_exit)
        self.accept("window-event", self._on_window_event)

        self.taskMgr.add(self._update, "passages_update")

        self._tk_root = tk.Tk()
        self._tk_root.withdraw()

    def _init_imgui(self) -> None:
        """
        Set up p3dimgui (panda3d-imgui).

        p3dimgui.init() registers two Panda3D tasks:
          sort=0  -> imgui-new-frame     (calls imgui.new_frame())
          sort=40 -> imgui-render-frame  (calls imgui.render())

        Our UI drawing task runs at sort=10, between those two.
        """
        try:
            import p3dimgui
            p3dimgui.init(
                style='dark',
                wantPlaceManager=False,
                wantExplorerManager=False,
                wantTimeSliderManager=False,
            )
            self._imgui_scale_applied = 1.0
            self._apply_imgui_ui_scale()
            # Before p3dimgui's new_frame (sort=0) so font_scale_main is in effect.
            self.taskMgr.add(self._ui_scale_task, "passages_ui_scale", sort=-1)
            self.taskMgr.add(self._imgui_frame, "passages_imgui_ui", sort=10)
            self._imgui_active = True
        except Exception:
            log.exception(
                "p3dimgui not available. UI panels will be unavailable. "
                "Run: pip install panda3d-imgui"
            )
            self._imgui_active = False

    def _imgui_frame(self, task):
        """Draw all ImGui panels (runs at task sort=10)."""
        try:
            sel_pl = self._get_selected_polyline()
            self._toolbar.draw(
                current_tool = self._tool,
                can_undo     = self._history.can_undo(),
                can_redo     = self._history.can_redo(),
                is_dirty     = self._level.dirty,
                snap_enabled = self._snap_enabled,
                snap_grid    = self._level.meta.snap_grid,
                ui_scale     = self._ui_scale,
            )
            self._palette.draw(self._ui_scale)
            self._props.draw(sel_pl, self._palette.selected_name, self._level, self._ui_scale)
            self._refresh_title()

            if self._arch_snap_pending:
                from imgui_bundle import imgui
                display_size = imgui.get_io().display_size
                dlg_w = scaled_px(360, self._ui_scale)
                dlg_h = scaled_px(80, self._ui_scale)
                imgui.set_next_window_pos(
                    (display_size.x / 2 - dlg_w / 2, scaled_px(50, self._ui_scale)),
                    imgui.Cond_.always.value,
                )
                imgui.set_next_window_size((dlg_w, dlg_h), imgui.Cond_.always.value)
                imgui.begin("Arch Alignment Snap", None,
                            imgui.WindowFlags_.no_title_bar.value |
                            imgui.WindowFlags_.no_resize.value |
                            imgui.WindowFlags_.no_move.value)
                imgui.text_colored((1.0, 0.8, 0.2, 1.0), "Offer Wall-Perpendicular Snap")
                imgui.text("Press Enter to snap perpendicular, Esc (or click) to keep billboard.")
                imgui.end()

            if self._validation_warnings:
                from imgui_bundle import imgui
                imgui.set_next_window_size(
                    (scaled_px(400, self._ui_scale), scaled_px(200, self._ui_scale)),
                    imgui.Cond_.first_use_ever.value,
                )
                expanded, opened = imgui.begin("Validation Warnings", True)
                if not opened:
                    self._validation_warnings = []
                    self._rebuild_all_highlights()
                else:
                    if imgui.button("Clear / Dismiss"):
                        self._validation_warnings = []
                        self._rebuild_all_highlights()
                    else:
                        imgui.separator()
                        for i, w in enumerate(self._validation_warnings):
                            if w.arch_id:
                                if imgui.small_button(f"Select##vw{i}"):
                                    self._focus_polyline(w.arch_id)
                                imgui.same_line()
                            imgui.text_wrapped(w.message)
                            imgui.separator()
                imgui.end()
        except Exception:
            log.exception("ImGui frame failed")
        return task.cont

    def _rebuild_grid(self) -> None:
        fw = self._cam.film_w
        fh = self._cam.film_h
        cx = self._cam._cam_x
        cz = self._cam._cam_z
        self._grid.rebuild(fw, fh, cx, cz, cell=self._level.meta.snap_grid)

    def _on_window_event(self, window) -> None:
        if window != self.win:
            return
        props = window.getProperties()
        w, h = int(props.getXSize()), int(props.getYSize())
        if w > 1 and h > 1:
            self._cam.on_resize(w, h)
            self._rebuild_grid()

    def _refresh_title(self) -> None:
        if self.win is None:
            return
        name = self._file_path.name if self._file_path else "Untitled"
        dirty = " *" if self._level.dirty else ""
        props = WindowProperties()
        props.setTitle(f"{WINDOW_TITLE} — {name}{dirty}")
        self.win.requestProperties(props)

    def _focus_polyline(self, pid: str) -> None:
        pl = self._level.get_polyline(pid)
        if pl is None:
            return
        self._pm.select(pid)
        if not pl.vertices:
            return
        xs = [v[0] for v in pl.vertices]
        zs = [v[1] for v in pl.vertices]
        pad = 2.0
        self._cam.zoom_to_fit(min(xs) - pad, max(xs) + pad, min(zs) - pad, max(zs) + pad)
        self._rebuild_grid()

    def _load_editor_state(self) -> dict:
        if not EDITOR_STATE_PATH.is_file():
            return {}
        try:
            data = json.loads(EDITOR_STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _restore_texture_dir(self, state: Optional[dict] = None) -> None:
        if state is None:
            state = self._load_editor_state()
        saved = state.get("texture_dir") if isinstance(state, dict) else None
        candidates = []
        if saved:
            candidates.append(Path(str(saved)))
        candidates.append(TOOL_ROOT / "assets" / "sample_textures")
        for path in candidates:
            if path.is_dir():
                self._tex.scan_directory(path)
                return

    def _save_editor_state(self) -> None:
        data = self._load_editor_state()
        data["texture_dir"] = str(self._tex.base_dir) if self._tex.base_dir else None
        data["ui_scale"] = self._ui_scale
        try:
            EDITOR_STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _set_ui_scale(self, scale: float) -> None:
        self._ui_scale = clamp_ui_scale(scale)
        self._save_editor_state()

    def _apply_imgui_ui_scale(self) -> None:
        try:
            from imgui_bundle import imgui

            self._imgui_scale_applied = apply_imgui_ui_scale(
                imgui.get_style(),
                target=self._ui_scale,
                applied=self._imgui_scale_applied,
            )
        except Exception:
            pass

    def _ui_scale_task(self, task):
        self._apply_imgui_ui_scale()
        return task.cont


def main() -> None:
    configure_editor()
    app = PassagesApp()
    app.run()


if __name__ == "__main__":
    main()
