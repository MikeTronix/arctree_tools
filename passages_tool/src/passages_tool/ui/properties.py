"""
ui/properties.py
────────────────
Properties inspector panel — Dear ImGui sidebar for the selected polyline.

Type-specific sections (v3 — Phase 3 complete)
───────────────────────────────────────────────
  WALL     Type selector; closed toggle; full texture-interval editor
           (assign texture from palette, set x_offset, split, remove,
           add new interval); vertex list.

  ARCH     Type selector; position; orientation; dressing (kind / profile /
           depth / side texture); texture; transparency; light source.

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
)
from passages_tool.editor.level import Level, Polyline, PolylineType
from passages_tool.ui.scale import overlay_layout, overlay_top_px, scaled_px


_TYPE_LABELS = ["Wall", "Arch", "EyePath", "Anchor"]
_TYPE_VALUES = ["wall", "arch", "eyepath", "anchor"]
_TRANS_LABELS = ["None", "Alpha test", "Alpha blend"]
_TRANS_VALUES = ["none", "alpha_test", "alpha_blend"]
_KIND_LABELS = ["Card", "Opening", "Niche", "Volume", "Recess"]
_KIND_VALUES = [None, "opening", "niche", "volume", "recess"]
_PROFILE_LABELS = ["(style default)", "Rect", "Round", "Gothic"]
_PROFILE_VALUES = [None, "rect", "round", "gothic"]
_CEIL_MODE_LABELS = ["(style default)", "Closed", "None (no roof)"]
_CEIL_MODE_VALUES = [None, "closed", "none"]

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
        self._ui_scale: float = 1.0

    def _px(self, base: float) -> float:
        return scaled_px(base, self._ui_scale)

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
        imgui.set_next_item_width(self._px(width))
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
        ui_scale:    float = 1.0,
        menu_bar_h:  float = 0.0,
    ) -> None:
        """Render the properties panel. Must be called inside an imgui frame."""
        try:
            from imgui_bundle import imgui
        except ImportError:
            return

        self._ui_scale = ui_scale

        # Reset selected vertex preview state if the selected polyline changes
        cur_id = polyline.id if polyline else None
        if getattr(self, "_last_polyline_id", None) != cur_id:
            self._last_polyline_id = cur_id
            self._selected_vertex_idx = None
            self._preview_image_ref = None

        display_w = imgui.get_io().display_size.x
        display_h = imgui.get_io().display_size.y
        bar_guess = menu_bar_h if menu_bar_h > 1.0 else overlay_top_px(imgui, ui_scale)
        bar_h, _pal_w, panel_w, panel_h = overlay_layout(
            display_w, display_h, ui_scale, bar_guess
        )

        always      = imgui.Cond_.always.value
        no_move     = imgui.WindowFlags_.no_move.value
        no_resize   = imgui.WindowFlags_.no_resize.value
        no_collapse = imgui.WindowFlags_.no_collapse.value

        imgui.set_next_window_size((panel_w, panel_h), always)
        imgui.set_next_window_pos((display_w - panel_w, bar_h), always)

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
            self._draw_arch_props(imgui, polyline, palette_sel, level)
        elif t == PolylineType.EYEPATH:
            self._draw_eyepath_props(imgui, polyline)
        elif t == PolylineType.ANCHOR:
            self._draw_anchor_props(imgui, polyline)

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
            imgui.set_next_item_width(self._px(80))
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
        level: Optional[Level] = None,
    ) -> None:
        # ── Position ──────────────────────────────────────────────────────────
        imgui.text_colored((0.25, 0.82, 0.91, 1.0), "Position")
        if polyline.vertices:
            px, pz = polyline.vertices[0]
            imgui.set_next_item_width(self._px(100))
            cx, nx = imgui.input_float("x##arch_px", px, format="%.2f")
            imgui.same_line()
            imgui.set_next_item_width(self._px(100))
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
            imgui.text("Angle")
            imgui.set_next_item_width(-1)
            ang_changed, new_ang = imgui.slider_float(
                "##ori", curr_ang, 0.0, 360.0, "%.1f deg")
            if ang_changed:
                fn = self._cb.get("set_field")
                if fn:
                    fn(polyline.id, "orientation", new_ang)

        imgui.separator()

        # ── Geometry ──────────────────────────────────────────────────────────
        imgui.text_colored((0.25, 0.82, 0.91, 1.0), "Geometry")

        is_billboard = (polyline.orientation == "billboard")
        auto_snap_val = False

        if not is_billboard:
            auto_snap_val = getattr(polyline, "auto_snap", False)
            as_changed, new_as = imgui.checkbox("Auto-snap to walls", auto_snap_val)
            if as_changed:
                fn = self._cb.get("set_field")
                if fn:
                    fn(polyline.id, "auto_snap", new_as)
            
            if auto_snap_val:
                if level is not None:
                    try:
                        from passages_tool.converter.arch_builder import find_snap_points
                        try:
                            theta_deg = float(polyline.orientation)
                        except (ValueError, TypeError):
                            theta_deg = 0.0
                        _, _, snap_w, _, _ = find_snap_points(
                            level, polyline.position, theta_deg
                        )
                        if abs(snap_w - polyline.width) > 1e-4:
                            fn = self._cb.get("set_field")
                            if fn:
                                fn(polyline.id, "width", snap_w)
                    except (ValueError, TypeError, ArithmeticError):
                        pass
                imgui.text(f"Width (snapped): {polyline.width:.2f} m")

        if is_billboard or not auto_snap_val:
            imgui.text("Width (m)")
            imgui.set_next_item_width(-1)
            w_changed, new_w = imgui.input_float(
                "##arch_w", polyline.width, step=0.1, format="%.2f")
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
            imgui.text("Height (m)")
            imgui.set_next_item_width(-1)
            hov = polyline.height_override or 4.0
            hc, nh = imgui.input_float(
                "##arch_h", hov, step=0.1, format="%.2f")
            if hc:
                fn = self._cb.get("set_field")
                if fn:
                    fn(polyline.id, "height_override", max(0.01, nh))

        imgui.text("Z offset (m)")
        imgui.set_next_item_width(-1)
        zc, nz = imgui.input_float(
            "##arch_z", polyline.z_offset, step=0.05, format="%.2f")
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

        # ── Dressing (style openings / niches / volumes / recesses) ───────────
        imgui.text_colored((0.25, 0.82, 0.91, 1.0), "Dressing")
        if is_billboard:
            imgui.text_disabled("Fixed angle required (uncheck Billboard).")
        else:
            raw_kind = getattr(polyline, "kind", None) or None
            try:
                kind_idx = _KIND_VALUES.index(raw_kind)
            except ValueError:
                kind_idx = 0
            imgui.text("Kind")
            imgui.set_next_item_width(-1)
            kc, kni = imgui.combo("##arch_kind", kind_idx, _KIND_LABELS)
            if kc:
                fn = self._cb.get("set_field")
                if fn:
                    new_kind = _KIND_VALUES[kni]
                    fn(polyline.id, "kind", new_kind)
                    # Card + leftover depth_m would still bake as an opening.
                    if new_kind is None:
                        fn(polyline.id, "depth_m", None)
            kind = _KIND_VALUES[kni] if kc else raw_kind

            if kind in ("opening", "recess"):
                raw_prof = getattr(polyline, "profile", None) or None
                try:
                    pidx = _PROFILE_VALUES.index(raw_prof)
                except ValueError:
                    pidx = 0
                imgui.text("Profile")
                imgui.set_next_item_width(-1)
                pc, pni = imgui.combo("##arch_prof", pidx, _PROFILE_LABELS)
                if pc:
                    fn = self._cb.get("set_field")
                    if fn:
                        fn(polyline.id, "profile", _PROFILE_VALUES[pni])

            if kind in ("opening", "volume", "recess"):
                shown_d = getattr(polyline, "depth_m", None)
                shown_d = float(shown_d) if shown_d is not None else 0.4
                imgui.text("Depth (m)")
                imgui.set_next_item_width(-1)
                dc, nd = imgui.input_float(
                    "##arch_depth", shown_d, step=0.05, format="%.2f")
                if dc:
                    fn = self._cb.get("set_field")
                    if fn:
                        fn(polyline.id, "depth_m", max(0.05, nd))

            if kind in ("opening", "volume", "recess"):
                side = getattr(polyline, "side_texture", None)
                imgui.text("Side texture")
                imgui.text_disabled((side or "(style / front)")[-26:])
                if palette_sel and palette_sel != side:
                    if imgui.button("Assign side"):
                        fn = self._cb.get("set_field")
                        if fn:
                            fn(polyline.id, "side_texture", palette_sel)
                if side:
                    imgui.same_line()
                    if imgui.button("Clear##side"):
                        fn = self._cb.get("set_field")
                        if fn:
                            fn(polyline.id, "side_texture", None)

            if kind == "niche":
                imgui.text_disabled("Needs a style pack (unique wall maps + POM).")
            if kind == "volume":
                imgui.text_disabled("Keep width modest (not the 4 m door default).")

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

        imgui.text("Transparency")
        imgui.set_next_item_width(-1)
        tc, ni = imgui.combo("##arch_trans", trans_idx, _TRANS_LABELS)
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
            imgui.text("Color")
            imgui.set_next_item_width(-1)
            cc, nc = imgui.color_edit3("##lc", polyline.light_color)
            if cc:
                fn = self._cb.get("set_field")
                if fn:
                    fn(polyline.id, "light_color", tuple(nc))

            imgui.text("Intensity")
            imgui.set_next_item_width(-1)
            ic, ni2 = imgui.slider_float(
                "##li", polyline.light_intensity,
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
                avail_w = imgui.get_content_region_avail().x
                imgui.image(self._preview_image_ref, (avail_w, avail_w * 9.0 / 16.0))

    # ── ANCHOR ────────────────────────────────────────────────────────────────

    def _draw_anchor_props(self, imgui, polyline: Polyline) -> None:
        # ── Position ──────────────────────────────────────────────────────────
        imgui.text_colored((0.72, 0.64, 1.00, 1.0), "Position")
        if polyline.vertices:
            px, pz = polyline.vertices[0]
            imgui.set_next_item_width(self._px(100))
            cx, nx = imgui.input_float("x##anchor_px", px, format="%.2f")
            imgui.same_line()
            imgui.set_next_item_width(self._px(100))
            cz, nz = imgui.input_float("y##anchor_py", pz, format="%.2f")
            if cx or cz:
                fn = self._cb.get("move_vertex")
                if fn:
                    fn(polyline.id, 0,
                       nx if cx else px,
                       nz if cz else pz)

        imgui.separator()

        # ── Anchor Settings ───────────────────────────────────────────────────
        imgui.text_colored((0.72, 0.64, 1.00, 1.0), "Settings")

        # Radius
        imgui.text("Radius (footprint, m)")
        imgui.set_next_item_width(-1)
        r_changed, new_r = imgui.input_float(
            "##anchor_radius", polyline.radius, step=0.1, format="%.2f")
        if r_changed:
            fn = self._cb.get("set_field")
            if fn:
                fn(polyline.id, "radius", max(0.01, new_r))

        # height (nominal extent — vertical size of the visibility sample grid)
        imgui.text("Height (extent, m)")
        imgui.set_next_item_width(-1)
        h_changed, new_h = imgui.input_float(
            "##anchor_height", polyline.height, step=0.1, format="%.2f")
        if h_changed:
            fn = self._cb.get("set_field")
            if fn:
                fn(polyline.id, "height", max(0.01, new_h))

        # height offset (z_offset)
        imgui.text("Height Offset (lift base, m)")
        imgui.set_next_item_width(-1)
        z_changed, new_z = imgui.input_float(
            "##anchor_zoff", polyline.z_offset, step=0.1, format="%.2f")
        if z_changed:
            fn = self._cb.get("set_field")
            if fn:
                fn(polyline.id, "z_offset", new_z)

        # max_distance
        imgui.text("Max Distance (render cutoff, m)")
        imgui.set_next_item_width(-1)
        md_changed, new_md = imgui.input_float(
            "##anchor_maxdist", polyline.max_distance, step=0.5, format="%.1f")
        if md_changed:
            fn = self._cb.get("set_field")
            if fn:
                fn(polyline.id, "max_distance", max(0.1, new_md))

        # fov_limit (None vs float)
        use_fov_limit = polyline.fov_limit is not None
        fl_toggle_changed, new_use_fl = imgui.checkbox("Limit horizontal angle", use_fov_limit)
        if fl_toggle_changed:
            fn = self._cb.get("set_field")
            if fn:
                fn(polyline.id, "fov_limit", 45.0 if new_use_fl else None)

        if use_fov_limit:
            curr_fl = float(polyline.fov_limit) if polyline.fov_limit is not None else 45.0
            imgui.text("Max Angle Offset")
            imgui.set_next_item_width(-1)
            fl_changed, new_fl = imgui.slider_float(
                "##anchor_fov", curr_fl, 1.0, 180.0, "%.1f deg")
            if fl_changed:
                fn = self._cb.get("set_field")
                if fn:
                    fn(polyline.id, "fov_limit", new_fl)

        # sprite_count
        imgui.text("Sprite Capacity")
        imgui.set_next_item_width(-1)
        sc_changed, new_sc = imgui.input_int("##anchor_sprcount", polyline.sprite_count)
        if sc_changed:
            fn = self._cb.get("set_field")
            if fn:
                fn(polyline.id, "sprite_count", max(1, new_sc))

        # tags
        imgui.text("Tags (comma separated)")
        imgui.set_next_item_width(-1)
        tags_str = ", ".join(polyline.tags)
        tags_changed, new_tags_str = imgui.input_text(
            "##anchor_tags", tags_str)
        if tags_changed:
            fn = self._cb.get("set_field")
            if fn:
                tags_list = [t.strip() for t in new_tags_str.split(",") if t.strip()]
                fn(polyline.id, "tags", tags_list)

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _draw_vertex_list(self, imgui, polyline: Polyline) -> None:
        to_delete: Optional[int] = None
        to_insert: Optional[tuple[int, float, float]] = None

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
            imgui.set_next_item_width(self._px(85))
            cx, nx = imgui.input_float(f"x##{i}", vx, format="%.2f")
            imgui.same_line()
            imgui.set_next_item_width(self._px(85))
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

            # Insert a vertex on the edge leaving this one (midpoint), then the
            # artist drags it into place. Wraps for closed polygons; skipped on
            # the last vertex of an open polyline (no edge to split).
            n = len(polyline.vertices)
            nxt = (i + 1) % n if polyline.closed else i + 1
            if nxt < n:
                imgui.same_line()
                if imgui.button("Ins"):
                    nvx, nvz = polyline.vertices[nxt]
                    to_insert = (i, (vx + nvx) / 2.0, (vz + nvz) / 2.0)

            imgui.pop_id()

        if to_delete is not None:
            fn = self._cb.get("del_vertex")
            if fn:
                fn(polyline.id, to_delete)

        if to_insert is not None:
            fn = self._cb.get("insert_vertex")
            if fn:
                fn(polyline.id, to_insert[0], to_insert[1], to_insert[2])

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

        # fov_v is authored; fov_h is derived from VFOV × render aspect.
        imgui.text("FOV Vertical:")
        imgui.same_line()
        imgui.set_next_item_width(self._px(80))
        changed_v, fv_val = imgui.input_float("##meta_fovv", m.fov_v, format="%.1f")
        if changed_v and fn:
            fn("fov_v", max(1.0, min(179.0, fv_val)))
        from passages_tool.config import derived_fov_h
        derived_h = derived_fov_h(m.fov_v, m.render_width, m.render_height)
        imgui.text_disabled(
            f"FOV Horiz (from V + {m.render_width}×{m.render_height}): {derived_h:.1f}°"
        )

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
        imgui.set_next_item_width(self._px(80))
        changed_fs, fs_val = imgui.input_float("##meta_fogs", m.fog_start, format="%.1f")
        imgui.same_line()
        imgui.set_next_item_width(self._px(80))
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
        imgui.set_next_item_width(self._px(80))
        changed_rw, rw_val = imgui.input_int("##meta_rw", m.render_width)
        imgui.same_line()
        imgui.set_next_item_width(self._px(80))
        changed_rh, rh_val = imgui.input_int("##meta_rh", m.render_height)
        if changed_rw and fn:
            fn("render_width", max(1, rw_val))
        if changed_rh and fn:
            fn("render_height", max(1, rh_val))

        imgui.separator()
        imgui.text_colored((0.28, 0.91, 0.50, 1.0), "Style dressing")

        style_ids: list[str] = []
        list_fn = self._cb.get("list_styles")
        if list_fn:
            try:
                style_ids = list(list_fn() or [])
            except Exception:
                style_ids = []
        style_labels = ["(none)"] + style_ids
        cur_style = (m.style or "").strip()
        if cur_style and cur_style not in style_ids:
            style_labels.append(cur_style)
        try:
            sidx = style_labels.index(cur_style) if cur_style else 0
        except ValueError:
            sidx = 0
        imgui.text("Style")
        imgui.set_next_item_width(-1)
        sc, sni = imgui.combo("##meta_style", sidx, style_labels)
        if sc and fn:
            fn("style", None if sni == 0 else style_labels[sni])
        if not style_ids:
            imgui.text_disabled("No styles/*.json in the texture folder.")

        pom_on = bool(getattr(m, "pom_enabled", False))
        pc, npom = imgui.checkbox("POM enabled", pom_on)
        if pc and fn:
            fn("pom_enabled", bool(npom))

        use_seed = m.overlay_seed is not None
        oc, nuse = imgui.checkbox("Override overlay seed", use_seed)
        if oc and fn:
            fn("overlay_seed", 0 if nuse else None)
        if m.overlay_seed is not None:
            imgui.text("Overlay seed")
            imgui.set_next_item_width(-1)
            ic, nseed = imgui.input_int("##meta_oseed", int(m.overlay_seed))
            if ic and fn:
                fn("overlay_seed", int(nseed))

        raw_cm = getattr(m, "ceiling_mode", None)
        try:
            cidx = _CEIL_MODE_VALUES.index(raw_cm)
        except ValueError:
            cidx = 0
        imgui.text("Ceiling")
        imgui.set_next_item_width(-1)
        cc, cni = imgui.combo("##meta_cmode", cidx, _CEIL_MODE_LABELS)
        if cc and fn:
            fn("ceiling_mode", _CEIL_MODE_VALUES[cni])

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
