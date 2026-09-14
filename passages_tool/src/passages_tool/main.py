"""
main.py
───────
Passages Level Editor — main application entry point.

Architecture overview
─────────────────────
  PassagesApp (ShowBase subclass)
    ├── ViewportCamera   — orthographic pan/zoom
    ├── BackgroundGrid   — redrawn on zoom/pan
    ├── Level            — document data model
    ├── History          — undo/redo
    ├── PolylineManager  — scene-graph objects for all polylines
    ├── TextureManager   — texture/thumbnail cache
    ├── Toolbar          — ImGui menu bar
    ├── TexturePalette   — ImGui right-side panel
    └── PropertiesPanel  — ImGui bottom-right panel

Coordinate system
─────────────────
  World: XZ plane (Panda3D Z-up).  Camera is at Y=-100, looking +Y.
  Screen: normalised [-1, 1] via Panda3D's mouse watcher.

ImGui integration
─────────────────
  Uses p3dimgui (panda3d-imgui package).
  p3dimgui adds two tasks:
    sort=0  — imgui-new-frame
    sort=40 — imgui-render-frame
  Our UI task runs at sort=10, between those two.

Tool modes
──────────
  SELECT        — click/drag vertex handles; click background to deselect
  DRAW_POLYLINE — left-click adds a vertex to the active polyline;
                  Enter/RMB finishes the polyline
"""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from typing import Optional

from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    WindowProperties,
    loadPrcFileData,
)

from passages_tool.config import (
    PICK_RADIUS_PX,
    WINDOW_H,
    WINDOW_TITLE,
    WINDOW_W,
)
from passages_tool.editor.history  import History
from passages_tool.editor.level    import (
    Level,
    Polyline,
    PolylineType,
    wall_edge_index_pairs,
)

TOOL_ROOT = Path(__file__).resolve().parents[2]
EDITOR_STATE_PATH = TOOL_ROOT / "editor_state.json"
from passages_tool.editor.polyline import PolylineManager
from passages_tool.io.level_format  import LevelIOError, load, save
from passages_tool.textures.manager import TextureManager
from passages_tool.ui.palette       import TexturePalette
from passages_tool.ui.properties    import PropertiesPanel
from passages_tool.ui.toolbar       import ToolMode, Toolbar
from passages_tool.viewport.camera  import ViewportCamera
from passages_tool.viewport.grid    import BackgroundGrid

# ── Panda3D config (must be set before ShowBase.__init__) ────────────────────
loadPrcFileData("", f"window-title {WINDOW_TITLE}")
loadPrcFileData("", f"win-size {WINDOW_W} {WINDOW_H}")
loadPrcFileData("", "sync-video false")
loadPrcFileData("", "show-frame-rate-meter false")  # shown in ImGui toolbar instead
loadPrcFileData("", "notify-level warning")


