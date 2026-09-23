"""File, undo, and properties-panel commands. Mixed into PassagesApp."""
from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

from passages_tool.editor.level import (
    Level,
    PolylineType,
    TextureInterval,
    convert_polyline_type,
)
from passages_tool.editor.polyline_data import EyePath
from passages_tool.io.level_format import LevelIOError, load, save


class CommandsMixin:
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
        self._resync_window()
        if not path:
            return
        try:
            new_level = load(path)
        except LevelIOError as e:
            messagebox.showerror("Open Error", str(e), parent=self._tk_root)
            self._resync_window()
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
            self._resync_window()

    def _cmd_save_as(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save Level As",
            defaultextension=".passages.json",
            filetypes=[("Passages Level", "*.passages.json"), ("All files", "*.*")],
            parent=self._tk_root,
        )
        self._resync_window()
        if not path:
            return
        self._file_path = Path(path)
        self.cmd_save()

    def cmd_browse_textures(self) -> None:
        directory = filedialog.askdirectory(
            title="Select Texture Folder",
            parent=self._tk_root,
        )
        self._resync_window()
        if directory:
            self._tex.scan_directory(directory)
            self._save_editor_state()

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
        pl = self._level.get_polyline(pid)
        n = len(pl.vertices) if pl else 0
        sel = self._pm.selected_vertex_idx
        if pid == self._pm.selected_id and sel is not None:
            if n <= 0:
                self._pm.select(pid, None)
            elif sel == idx:
                self._pm.select(pid, min(idx, n - 1))
            elif sel > idx:
                self._pm.select(pid, sel - 1)
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
            self._resync_window()
            return
        self._resync_window()
        self._hist()
        self._level.replace_polyline(convert_polyline_type(pl, new_type))
        self._pm.rebuild_one(pid)

    def _cb_select_vertex(self, idx: int) -> None:
        pid = self._pm.selected_id
        if pid:
            self._pm.select(pid, idx)

    def _cb_set_field(self, pid: str, field: str, value) -> None:
        """Generic field setter for Arch (and future) properties."""
        self._hist(f"field:{pid}:{field}")
        pl = self._level.get_polyline(pid)
        if pl and hasattr(pl, field):
            setattr(pl, field, value)
            if field == "kind" and value == "volume":
                from passages_tool.converter.opening import apply_volume_kind_defaults

                apply_volume_kind_defaults(pl)
            self._level.dirty = True
        self._pm.rebuild_one(pid)

    def _cb_set_interval_texture(
            self, pid: str, idx: int, tex: Optional[str]) -> None:
        self._hist()
        self._level.set_interval_texture(pid, idx, tex)
        self._pm.rebuild_one(pid)

    def _cb_clear_wall_png_overrides(self, pid: str) -> None:
        self._hist()
        self._level.clear_wall_png_overrides(pid)
        self._pm.rebuild_one(pid)

    def _cb_set_interval_x_offset(
            self, pid: str, idx: int, x: float) -> None:
        self._hist(f"ivoff:{pid}:{idx}")
        self._level.set_interval_x_offset(pid, idx, x)

    def _cb_add_texture_interval(
            self, pid: str, from_v: int, to_v: int) -> None:
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

    def _cb_add_eyepath_edge(
            self, pid: str, v_from: int, v_to: int) -> None:
        self._hist()
        pl = self._level.get_polyline(pid)
        if isinstance(pl, EyePath) and not pl.edges:
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

    def _cb_list_styles(self) -> list:
        from passages_tool.textures.style import list_style_ids

        return list_style_ids(self._tex.base_dir)

    def _cb_set_meta_field(self, field: str, value) -> None:
        if field == "fov_h":
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

    def _hist(self, key: Optional[str] = None) -> None:
        """Push a history snapshot. Repeating `key` coalesces slider/drag edits."""
        if key is None:
            self._history.push(self._level.to_dict())
            self._history_edit_key = None
            return
        if key != self._history_edit_key:
            self._history.push(self._level.to_dict())
            self._history_edit_key = key

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
        ok = messagebox.askyesno(
            "Unsaved Changes",
            "The current level has unsaved changes.\nDiscard and continue?",
            parent=self._tk_root,
        )
        self._resync_window()
        return ok


