"""Viewport mouse/keyboard handlers. Mixed into PassagesApp."""
from __future__ import annotations

from typing import Optional

from passages_tool.config import PICK_RADIUS_PX
from passages_tool.editor.level import Polyline, PolylineType, wall_edge_index_pairs
from passages_tool.ui.toolbar import ToolMode


class InputMixin:
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

    def _on_scroll(self, direction: int) -> None:
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

    def _draw_add_vertex(self, wx: float, wz: float) -> None:
        if self._snap_enabled:
            grid_size = self._level.meta.snap_grid
            wx = round(wx / grid_size) * grid_size
            wz = round(wz / grid_size) * grid_size

        if self._tool == ToolMode.DRAW_ANCHOR:
            pl = Polyline.make_anchor((wx, wz))
            self._hist()
            self._level.add_polyline(pl)
            self._pm.sync_with_level(self._level.polylines)
            self._pm.select(pl.id)
            self._tool = ToolMode.SELECT
            return

        if self._tool == ToolMode.DRAW_ARCH:
            pl = Polyline.make_arch((wx, wz))
            self._hist()
            self._level.add_polyline(pl)
            self._pm.sync_with_level(self._level.polylines)
            self._pm.select(pl.id)

            from passages_tool.editor.arch_utils import (
                nearest_wall_edge,
                arch_perpendicular_angle,
                is_tangent_ambiguous,
            )
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
                    return
            self._tool = ToolMode.SELECT
            return

        if self._active_polyline_id is None:
            if self._tool == ToolMode.DRAW_EYEPATH:
                pl = Polyline.make_eyepath()
            else:
                pl = Polyline.make_wall()
            self._hist()
            self._level.add_polyline(pl)
            self._pm.sync_with_level(self._level.polylines)
            self._active_polyline_id = pl.id
        else:
            self._hist()

        self._level.add_vertex(self._active_polyline_id, wx, wz)

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

    def set_tool(self, tool: ToolMode) -> None:
        if self._arch_snap_pending:
            self._confirm_arch_snap(accept=False)
        _draw_modes = {
            ToolMode.DRAW_WALL,
            ToolMode.DRAW_ARCH,
            ToolMode.DRAW_EYEPATH,
            ToolMode.DRAW_ANCHOR,
        }
        if self._tool in _draw_modes and tool not in _draw_modes:
            self._finish_draw()
        elif tool != self._tool:
            self._active_polyline_id = None
        self._tool = tool

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
