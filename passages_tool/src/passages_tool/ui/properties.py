"""
ui/properties.py
────────────────
Properties inspector panel — Dear ImGui sidebar for the selected polyline.

Type-specific sections (v3 — Phase 3 complete)
───────────────────────────────────────────────
  WALL     Type selector; closed toggle; full texture-interval editor
           (assign texture from palette, set x_offset, split, remove,
           add new interval); vertex list.

  ARCH     Type selector; position; orientation (billboard / angle);
           width; height override; texture assign; transparency;
           z-offset; v-at-floor; light-source sub-section.

  EYEPATH  Type selector; directed edge editor (add / remove edges by
           vertex index); vertex list.

Callbacks (caller must supply in the dict passed to __init__)
──────────────────────────────────────────────────────────────
  set_closed(pid, bool)
  set_texture(pid, str|None)
  set_type(pid, str)
  set_field(pid, field, value)
  move_vertex(pid, idx, x, z)
  del_vertex(pid, idx)
  del_polyline(pid)
  -- Phase 3 additions --
  set_interval_texture(pid, idx, tex|None)
  set_interval_x_offset(pid, idx, float)
  add_texture_interval(pid, from_v, to_v)
  remove_texture_interval(pid, idx)
  split_texture_interval(pid, at_vertex)
  add_eyepath_edge(pid, v_from, v_to)
  remove_eyepath_edge(pid, v_from, v_to)
"""
from __future__ import annotations

from typing import Callable, Optional

from passages_tool.config import (
    INTERVAL_COLORS,
    PALETTE_PANEL_W,
    PROPS_PANEL_W,
)
from passages_tool.editor.level import Level, Polyline, PolylineType


_TYPE_LABELS = ["Wall", "Arch", "EyePath"]
_TYPE_VALUES = ["wall", "arch", "eyepath"]
_TRANS_LABELS = ["None", "Alpha test", "Alpha blend"]
_TRANS_VALUES = ["none", "alpha_test", "alpha_blend"]

# Soft tints shown next to each interval label (matches INTERVAL_COLORS).
_IV_TINTS = [
    (0.55, 0.78, 1.00, 1.0),
    (1.00, 0.82, 0.45, 1.0),
    (0.88, 0.60, 1.00, 1.0),
    (0.45, 1.00, 0.90, 1.0),
]