class PassagesApp(ShowBase):
    def __init__(self) -> None:
        super().__init__()

        # ── Core state ────────────────────────────────────────────────────────
        self._level    = Level()
        self._history  = History(max_size=100)
        self._tool     = ToolMode.SELECT
        self._active_polyline_id: Optional[str] = None   # polyline being drawn
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

        # ── Panda3D scene setup ───────────────────────────────────────────────
        self.setBackgroundColor(0.12, 0.12, 0.15, 1.0)

        # ── Viewport ──────────────────────────────────────────────────────────
        self._cam   = ViewportCamera(self, WINDOW_W, WINDOW_H)
        self._grid  = BackgroundGrid(self.render)
        self._pm    = PolylineManager(self.render)
        self._pm.level = self._level
        self._tex   = TextureManager()
        self._restore_texture_dir()

        self._rebuild_grid()
        self._refresh_title()

        # ── ImGui UI ──────────────────────────────────────────────────────────
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
            # Phase 3 ── interval editor ────────────────────────────────
            "set_interval_texture":    self._cb_set_interval_texture,
            "set_interval_x_offset":   self._cb_set_interval_x_offset,
            "add_texture_interval":    self._cb_add_texture_interval,
            "remove_texture_interval": self._cb_remove_texture_interval,
            "split_texture_interval":  self._cb_split_texture_interval,
            # Phase 3 ── eyepath edge editor ────────────────────────────
            "add_eyepath_edge":        self._cb_add_eyepath_edge,
            "remove_eyepath_edge":     self._cb_remove_eyepath_edge,
            "set_meta_field":          self._cb_set_meta_field,
            "render_preview":          self._cb_render_preview,
        })

        # ── Input bindings ────────────────────────────────────────────────────
        self._init_input()
        if self.win is not None:
            self.win.setCloseRequestEvent("passages-close")
        self.accept("passages-close", self.cmd_exit)
        self.accept("window-event", self._on_window_event)

        # ── Main update task ───────────────────────────────────────────────────
        self.taskMgr.add(self._update, "passages_update")

        # ── Hidden tkinter root (for native file dialogs) ─────────────────────
        self._tk_root = tk.Tk()
        self._tk_root.withdraw()

    # ── ImGui init ────────────────────────────────────────────────────────────

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
            # Add our UI drawing task between new_frame (0) and render_frame (40).
            self.taskMgr.add(self._imgui_frame, "passages_imgui_ui", sort=10)
            self._imgui_active = True
        except Exception as e:
            print(
                f"[WARNING] p3dimgui not available: {e}\n"
                "  UI panels will be unavailable.\n"
                "  Run: pip install panda3d-imgui"
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
            )
            self._palette.draw()
            self._props.draw(sel_pl, self._palette.selected_name, self._level)
            self._refresh_title()

            if self._arch_snap_pending:
                from imgui_bundle import imgui
                display_size = imgui.get_io().display_size
                imgui.set_next_window_pos((display_size.x / 2 - 180, 50), imgui.Cond_.always.value)
                imgui.set_next_window_size((360, 80), imgui.Cond_.always.value)
                imgui.begin("Arch Alignment Snap", None, 
                            imgui.WindowFlags_.no_title_bar.value | 
                            imgui.WindowFlags_.no_resize.value | 
                            imgui.WindowFlags_.no_move.value)
                imgui.text_colored((1.0, 0.8, 0.2, 1.0), "Offer Wall-Perpendicular Snap")
                imgui.text("Press Enter to snap perpendicular, Esc (or click) to keep billboard.")
                imgui.end()

            if self._validation_warnings:
                from imgui_bundle import imgui
                imgui.set_next_window_size((400, 200), imgui.Cond_.first_use_ever.value)
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
            import traceback
            traceback.print_exc()
        return task.cont

    # ── Input bindings ────────────────────────────────────────────────────────

    def _init_input(self) -> None:
        self.accept("wheel_up",   self._on_scroll, [-1])
        self.accept("wheel_down", self._on_scroll, [+1])
        self.accept("mouse2",     self._on_pan_start)
        self.accept("mouse2-up",  self._on_pan_end)
        self.accept("mouse1",     self._on_lclick)
        self.accept("mouse1-up",  self._on_lclick_up)
        self.accept("enter",      self._on_enter)
        self.accept("mouse3",     self._finish_draw)
        self.accept("delete",     self._on_delete)
        self.accept("control-z",  self.cmd_undo)
        self.accept("control-y",  self.cmd_redo)
        self.accept("control-s",  self.cmd_save)
        self.accept("control-shift-s", self._cmd_save_as)
        self.accept("control-o",  self.cmd_open)
        self.accept("control-n",  self.cmd_new)
        self.accept("s",          lambda: self._set_tool_key(ToolMode.SELECT))
        self.accept("w",          lambda: self._set_tool_key(ToolMode.DRAW_WALL))
        self.accept("a",          lambda: self._set_tool_key(ToolMode.DRAW_ARCH))
        self.accept("e",          lambda: self._set_tool_key(ToolMode.DRAW_EYEPATH))
        self.accept("r",          lambda: self._set_tool_key(ToolMode.DRAW_ANCHOR))
        self.accept("g",          self._toggle_snap)
        self.accept("v",          self._run_validation)
        self.accept("escape",     self._on_escape)

    # ── Main update task ──────────────────────────────────────────────────────

    def _update(self, task):
        if self._panning and self.mouseWatcherNode.hasMouse():
            mx = self.mouseWatcherNode.getMouseX()
            my = self.mouseWatcherNode.getMouseY()
            wx, wz = self._cam.screen_to_world(mx, my)
            dx = wx - self._pan_last[0]
            dz = wz - self._pan_last[1]
            self._cam.pan(-dx, -dz)
            self._pan_last = self._cam.screen_to_world(mx, my)
            self._rebuild_grid()
        elif (
            self._drag_pid is not None
            and self._drag_idx is not None
            and self.mouseWatcherNode.hasMouse()
        ):
            mx = self.mouseWatcherNode.getMouseX()
            my = self.mouseWatcherNode.getMouseY()
            wx, wz = self._cam.screen_to_world(mx, my)
            if self._snap_enabled:
                grid_size = self._level.meta.snap_grid
                if grid_size > 0:
                    wx = round(wx / grid_size) * grid_size
                    wz = round(wz / grid_size) * grid_size
            self._hist(f"drag:{self._drag_pid}:{self._drag_idx}")
            self._level.move_vertex(self._drag_pid, self._drag_idx, wx, wz)
            self._pm.rebuild_one(self._drag_pid)
        return task.cont

    # ── Viewport interaction ──────────────────────────────────────────────────

    def _on_scroll(self, direction: int) -> None:
        # Don't zoom if ImGui is capturing the mouse.
        if self._imgui_active:
            try:
                if self.imgui.isMouseCaptured():
                    return
            except AttributeError:
                pass
        self._cam.zoom_by(direction)
        self._rebuild_grid()

    def _on_pan_start(self) -> None:
        if not self.mouseWatcherNode.hasMouse():
            return
        mx = self.mouseWatcherNode.getMouseX()
        my = self.mouseWatcherNode.getMouseY()
        self._pan_last = self._cam.screen_to_world(mx, my)
        self._panning  = True

    def _on_pan_end(self) -> None:
        self._panning = False

    def _on_lclick(self) -> None:
        # Don't interact with level if ImGui captured the click.
        if self._imgui_active:
            try:
                if self.imgui.isMouseCaptured():
                    return
            except AttributeError:
                pass
        if not self.mouseWatcherNode.hasMouse():
            return

        if self._arch_snap_pending:
            self._confirm_arch_snap(accept=False)
            return

        mx = self.mouseWatcherNode.getMouseX()
        my = self.mouseWatcherNode.getMouseY()
        wx, wz = self._cam.screen_to_world(mx, my)

        if self._tool in (
            ToolMode.DRAW_WALL,
            ToolMode.DRAW_ARCH,
            ToolMode.DRAW_EYEPATH,
            ToolMode.DRAW_ANCHOR,
        ):
            self._draw_add_vertex(wx, wz)
        elif self._tool == ToolMode.SELECT:
            self._select_at(wx, wz, mx, my)

    def _on_lclick_up(self) -> None:
        self._drag_pid = None
        self._drag_idx = None
        self._history_edit_key = None

    # ── Draw tool ─────────────────────────────────────────────────────────────

    def _draw_add_vertex(self, wx: float, wz: float) -> None:
        if self._snap_enabled:
            grid_size = self._level.meta.snap_grid
            wx = round(wx / grid_size) * grid_size
            wz = round(wz / grid_size) * grid_size

        # ── Place Anchor: single click, immediate finish + select ─────────────
        if self._tool == ToolMode.DRAW_ANCHOR:
            pl = Polyline.make_anchor((wx, wz))
            self._hist()
            self._level.add_polyline(pl)
            self._pm.sync_with_level(self._level.polylines)
            self._pm.select(pl.id)
            self._tool = ToolMode.SELECT
            return

        # ── Place Arch: single click, immediate finish + select ───────────────
        if self._tool == ToolMode.DRAW_ARCH:
            pl = Polyline.make_arch((wx, wz))
            self._hist()
            self._level.add_polyline(pl)
            self._pm.sync_with_level(self._level.polylines)
            self._pm.select(pl.id)

            # Check for perpendicular snapping
            from passages_tool.editor.arch_utils import nearest_wall_edge, arch_perpendicular_angle, is_tangent_ambiguous
            res = nearest_wall_edge((wx, wz), self._level)
            if res:
                wall_pid, edge_idx, tangent_ang, dist = res
                if dist <= 3.0:
                    perp_ang = arch_perpendicular_angle(tangent_ang)
                    pl.orientation = perp_ang
                    self._arch_snap_pending = True
                    self._pending_arch_id = pl.id
                    if is_tangent_ambiguous(self._level, wall_pid, edge_idx, (wx, wz)):
                        pl.warning = True
                    self._pm.rebuild_one(pl.id)
                    return  # wait for confirmation
            self._tool = ToolMode.SELECT
            return

        # ── Wall / EyePath: accumulate vertices, finish on Enter/RMB ─────────
        if self._active_polyline_id is None:
            if self._tool == ToolMode.DRAW_EYEPATH:
                pl = Polyline.make_eyepath()
            else:
                pl = Polyline.make_wall()   # default + DRAW_WALL
            self._hist()
            self._level.add_polyline(pl)
            self._pm.sync_with_level(self._level.polylines)
            self._active_polyline_id = pl.id
        else:
            self._hist()

        self._level.add_vertex(self._active_polyline_id, wx, wz)
        
        # Auto-create directed EyePath edges when drawing consecutive vertices
        pl = self._level.get_polyline(self._active_polyline_id)
        if pl and pl.type == PolylineType.EYEPATH and len(pl.vertices) >= 2:
            v_from = len(pl.vertices) - 2
            v_to = len(pl.vertices) - 1
            self._level.add_eyepath_edge(pl.id, v_from, v_to)
            
        self._pm.rebuild_one(self._active_polyline_id)

    def _on_enter(self) -> None:
        if self._imgui_wants_keyboard():
            return
        self._finish_draw()

    def _finish_draw(self) -> None:
        """Finish the active polyline, auto-select it, and return to SELECT."""
        if self._arch_snap_pending:
            self._confirm_arch_snap(accept=True)
            return
        if self._active_polyline_id:
            # Auto-select the completed polyline so its properties appear.
            self._pm.select(self._active_polyline_id)
        self._active_polyline_id = None
        self._tool = ToolMode.SELECT

    def _confirm_arch_snap(self, accept: bool) -> None:
        if self._arch_snap_pending and self._pending_arch_id:
            pl = self._level.get_polyline(self._pending_arch_id)
            if pl and pl.type == PolylineType.ARCH:
                if not accept:
                    pl.orientation = "billboard"
                    self._pm.rebuild_one(pl.id)
            self._arch_snap_pending = False
            self._pending_arch_id = None
        self._tool = ToolMode.SELECT

    def _on_escape(self) -> None:
        if self._imgui_wants_keyboard():
            return
        if self._arch_snap_pending:
            self._confirm_arch_snap(accept=False)

    def _set_tool_key(self, tool: ToolMode) -> None:
        if self._imgui_wants_keyboard():
            return
        self.set_tool(tool)

    # ── Select tool ───────────────────────────────────────────────────────────

    def _select_at(self, wx: float, wz: float, mx: float, my: float) -> None:
        """Pick a vertex (starts a drag) or an edge (selects the polyline)."""
        ndc_r = PICK_RADIUS_PX / (0.5 * max(1, self._cam.win_w))
        r2 = ndc_r * ndc_r

        best_d2 = r2
        best_pid: Optional[str] = None
        best_idx: Optional[int] = None
        for pid, pl in self._level.polylines.items():
            for i, (vx, vz) in enumerate(pl.vertices):
                sx, sy = self._cam.world_to_screen(vx, vz)
                d2 = (sx - mx) ** 2 + (sy - my) ** 2
                if d2 < best_d2:
                    best_d2 = d2
                    best_pid = pid
                    best_idx = i
        if best_pid is not None and best_idx is not None:
            self._pm.select(best_pid)
            self._drag_pid = best_pid
            self._drag_idx = best_idx
            return

        best_d2 = r2
        best_pid = None
        for pid, pl in self._level.polylines.items():
            pairs: list[tuple[tuple[float, float], tuple[float, float]]]
            if pl.type == PolylineType.WALL:
                verts = pl.vertices
                pairs = [(verts[a], verts[b]) for a, b in wall_edge_index_pairs(pl)]
            elif pl.type == PolylineType.EYEPATH and pl.edges:
                verts = pl.vertices
                pairs = [
                    (verts[a], verts[b])
                    for a, b in pl.edges
                    if a < len(verts) and b < len(verts)
                ]
            elif len(pl.vertices) >= 2:
                pairs = list(zip(pl.vertices, pl.vertices[1:]))
            else:
                continue
            for (ax, az), (bx, bz) in pairs:
                sx0, sy0 = self._cam.world_to_screen(ax, az)
                sx1, sy1 = self._cam.world_to_screen(bx, bz)
                d2 = _point_seg_dist2(mx, my, sx0, sy0, sx1, sy1)
                if d2 < best_d2:
                    best_d2 = d2
                    best_pid = pid
        self._pm.select(best_pid)

    def _get_selected_polyline(self) -> Optional[Polyline]:
        sel = self._pm.selected_id
        if sel:
            return self._level.get_polyline(sel)
        return None

    # ── Delete ────────────────────────────────────────────────────────────────

    def _on_delete(self) -> None:
        if self._imgui_wants_keyboard():
            return
        sel = self._pm.selected_id
        if sel:
            self._hist()
            self._level.remove_polyline(sel)
            self._pm.sync_with_level(self._level.polylines)

    def _toggle_snap(self) -> None:
        if self._imgui_wants_keyboard():
            return
        self._snap_enabled = not self._snap_enabled

    def _run_validation(self) -> None:
        if self._imgui_wants_keyboard():
            return
        from passages_tool.editor.validator import (
            validate_arch_visibility,
            validate_structure,
            validate_textures,
        )
        self._validation_warnings = (
            validate_structure(self._level)
            + validate_arch_visibility(self._level)
            + validate_textures(self._level)
        )
        self._rebuild_all_highlights()

    # ── Rebuild grid ──────────────────────────────────────────────────────────

    def _rebuild_grid(self) -> None:
        fw = self._cam.film_w
        fh = self._cam.film_h
        cx = self._cam._cam_x
        cz = self._cam._cam_z
        self._grid.rebuild(fw, fh, cx, cz, cell=self._level.meta.snap_grid)

    # ── File commands ─────────────────────────────────────────────────────────

    def cmd_new(self) -> None:
        if self._level.dirty and not self._confirm_discard():
            return
        self._level = Level()
        self._pm.level = self._level
        self._history.clear()
        self._pm.destroy_all()
        self._file_path = None
        self._active_polyline_id = None
        self._validation_warnings = []
        self._capture_saved()

    def cmd_open(self) -> None:
        if self._level.dirty and not self._confirm_discard():
            return
        path = filedialog.askopenfilename(
            title="Open Level",
            filetypes=[("Passages Level", "*.passages.json"), ("All files", "*.*")],
            parent=self._tk_root,
        )
        if not path:
            return
        try:
            new_level = load(path)
        except LevelIOError as e:
            messagebox.showerror("Open Error", str(e), parent=self._tk_root)
            return
        self._level = new_level
        self._pm.level = self._level
        self._history.clear()
        self._pm.destroy_all()
        self._pm.sync_with_level(self._level.polylines)
        self._pm.rebuild_all()
        self._file_path = Path(path)
        self._cam.zoom_to_fit(*self._level.bounding_box())
        self._rebuild_grid()
        self._validation_warnings = []
        self._capture_saved()

    def cmd_save(self) -> None:
        if self._file_path is None:
            self._cmd_save_as()
            return
        try:
            save(self._level, self._file_path)
            self._capture_saved()
        except LevelIOError as e:
            messagebox.showerror("Save Error", str(e), parent=self._tk_root)

    def _cmd_save_as(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save Level As",
            defaultextension=".passages.json",
            filetypes=[("Passages Level", "*.passages.json"), ("All files", "*.*")],
            parent=self._tk_root,
        )
        if not path:
            return
        self._file_path = Path(path)
        self.cmd_save()

    def cmd_browse_textures(self) -> None:
        directory = filedialog.askdirectory(
            title="Select Texture Folder",
            parent=self._tk_root,
        )
        if directory:
            self._tex.scan_directory(directory)
            self._save_editor_state()

    # ── Undo / Redo ───────────────────────────────────────────────────────────

    def cmd_undo(self) -> None:
        self._history_edit_key = None
        snapshot = self._history.undo(self._level.to_dict())
        if snapshot is not None:
            self._apply_snapshot(snapshot)

    def cmd_redo(self) -> None:
        self._history_edit_key = None
        snapshot = self._history.redo(self._level.to_dict())
        if snapshot is not None:
            self._apply_snapshot(snapshot)

    def _apply_snapshot(self, snapshot: dict) -> None:
        old_sel = self._pm.selected_id
        self._level = Level.from_dict(snapshot)
        self._pm.level = self._level
        self._pm.destroy_all()
        self._pm.sync_with_level(self._level.polylines)
        self._pm.rebuild_all()
        if old_sel and old_sel in self._level.polylines:
            self._pm.select(old_sel)
        self._validation_warnings = []
        self._refresh_dirty()

    # ── Tool mode ──────────────────────────────────────────────────────────────

    def set_tool(self, tool: ToolMode) -> None:
        if self._arch_snap_pending:
            self._confirm_arch_snap(accept=False)
        _draw_modes = {ToolMode.DRAW_WALL, ToolMode.DRAW_ARCH, ToolMode.DRAW_EYEPATH, ToolMode.DRAW_ANCHOR}
        if self._tool in _draw_modes and tool not in _draw_modes:
            # Leaving a draw mode → finish whatever is in progress.
            self._finish_draw()
        elif tool != self._tool:
            # Switching between draw modes → abandon the partially-drawn polyline.
            self._active_polyline_id = None
        self._tool = tool

    # ── PropertiesPanel callbacks ──────────────────────────────────────────────

    def _cb_set_closed(self, pid: str, closed: bool) -> None:
        self._hist()
        self._level.set_polyline_closed(pid, closed)
        self._pm.rebuild_one(pid)

    def _cb_set_texture(self, pid: str, tex: Optional[str]) -> None:
        self._hist()
        self._level.set_polyline_texture(pid, tex)

    def _cb_move_vertex(self, pid: str, idx: int, x: float, z: float) -> None:
        self._hist(f"move:{pid}:{idx}")
        self._level.move_vertex(pid, idx, x, z)
        self._pm.rebuild_one(pid)

    def _cb_del_vertex(self, pid: str, idx: int) -> None:
        self._hist()
        self._level.delete_vertex(pid, idx)
        self._pm.rebuild_one(pid)

    def _cb_insert_vertex(self, pid: str, after_idx: int,
                          x: float, z: float) -> None:
        self._hist()
        self._level.insert_vertex(pid, after_idx, x, z)
        self._pm.rebuild_one(pid)

    def _cb_del_polyline(self, pid: str) -> None:
        self._hist()
        self._level.remove_polyline(pid)
        self._pm.sync_with_level(self._level.polylines)

    def _cb_set_type(self, pid: str, type_str: str) -> None:
        """Change the polyline type after confirming destructive conversion."""
        pl = self._level.get_polyline(pid)
        if pl is None:
            return
        try:
            new_type = PolylineType(type_str)
        except ValueError:
            return
        if pl.type == new_type:
            return
        if not messagebox.askyesno(
            "Change type",
            f"Convert this {pl.type.value} to {new_type.value}?\n"
            "Vertices/intervals/edges that the new type does not use will be dropped.",
            parent=self._tk_root,
        ):
            return
        self._hist()
        _convert_polyline_type(pl, new_type)
        self._level.dirty = True
        self._pm.rebuild_one(pid)

    def _cb_set_field(self, pid: str, field: str, value) -> None:
        """Generic field setter for Arch (and future) properties."""
        self._hist(f"field:{pid}:{field}")
        pl = self._level.get_polyline(pid)
        if pl and hasattr(pl, field):
            setattr(pl, field, value)
            self._level.dirty = True
        self._pm.rebuild_one(pid)

    # ── Phase 3: interval callbacks ────────────────────────────────────────────

    def _cb_set_interval_texture(
            self, pid: str, idx: int, tex: Optional[str]) -> None:
        self._hist()
        self._level.set_interval_texture(pid, idx, tex)
        self._pm.rebuild_one(pid)

    def _cb_set_interval_x_offset(
            self, pid: str, idx: int, x: float) -> None:
        self._hist(f"ivoff:{pid}:{idx}")
        self._level.set_interval_x_offset(pid, idx, x)

    def _cb_add_texture_interval(
            self, pid: str, from_v: int, to_v: int) -> None:
        from passages_tool.editor.level import TextureInterval
        self._hist()
        self._level.add_texture_interval(
            pid, TextureInterval(from_vertex=from_v, to_vertex=to_v))
        self._pm.rebuild_one(pid)

    def _cb_remove_texture_interval(self, pid: str, idx: int) -> None:
        self._hist()
        self._level.remove_texture_interval(pid, idx)
        self._pm.rebuild_one(pid)

    def _cb_split_texture_interval(self, pid: str, at_vertex: int) -> None:
        self._hist()
        self._level.split_texture_interval(pid, at_vertex)
        self._pm.rebuild_one(pid)

    # ── Phase 3: eyepath edge callbacks ──────────────────────────────────────

    def _cb_add_eyepath_edge(
            self, pid: str, v_from: int, v_to: int) -> None:
        self._hist()
        pl = self._level.get_polyline(pid)
        if pl and pl.type == PolylineType.EYEPATH and not pl.edges:
            n_verts = len(pl.vertices)
            if n_verts >= 2:
                for i in range(n_verts - 1):
                    self._level.add_eyepath_edge(pid, i, i + 1)
        self._level.add_eyepath_edge(pid, v_from, v_to)
        self._pm.rebuild_one(pid)

    def _cb_remove_eyepath_edge(
            self, pid: str, v_from: int, v_to: int) -> None:
        self._hist()
        self._level.remove_eyepath_edge(pid, v_from, v_to)
        self._pm.rebuild_one(pid)

    def _cb_set_meta_field(self, field: str, value) -> None:
        if field == "fov_h":
            # Horizontal FOV is derived from fov_v + render aspect; ignore edits.
            return
        self._hist(f"meta:{field}")
        setattr(self._level.meta, field, value)
        self._level.dirty = True
        if field in ("fov_v", "render_width", "render_height"):
            self._level.sync_derived_fov_h()
        if field == "snap_grid":
            self._rebuild_grid()

    def _rebuild_all_highlights(self) -> None:
        highlighted_ids = {w.arch_id for w in self._validation_warnings}
        self._pm.set_highlights(highlighted_ids)

    def _cb_render_preview(self, pid: str, v_from: int, v_to: int) -> None:
        from passages_tool.converter.scene_builder import build_scene
        from passages_tool.renderer.viewpoint_renderer import ViewpointRenderer
        from panda3d.core import TexturePool

        # Tool root is parents[2] of this file (src/passages_tool/main.py).
        preview_dir = Path(__file__).resolve().parents[2] / "temp_preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        tex_dir = self._tex.base_dir

        if tex_dir:
            from passages_tool.textures.manager import preload_level_textures
            preload_level_textures(self._level, tex_dir)

        try:
            build_scene(self._level, preview_dir, tex_dir, write_combined=False)
        except Exception as e:
            print(f"Error compiling scene for preview: {e}")
            return

        temp_png = preview_dir / "preview.png"
        renderer = None
        try:
            renderer = ViewpointRenderer(self._level, preview_dir, tex_dir)
            ok = renderer.render_edge(v_from, v_to, temp_png)
        except Exception as e:
            print(f"Error rendering preview: {e}")
            return
        finally:
            if renderer:
                renderer.close()

        if temp_png.is_file():
            # Release cached texture reference to force reload
            tex_path_str = str(temp_png)
            TexturePool.release_texture(TexturePool.find_texture(tex_path_str))
            panda_tex = TexturePool.load_texture(tex_path_str)
            if panda_tex:
                try:
                    ref = self.base.imgui.loadTexture(panda_tex)
                    self._props.set_preview_image(ref)
                except Exception as e:
                    print(f"Error loading preview texture into ImGui: {e}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _hist(self, key: Optional[str] = None) -> None:
        """Push a history snapshot. Repeating `key` coalesces slider/drag edits."""
        if key is None:
            self._history.push(self._level.to_dict())
            self._history_edit_key = None
            return
        if key != self._history_edit_key:
            self._history.push(self._level.to_dict())
            self._history_edit_key = key

    def _imgui_wants_keyboard(self) -> bool:
        if not self._imgui_active:
            return False
        try:
            if self.imgui.isKeyboardCaptured():
                return True
        except AttributeError:
            pass
        try:
            from imgui_bundle import imgui
            return bool(imgui.get_io().want_capture_keyboard)
        except Exception:
            return False

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

    def _restore_texture_dir(self) -> None:
        saved: Optional[str] = None
        if EDITOR_STATE_PATH.is_file():
            try:
                saved = json.loads(EDITOR_STATE_PATH.read_text(encoding="utf-8")).get(
                    "texture_dir"
                )
            except (OSError, json.JSONDecodeError, AttributeError):
                saved = None
        candidates = []
        if saved:
            candidates.append(Path(saved))
        candidates.append(TOOL_ROOT / "assets" / "sample_textures")
        for path in candidates:
            if path.is_dir():
                self._tex.scan_directory(path)
                return

    def _save_editor_state(self) -> None:
        data = {
            "texture_dir": str(self._tex.base_dir) if self._tex.base_dir else None,
        }
        try:
            EDITOR_STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _capture_saved(self) -> None:
        """Record the last-saved document so undo can restore a clean dirty flag."""
        self._saved_snapshot = self._level.to_dict()
        self._level.dirty = False
        self._refresh_title()

    def _refresh_dirty(self) -> None:
        self._level.dirty = self._level.to_dict() != self._saved_snapshot

    def cmd_exit(self) -> None:
        if self._level.dirty and not self._confirm_discard():
            return
        self.userExit()

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno(
            "Unsaved Changes",
            "The current level has unsaved changes.\nDiscard and continue?",
            parent=self._tk_root,
        )


def _point_seg_dist2(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    abx, aby = bx - ax, by - ay
    denom = abx * abx + aby * aby
    if denom < 1e-12:
        dx, dy = px - ax, py - ay
        return dx * dx + dy * dy
    t = ((px - ax) * abx + (py - ay) * aby) / denom
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * abx, ay + t * aby
    dx, dy = px - cx, py - cy
    return dx * dx + dy * dy


def _convert_polyline_type(pl: Polyline, new_type: PolylineType) -> None:
    """Keep compatible fields when changing a polyline's type in place."""
    pl.type = new_type
    if new_type in (PolylineType.ARCH, PolylineType.ANCHOR):
        if pl.vertices:
            pl.vertices = [pl.vertices[0]]
        pl.texture_intervals = []
        pl.edges = []
        pl.closed = False
    elif new_type == PolylineType.WALL:
        pl.edges = []
    elif new_type == PolylineType.EYEPATH:
        pl.texture_intervals = []
        pl.closed = False


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    app = PassagesApp()
    app.run()


if __name__ == "__main__":
    main()