class PropertiesPanel:
    def __init__(self, callbacks: Optional[dict[str, Callable]] = None) -> None:
        self._cb = callbacks or {}

        # ── Per-session UI state ───────────────────────────────────────────────
        # EyePath edge "Add" inputs
        self._ep_from: int = 0
        self._ep_to:   int = 1

        # Wall interval "Add" inputs
        # _iv_to uses -1 as sentinel ("not yet initialised") so the user can
        # set it to 0 without triggering a re-initialisation every frame.
        self._iv_from: int = 0
        self._iv_to:   int = -1

        # Wall interval "Split" targets — one integer per interval index.
        self._iv_split: dict[int, int] = {}

        # Selected EyePath vertex preview state
        self._last_polyline_id: Optional[str] = None
        self._selected_vertex_idx: Optional[int] = None
        self._preview_target_idx: int = 0
        self._preview_image_ref: Optional[object] = None

    # ── Helper: integer stepper control ──────────────────────────────────────

    def _int_stepper(
        self, imgui, uid: str, value: int,
        min_v: int, max_v: int, width: int = 38,
    ) -> int:
        """
        Render  [−][ _value_ ][+]  with reliable click targets.

        input_int(step=0) shows a plain editable number without Imgui's
        built-in +/− arrows (which are too narrow for p3dimgui's mouse
        forwarding to register reliably).  The flanking small_button(−/+)
        are ordinary buttons and always work.

        uid must be unique within the current ImGui push_id scope.
        Returns the new value clamped to [min_v, max_v].
        """
        if imgui.small_button(f"-##{uid}"):
            value = max(min_v, value - 1)
        imgui.same_line()
        imgui.set_next_item_width(width)
        changed, nv = imgui.input_int(f"##{uid}v", value, step=0)
        if changed:
            value = max(min_v, min(nv, max_v))
        imgui.same_line()
        if imgui.small_button(f"+##{uid}"):
            value = min(max_v, value + 1)
        return value

    def set_preview_image(self, ref: Optional[object]) -> None:
        self._preview_image_ref = ref

    def draw(
        self,
        polyline:    Optional[Polyline],
        palette_sel: Optional[str],
        level:       Optional[Level] = None,
    ) -> None:
        """Render the properties panel. Must be called inside an imgui frame."""
        try:
            from imgui_bundle import imgui
        except ImportError:
            return

        # Reset selected vertex preview state if the selected polyline changes
        cur_id = polyline.id if polyline else None
        if getattr(self, "_last_polyline_id", None) != cur_id:
            self._last_polyline_id = cur_id
            self._selected_vertex_idx = None
            self._preview_image_ref = None

        display_w = imgui.get_io().display_size.x
        display_h = imgui.get_io().display_size.y
        panel_h   = display_h - 20

        always      = imgui.Cond_.always.value
        no_move     = imgui.WindowFlags_.no_move.value
        no_resize   = imgui.WindowFlags_.no_resize.value
        no_collapse = imgui.WindowFlags_.no_collapse.value

        imgui.set_next_window_size((PROPS_PANEL_W, panel_h), always)
        imgui.set_next_window_pos((display_w - PROPS_PANEL_W, 20), always)

        opened, _ = imgui.begin("Properties",
                                flags=no_move | no_resize | no_collapse)
        if not opened:
            imgui.end()
            return

        if polyline is None:
            if level is not None:
                self._draw_level_meta(imgui, level, palette_sel)
            else:
                imgui.text_colored((0.5, 0.5, 0.5, 1.0), "Nothing selected.")
            imgui.end()
            return

        # ── Type selector ─────────────────────────────────────────────────────
        self._draw_type_selector(imgui, polyline)
        imgui.separator()

        # ── ID line ───────────────────────────────────────────────────────────
        short_id = polyline.id[:18] + ("…" if len(polyline.id) > 18 else "")
        imgui.text_disabled(f"ID: {short_id}")

        # ── Type-specific body ────────────────────────────────────────────────
        t = polyline.type
        if t == PolylineType.WALL:
            self._draw_wall_props(imgui, polyline, palette_sel)
        elif t == PolylineType.ARCH:
            self._draw_arch_props(imgui, polyline, palette_sel)
        elif t == PolylineType.EYEPATH:
            self._draw_eyepath_props(imgui, polyline)

        # ── Delete polyline (all types) ───────────────────────────────────────
        imgui.separator()
        imgui.push_style_color(imgui.Col_.button.value, (0.7, 0.15, 0.15, 1.0))
        if imgui.button("Delete polyline", (-1, 0)):
            fn = self._cb.get("del_polyline")
            if fn:
                fn(polyline.id)
        imgui.pop_style_color()

        imgui.end()

    # ── Type selector ─────────────────────────────────────────────────────────

    def _draw_type_selector(self, imgui, polyline: Polyline) -> None:
        try:
            curr_idx = _TYPE_VALUES.index(polyline.type.value)
        except ValueError:
            curr_idx = 0
        imgui.set_next_item_width(-1)
        changed, new_idx = imgui.combo("##type", curr_idx, _TYPE_LABELS)
        if changed and new_idx != curr_idx:
            fn = self._cb.get("set_type")
            if fn:
                fn(polyline.id, _TYPE_VALUES[new_idx])

    # ── WALL ──────────────────────────────────────────────────────────────────

    def _draw_wall_props(
        self, imgui, polyline: Polyline, palette_sel: Optional[str],
    ) -> None:
        imgui.text(f"Vertices: {len(polyline.vertices)}")

        changed, new_closed = imgui.checkbox("Closed", polyline.closed)
        if changed:
            fn = self._cb.get("set_closed")
            if fn:
                fn(polyline.id, new_closed)

        imgui.separator()

        # ── Texture intervals ─────────────────────────────────────────────────
        self._draw_interval_editor(imgui, polyline, palette_sel)

        imgui.separator()

        # ── Vertex list ───────────────────────────────────────────────────────
        imgui.text_colored((0.9, 0.8, 0.2, 1.0), "Vertices")
        self._draw_vertex_list(imgui, polyline)

    def _draw_interval_editor(
        self, imgui, polyline: Polyline, palette_sel: Optional[str],
    ) -> None:
        imgui.text_colored((0.9, 0.8, 0.2, 1.0), "Texture Intervals")

        n_verts = len(polyline.vertices)
        max_v   = max(0, n_verts - 1)
        ivs     = polyline.texture_intervals

        to_remove: Optional[int] = None
        to_split:  Optional[tuple[int, int]] = None  # (interval_idx, at_vertex)

        # ── List existing intervals ───────────────────────────────────────────
        for i, iv in enumerate(ivs):
            imgui.push_id(i)
            tint = _IV_TINTS[i % len(_IV_TINTS)]

            # Row header: colored bullet + range
            imgui.text_colored(tint, "●")
            imgui.same_line()
            imgui.text(f"V{iv.from_vertex}–{iv.to_vertex}")

            # Texture display + assign/clear
            tex_label = (iv.texture or "(none)")
            imgui.same_line()
            imgui.text_disabled(tex_label[-14:] if len(tex_label) > 14 else tex_label)

            if palette_sel and palette_sel != iv.texture:
                if imgui.small_button("Assign"):
                    fn = self._cb.get("set_interval_texture")
                    if fn:
                        fn(polyline.id, i, palette_sel)
            if iv.texture:
                imgui.same_line()
                if imgui.small_button("Clr"):
                    fn = self._cb.get("set_interval_texture")
                    if fn:
                        fn(polyline.id, i, None)

            # x_offset
            imgui.set_next_item_width(80)
            xc, nx = imgui.input_float(f"x_off##{i}", iv.x_offset,
                                       step=0.1, format="%.1f")
            if xc:
                fn = self._cb.get("set_interval_x_offset")
                if fn:
                    fn(polyline.id, i, nx)

            # Split — [−][vertex][+] buttons flanking input_int(step=0).
            # Disabled when the interval has only 1 edge (no valid split
            # vertex exists since the split requires from < V < to).
            can_split = (iv.to_vertex - iv.from_vertex) >= 2
            if i not in self._iv_split:
                mid = (iv.from_vertex + iv.to_vertex) // 2
                self._iv_split[i] = max(iv.from_vertex + 1,
                                        min(mid, iv.to_vertex - 1))
            imgui.same_line()
            if not can_split:
                imgui.begin_disabled()
            self._iv_split[i] = self._int_stepper(
                imgui, "spv",
                self._iv_split[i],
                iv.from_vertex + 1,
                iv.to_vertex - 1,
            )
            imgui.same_line()
            if imgui.small_button("Split"):
                to_split = (i, self._iv_split[i])
            if not can_split:
                imgui.end_disabled()

            # Remove
            imgui.same_line()
            if imgui.small_button("X##ivdel"):
                to_remove = i

            imgui.pop_id()

        # Deferred mutations (only one per frame to avoid index drift)
        if to_remove is not None:
            fn = self._cb.get("remove_texture_interval")
            if fn:
                fn(polyline.id, to_remove)
            self._iv_split.pop(to_remove, None)
        elif to_split is not None:
            fn = self._cb.get("split_texture_interval")
            if fn:
                fn(polyline.id, to_split[1])

        imgui.separator()

        # ── Add new interval ──────────────────────────────────────────────────
        imgui.text("Add interval:")
        # Initialise _iv_to on first render (-1 = sentinel).
        if self._iv_to < 0:
            self._iv_to = max_v
        self._iv_from = self._int_stepper(
            imgui, "iv_from", self._iv_from, 0, max(0, max_v - 1))
        imgui.same_line()
        self._iv_to = self._int_stepper(
            imgui, "iv_to", self._iv_to, self._iv_from + 1, max_v)
        imgui.same_line()
        if imgui.small_button("Add##iv"):
            fn = self._cb.get("add_texture_interval")
            if fn:
                fn(polyline.id, self._iv_from, self._iv_to)

    # ── ARCH ──────────────────────────────────────────────────────────────────

    def _draw_arch_props(
        self, imgui, polyline: Polyline, palette_sel: Optional[str],
    ) -> None:
        # ── Position ──────────────────────────────────────────────────────────
        imgui.text_colored((0.25, 0.82, 0.91, 1.0), "Position")
        if polyline.vertices:
            px, pz = polyline.vertices[0]
            imgui.set_next_item_width(100)
            cx, nx = imgui.input_float("x##arch_px", px, format="%.2f")
            imgui.same_line()
            imgui.set_next_item_width(100)
            cz, nz = imgui.input_float("y##arch_py", pz, format="%.2f")
            if cx or cz:
                fn = self._cb.get("move_vertex")
                if fn:
                    fn(polyline.id, 0,
                       nx if cx else px,
                       nz if cz else pz)

        imgui.separator()

        # ── Orientation ───────────────────────────────────────────────────────
        imgui.text_colored((0.25, 0.82, 0.91, 1.0), "Orientation")
        is_billboard = polyline.orientation == "billboard"
        bb_changed, new_bb = imgui.checkbox("Billboard", is_billboard)
        if bb_changed:
            new_ori = "billboard" if new_bb else 0.0
            fn = self._cb.get("set_field")
            if fn:
                fn(polyline.id, "orientation", new_ori)

        if not is_billboard:
            curr_ang = float(polyline.orientation) if isinstance(
                polyline.orientation, (int, float)) else 0.0
            imgui.set_next_item_width(-1)
            ang_changed, new_ang = imgui.slider_float(
                "Angle##ori", curr_ang, 0.0, 360.0, "%.1f deg")
            if ang_changed:
                fn = self._cb.get("set_field")
                if fn:
                    fn(polyline.id, "orientation", new_ang)

        imgui.separator()

        # ── Geometry ──────────────────────────────────────────────────────────
        imgui.text_colored((0.25, 0.82, 0.91, 1.0), "Geometry")

        imgui.set_next_item_width(-1)
        w_changed, new_w = imgui.input_float(
            "Width##arch", polyline.width, step=0.1, format="%.2f")
        if w_changed:
            fn = self._cb.get("set_field")
            if fn:
                fn(polyline.id, "width", max(0.01, new_w))

        use_override = polyline.height_override is not None
        ho_changed, new_use_ho = imgui.checkbox("Override height", use_override)
        if ho_changed:
            fn = self._cb.get("set_field")
            if fn:
                fn(polyline.id, "height_override", 4.0 if new_use_ho else None)

        if use_override:
            imgui.set_next_item_width(-1)
            hov = polyline.height_override or 4.0
            hc, nh = imgui.input_float(
                "Height##arch_h", hov, step=0.1, format="%.2f")
            if hc:
                fn = self._cb.get("set_field")
                if fn:
                    fn(polyline.id, "height_override", max(0.01, nh))

        imgui.set_next_item_width(-1)
        zc, nz = imgui.input_float(
            "Z offset##arch", polyline.z_offset, step=0.05, format="%.2f")
        if zc:
            fn = self._cb.get("set_field")
            if fn:
                fn(polyline.id, "z_offset", nz)

        vc, nv = imgui.checkbox("V=0 at floor", polyline.v_at_floor)
        if vc:
            fn = self._cb.get("set_field")
            if fn:
                fn(polyline.id, "v_at_floor", nv)

        imgui.separator()

        # ── Texture & transparency ────────────────────────────────────────────
        imgui.text_colored((0.25, 0.82, 0.91, 1.0), "Texture")
        tex_label = polyline.texture or "(none)"
        imgui.text(tex_label[-26:])

        if palette_sel and palette_sel != polyline.texture:
            if imgui.button(f"Assign '{palette_sel[-16:]}'"):
                fn = self._cb.get("set_texture")
                if fn:
                    fn(polyline.id, palette_sel)

        if polyline.texture:
            imgui.same_line()
            if imgui.button("Clear##arch_tex"):
                fn = self._cb.get("set_texture")
                if fn:
                    fn(polyline.id, None)

        try:
            trans_idx = _TRANS_VALUES.index(polyline.transparency)
        except ValueError:
            trans_idx = 1

        imgui.set_next_item_width(-1)
        tc, ni = imgui.combo("Transparency##arch", trans_idx, _TRANS_LABELS)
        if tc:
            fn = self._cb.get("set_field")
            if fn:
                fn(polyline.id, "transparency", _TRANS_VALUES[ni])

        imgui.separator()

        # ── Light source ──────────────────────────────────────────────────────
        lc, nl = imgui.checkbox("Light source", polyline.is_light_source)
        if lc:
            fn = self._cb.get("set_field")
            if fn:
                fn(polyline.id, "is_light_source", nl)

        if polyline.is_light_source:
            imgui.text_colored((1.0, 0.85, 0.4, 1.0), "Light")
            imgui.set_next_item_width(-1)
            cc, nc = imgui.color_edit3("Color##lc", polyline.light_color)
            if cc:
                fn = self._cb.get("set_field")
                if fn:
                    fn(polyline.id, "light_color", tuple(nc))

            imgui.set_next_item_width(-1)
            ic, ni2 = imgui.slider_float(
                "Intensity##li", polyline.light_intensity,
                0.0, 10.0, "%.2f")
            if ic:
                fn = self._cb.get("set_field")
                if fn:
                    fn(polyline.id, "light_intensity", ni2)

    # ── EYEPATH ───────────────────────────────────────────────────────────────

    def _draw_eyepath_props(self, imgui, polyline: Polyline) -> None:
        imgui.text_colored((0.28, 0.91, 0.50, 1.0), "EyePath")
        imgui.text(f"Vertices: {len(polyline.vertices)}")

        # ── Edge editor ───────────────────────────────────────────────────────
        imgui.separator()
        imgui.text_colored((0.28, 0.91, 0.50, 1.0), "Edges")

        to_remove_edge: Optional[tuple[int, int]] = None
        for i, (vi, vj) in enumerate(polyline.edges):
            imgui.push_id(i)
            imgui.text(f"V{vi} \u2192 V{vj}")
            imgui.same_line()
            if imgui.small_button("X##edge"):
                to_remove_edge = (vi, vj)
            imgui.pop_id()

        if to_remove_edge is not None:
            fn = self._cb.get("remove_eyepath_edge")
            if fn:
                fn(polyline.id, *to_remove_edge)

        # Add edge — [−][vertex][+] stepper buttons for reliable clicks.
        imgui.text("Add:")
        max_v = max(0, len(polyline.vertices) - 1)
        self._ep_from = self._int_stepper(
            imgui, "ep_from", self._ep_from, 0, max_v)
        imgui.same_line()
        self._ep_to = self._int_stepper(
            imgui, "ep_to", self._ep_to, 0, max_v)
        imgui.same_line()
        if imgui.small_button("Add##epedge"):
            if self._ep_from != self._ep_to:
                fn = self._cb.get("add_eyepath_edge")
                if fn:
                    fn(polyline.id, self._ep_from, self._ep_to)

        # ── Vertex list ───────────────────────────────────────────────────────
        imgui.separator()
        imgui.text_colored((0.28, 0.91, 0.50, 1.0), "Vertices")
        self._draw_vertex_list(imgui, polyline)

        # ── Render Preview section ────────────────────────────────────────────
        if self._selected_vertex_idx is not None and self._selected_vertex_idx < len(polyline.vertices):
            v_idx = self._selected_vertex_idx
            imgui.separator()
            imgui.text_colored((0.28, 0.91, 0.50, 1.0), f"Preview Vertex V{v_idx}")
            
            # Find neighbors of this vertex
            neighbors = []
            for vi, vj in polyline.edges:
                if vi == v_idx:
                    neighbors.append(vj)
                elif vj == v_idx:
                    neighbors.append(vi)
            neighbors = sorted(list(set(neighbors)))
            
            if not neighbors:
                imgui.text_disabled("No connected neighbors to look toward.")
            else:
                # Dropdown to choose which connected neighbor to look toward
                if getattr(self, "_preview_target_idx", -1) not in neighbors:
                    self._preview_target_idx = neighbors[0]
                
                labels = [f"V{n}" for n in neighbors]
                try:
                    curr_sel = neighbors.index(self._preview_target_idx)
                except ValueError:
                    curr_sel = 0
                    self._preview_target_idx = neighbors[0]
                
                changed, new_sel = imgui.combo("Look Toward", curr_sel, labels)
                if changed:
                    self._preview_target_idx = neighbors[new_sel]
                    # Clear image on target change
                    self._preview_image_ref = None
                
                if imgui.button("Render Preview", (-1, 0)):
                    fn = self._cb.get("render_preview")
                    if fn:
                        fn(polyline.id, v_idx, self._preview_target_idx)
                        
            if self._preview_image_ref is not None:
                imgui.separator()
                imgui.text("Preview:")
                # Display 3D preview image (aspect ratio 4:3, fit in properties panel width)
                # PROPS_PANEL_W is 320, minus padding is 304 width, 228 height
                imgui.image(self._preview_image_ref, (304, 228))

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _draw_vertex_list(self, imgui, polyline: Polyline) -> None:
        to_delete: Optional[int] = None

        for i, (vx, vz) in enumerate(polyline.vertices):
            imgui.push_id(i)

            # If the polyline is an eyepath, make the vertex select-clickable
            if polyline.type == PolylineType.EYEPATH:
                is_selected = (self._selected_vertex_idx == i)
                if is_selected:
                    imgui.push_style_color(imgui.Col_.button.value, (0.2, 0.7, 0.3, 1.0))
                if imgui.small_button(f"[{i}]##sel"):
                    self._selected_vertex_idx = i
                    self._preview_image_ref = None
                if is_selected:
                    imgui.pop_style_color()
            else:
                imgui.text(f"[{i}]")
            imgui.same_line()
            imgui.set_next_item_width(85)
            cx, nx = imgui.input_float(f"x##{i}", vx, format="%.2f")
            imgui.same_line()
            imgui.set_next_item_width(85)
            cz, nz = imgui.input_float(f"y##{i}", vz, format="%.2f")

            if cx or cz:
                fn = self._cb.get("move_vertex")
                if fn:
                    fn(polyline.id, i,
                       nx if cx else vx,
                       nz if cz else vz)

            imgui.same_line()
            if imgui.button("X"):
                to_delete = i

            imgui.pop_id()

        if to_delete is not None:
            fn = self._cb.get("del_vertex")
            if fn:
                fn(polyline.id, to_delete)

    def _draw_level_meta(self, imgui, level: Level, palette_sel: Optional[str]) -> None:
        imgui.text_colored((0.28, 0.91, 0.50, 1.0), "Level Properties")
        imgui.separator()

        m = level.meta
        fn = self._cb.get("set_meta_field")

        # Identity
        imgui.text("Name:")
        imgui.set_next_item_width(-1)
        changed, name_val = imgui.input_text("##meta_name", m.name)
        if changed and fn:
            fn("name", name_val)

        imgui.text("Author:")
        imgui.set_next_item_width(-1)
        changed, author_val = imgui.input_text("##meta_author", m.author)
        if changed and fn:
            fn("author", author_val)

        imgui.separator()
        imgui.text_colored((0.28, 0.91, 0.50, 1.0), "3D Geometry")

        # wall_height
        imgui.text("Wall Height:")
        imgui.same_line()
        changed, h_val = imgui.input_float("##meta_wh", m.wall_height, format="%.2f")
        if changed and fn:
            fn("wall_height", max(0.1, h_val))

        # eye_height
        imgui.text("Eye Height:")
        imgui.same_line()
        changed, e_val = imgui.input_float("##meta_eh", m.eye_height, format="%.2f")
        if changed and fn:
            fn("eye_height", max(0.1, e_val))

        # fov_h / fov_v
        imgui.text("FOV Horiz / Vert:")
        imgui.set_next_item_width(80)
        changed_h, fh_val = imgui.input_float("##meta_fovh", m.fov_h, format="%.1f")
        imgui.same_line()
        imgui.set_next_item_width(80)
        changed_v, fv_val = imgui.input_float("##meta_fovv", m.fov_v, format="%.1f")
        if changed_h and fn:
            fn("fov_h", max(1.0, min(179.0, fh_val)))
        if changed_v and fn:
            fn("fov_v", max(1.0, min(179.0, fv_val)))

        # pixels_per_meter
        imgui.text("Pixels/Meter:")
        imgui.same_line()
        changed, ppm_val = imgui.input_float("##meta_ppm", m.pixels_per_meter, format="%.1f")
        if changed and fn:
            fn("pixels_per_meter", max(1.0, ppm_val))

        imgui.separator()
        imgui.text_colored((0.28, 0.91, 0.50, 1.0), "Fog Settings")

        # fog_start / fog_end
        imgui.text("Fog Start / End:")
        imgui.set_next_item_width(80)
        changed_fs, fs_val = imgui.input_float("##meta_fogs", m.fog_start, format="%.1f")
        imgui.same_line()
        imgui.set_next_item_width(80)
        changed_fe, fe_val = imgui.input_float("##meta_foge", m.fog_end, format="%.1f")
        if changed_fs and fn:
            fn("fog_start", max(0.0, fs_val))
        if changed_fe and fn:
            fn("fog_end", max(0.0, fe_val))

        imgui.separator()
        imgui.text_colored((0.28, 0.91, 0.50, 1.0), "Editor Settings")

        # snap_grid
        imgui.text("Snap Grid:")
        imgui.same_line()
        changed, sg_val = imgui.input_float("##meta_sg", m.snap_grid, format="%.3f")
        if changed and fn:
            fn("snap_grid", max(0.001, sg_val))

        imgui.separator()
        imgui.text_colored((0.28, 0.91, 0.50, 1.0), "Render Resolution")

        # render_width / render_height
        imgui.text("Width / Height:")
        imgui.set_next_item_width(80)
        changed_rw, rw_val = imgui.input_int("##meta_rw", m.render_width)
        imgui.same_line()
        imgui.set_next_item_width(80)
        changed_rh, rh_val = imgui.input_int("##meta_rh", m.render_height)
        if changed_rw and fn:
            fn("render_width", max(1, rw_val))
        if changed_rh and fn:
            fn("render_height", max(1, rh_val))

        imgui.separator()

        imgui.text_colored((0.28, 0.91, 0.50, 1.0), "Textures")

        # Floor texture
        imgui.text("Floor Texture:")
        fl_tex = m.floor_texture or "(none)"
        imgui.text_disabled(fl_tex[-26:])
        if palette_sel and palette_sel != m.floor_texture:
            imgui.same_line()
            if imgui.button("Assign##floor"):
                if fn:
                    fn("floor_texture", palette_sel)
        if m.floor_texture:
            imgui.same_line()
            if imgui.button("Clear##floor"):
                if fn:
                    fn("floor_texture", None)

        # Ceiling texture
        imgui.text("Ceiling Texture:")
        cl_tex = m.ceiling_texture or "(none)"
        imgui.text_disabled(cl_tex[-26:])
        if palette_sel and palette_sel != m.ceiling_texture:
            imgui.same_line()
            if imgui.button("Assign##ceiling"):
                if fn:
                    fn("ceiling_texture", palette_sel)
        if m.ceiling_texture:
            imgui.same_line()
            if imgui.button("Clear##ceiling"):
                if fn:
                    fn("ceiling_texture", None)
