"""
editor/polyline.py
──────────────────
Scene-graph representation of a single Polyline — type-aware (v2).

Each PolylineNode owns:
  - One PandaNode parent (self._geo_np) that groups all decorative geometry.
  - N CardMaker quads as draggable vertex handles (direct children of render_root
    so hit-testing tags remain reachable at the top level).

Visual conventions by type
──────────────────────────
  WALL     Warm-yellow line + exterior hatch ticks (one per edge midpoint,
           pointing LEFT when traversing vertices in creation order — that
           side is the exterior; the interior / right-hand side is unticked).

  ARCH     Cyan.  A single vertex = placement position.
           - Billboard: horizontal bar of pl.width + asterisk spokes indicating
             "can spin to face camera".
           - Fixed angle: bar at that angle + perpendicular cap ticks at ends.

  EYEPATH  Spring-green.  Vertices as handles, directed edges drawn with
           arrowheads.  If no edges are defined yet, consecutive vertices are
           connected with a plain line so the artist can see the layout.

Usage
─────
    pn = PolylineNode(render_root, polyline_data, selected=False)
    pn.rebuild()          # call after any vertex or field mutation
    pn.set_selected(True)
    pn.destroy()
"""
from __future__ import annotations

import math
from typing import Optional

from panda3d.core import (
    CardMaker,
    LColor,
    LineSegs,
    NodePath,
    PandaNode,
    TransparencyAttrib,
)

from passages_tool.config import (
    ARROW_HEAD_SIZE,
    COLOR_ARCH,
    COLOR_ARCH_SELECTED,
    COLOR_EYEPATH,
    COLOR_EYEPATH_SEL,
    COLOR_WALL,
    COLOR_WALL_NO_INTERVAL,
    COLOR_WALL_SELECTED,
    HATCH_LENGTH,
    HATCH_MIN_EDGE,
    INTERVAL_COLORS,
    POLYLINE_THICKNESS,
    VERTEX_HANDLE_RADIUS,
    VERTEX_HANDLE_SEL_COLOR,
)
from passages_tool.editor.level import Polyline, PolylineType


# ── PolylineNode ──────────────────────────────────────────────────────────────

class PolylineNode:
    """
    Panda3D scene objects for one Polyline data object.

    The caller is responsible for calling rebuild() after any mutation to
    the underlying Polyline data, and destroy() when the polyline is removed.
    """

    def __init__(
        self,
        render_root: NodePath,
        data: Polyline,
        selected: bool = False,
    ) -> None:
        self._root     = render_root
        self._data     = data
        self._selected = selected
        self._highlighted_error = False

        # _geo_np parents all decorative line geometry.
        # _handle_nps are direct children of render_root (needed for hit tags).
        self._geo_np:    Optional[NodePath] = None
        self._handle_nps: list[NodePath]    = []

        self.rebuild()

    # ── Public API ────────────────────────────────────────────────────────────

    def rebuild(self) -> None:
        """Destroy and recreate all scene objects from self._data."""
        self._destroy_scene()

        if not self._data.vertices:
            return

        # Create parent node that groups all decorative geometry.
        self._geo_np = self._root.attachNewNode(PandaNode(f"pl_{self._data.id}"))

        t = self._data.type
        if t == PolylineType.WALL:
            self._build_wall()
        elif t == PolylineType.ARCH:
            self._build_arch()
        elif t == PolylineType.EYEPATH:
            self._build_eyepath()
        else:
            self._build_wall()   # safe fallback

        self._build_handles()

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self.rebuild()

    def set_highlighted_error(self, value: bool) -> None:
        if self._highlighted_error != value:
            self._highlighted_error = value
            self.rebuild()

    @property
    def data(self) -> Polyline:
        return self._data

    def destroy(self) -> None:
        self._destroy_scene()

    # ── Type-specific geometry builders ───────────────────────────────────────

    def _build_wall(self) -> None:
        verts = self._data.vertices
        if not verts:
            return

        base_color = COLOR_WALL_SELECTED if self._selected else COLOR_WALL
        intervals  = self._data.texture_intervals
        has_ivs    = bool(intervals)

        def _edge_color(edge_idx: int) -> tuple:
            """Return the display color for edge (edge_idx → edge_idx+1)."""
            for n, iv in enumerate(intervals):
                if iv.from_vertex <= edge_idx < iv.to_vertex:
                    return INTERVAL_COLORS[n % len(INTERVAL_COLORS)]
            # No interval covers this edge.
            return COLOR_WALL_NO_INTERVAL if has_ivs else base_color

        # ── Main edge path ────────────────────────────────────────────────────
        if len(verts) >= 2:
            segs = LineSegs("wall_main")
            segs.setThickness(POLYLINE_THICKNESS)

            edge_pairs: list[tuple[int, tuple, tuple]] = []
            for i in range(len(verts) - 1):
                edge_pairs.append((i, verts[i], verts[i + 1]))
            if self._data.closed and len(verts) >= 3:
                edge_pairs.append((len(verts) - 1, verts[-1], verts[0]))

            for edge_idx, (ax, az), (bx, bz) in edge_pairs:
                col = _edge_color(edge_idx)
                segs.setColor(LColor(*col))
                segs.moveTo(ax, 0, az)
                segs.drawTo(bx, 0, bz)

            np = self._geo_np.attachNewNode(segs.create(dynamic=True))
            np.setBin("opaque", 1)

        # ── Exterior hatch ticks (always in base wall colour) ───────────────
        if len(verts) >= 2:
            pairs = list(zip(verts, verts[1:]))
            if self._data.closed and len(verts) >= 3:
                pairs.append((verts[-1], verts[0]))

            hsegs = LineSegs("wall_hatch")
            hsegs.setThickness(1.5)
            hsegs.setColor(LColor(*base_color))

            drew_any = False
            for (ax, az), (bx, bz) in pairs:
                dx, dz   = bx - ax, bz - az
                edge_len = math.hypot(dx, dz)
                if edge_len < HATCH_MIN_EDGE:
                    continue
                lx, lz = -dz / edge_len, dx / edge_len
                mx, mz = (ax + bx) * 0.5, (az + bz) * 0.5
                hsegs.moveTo(mx, 0, mz)
                hsegs.drawTo(mx + lx * HATCH_LENGTH, 0, mz + lz * HATCH_LENGTH)
                drew_any = True

            if drew_any:
                hnp = self._geo_np.attachNewNode(hsegs.create(dynamic=True))
                hnp.setBin("opaque", 1)

    def _build_arch(self) -> None:
        verts = self._data.vertices
        if not verts:
            return

        color  = (1.0, 0.2, 0.2, 1.0) if self._highlighted_error else (COLOR_ARCH_SELECTED if self._selected else COLOR_ARCH)
        px, pz = verts[0]
        half_w = self._data.width * 0.5

        segs = LineSegs("arch_main")
        segs.setThickness(POLYLINE_THICKNESS)
        segs.setColor(LColor(*color))

        if self._data.orientation == "billboard":
            # Horizontal bar
            segs.moveTo(px - half_w, 0, pz)
            segs.drawTo(px + half_w, 0, pz)
            # Four short "sweep" spokes radiating from centre — indicates
            # the arch can rotate to face the camera.
            spoke_r = min(half_w * 0.55, 0.4)
            for deg in (45, 135, 225, 315):
                rad = math.radians(deg)
                sx, sz = math.cos(rad) * spoke_r, math.sin(rad) * spoke_r
                segs.moveTo(px, 0, pz)
                segs.drawTo(px + sx, 0, pz + sz)
        else:
            # Bar perpendicular to the facing orientation angle
            ang = math.radians(float(self._data.orientation) + 90.0)
            dx  = math.cos(ang) * half_w
            dz  = math.sin(ang) * half_w
            segs.moveTo(px - dx, 0, pz - dz)
            segs.drawTo(px + dx, 0, pz + dz)

            # Ticks at each end run parallel to normal (facing angle)
            cap  = HATCH_LENGTH * 0.6
            pdx  = -math.sin(ang) * cap
            pdz  =  math.cos(ang) * cap
            for ex, ez in ((px - dx, pz - dz), (px + dx, pz + dz)):
                segs.moveTo(ex - pdx, 0, ez - pdz)
                segs.drawTo(ex + pdx, 0, ez + pdz)

        np = self._geo_np.attachNewNode(segs.create(dynamic=True))
        np.setBin("opaque", 1)

        # Draw warning diamond if warning is active
        if self._data.warning:
            wsegs = LineSegs("arch_warning")
            wsegs.setThickness(2.0)
            wsegs.setColor(LColor(1.0, 0.8, 0.0, 1.0))
            cx, cz = px, pz + 0.6
            r = 0.15
            wsegs.moveTo(cx, 0, cz + r)
            wsegs.drawTo(cx + r, 0, cz)
            wsegs.drawTo(cx, 0, cz - r)
            wsegs.drawTo(cx - r, 0, cz)
            wsegs.drawTo(cx, 0, cz + r)
            wnp = self._geo_np.attachNewNode(wsegs.create(dynamic=True))
            wnp.setBin("opaque", 1)

    def _build_eyepath(self) -> None:
        verts = self._data.vertices
        if not verts:
            return

        color = COLOR_EYEPATH_SEL if self._selected else COLOR_EYEPATH

        segs = LineSegs("eyepath_main")
        segs.setThickness(POLYLINE_THICKNESS)
        segs.setColor(LColor(*color))

        drew_edges = False
        for (vi, vj) in self._data.edges:
            if vi < len(verts) and vj < len(verts):
                x0, z0 = verts[vi]
                x1, z1 = verts[vj]
                segs.moveTo(x0, 0, z0)
                segs.drawTo(x1, 0, z1)
                self._add_arrowhead(segs, x0, z0, x1, z1)
                drew_edges = True

        # Before any edges are defined, connect consecutive vertices as a
        # plain path so the artist can see the vertex layout.
        if not drew_edges and len(verts) >= 2:
            x0, z0 = verts[0]
            segs.moveTo(x0, 0, z0)
            for x, z in verts[1:]:
                segs.drawTo(x, 0, z)

        np = self._geo_np.attachNewNode(segs.create(dynamic=True))
        np.setBin("opaque", 1)

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _add_arrowhead(
        self,
        segs: LineSegs,
        x0: float, z0: float,
        x1: float, z1: float,
    ) -> None:
        """Draw two wing lines at (x1, z1) pointing back toward (x0, z0)."""
        dx, dz = x1 - x0, z1 - z0
        length = math.hypot(dx, dz)
        if length < 1e-9:
            return
        # Backward unit direction
        bdx, bdz = -dx / length, -dz / length
        angle    = math.radians(25)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        L = ARROW_HEAD_SIZE
        # Left wing (+25° rotation of backward direction)
        lwx = (bdx * cos_a - bdz * sin_a) * L
        lwz = (bdx * sin_a + bdz * cos_a) * L
        # Right wing (-25° rotation of backward direction)
        rwx = (bdx * cos_a + bdz * sin_a) * L
        rwz = (-bdx * sin_a + bdz * cos_a) * L
        segs.moveTo(x1, 0, z1)
        segs.drawTo(x1 + lwx, 0, z1 + lwz)
        segs.moveTo(x1, 0, z1)
        segs.drawTo(x1 + rwx, 0, z1 + rwz)

    def _build_handles(self) -> None:
        """Vertex handle quads — direct children of render_root for hit-testing."""
        t = self._data.type
        if t == PolylineType.ARCH:
            unsel_color = COLOR_ARCH
        elif t == PolylineType.EYEPATH:
            unsel_color = COLOR_EYEPATH
        else:
            unsel_color = COLOR_WALL

        handle_color = VERTEX_HANDLE_SEL_COLOR if self._selected else unsel_color

        r = VERTEX_HANDLE_RADIUS
        for i, (x, z) in enumerate(self._data.vertices):
            cm = CardMaker(f"vtx_{self._data.id}_{i}")
            cm.setFrame(-r, r, -r, r)
            np = self._root.attachNewNode(cm.generate())
            np.setPos(x, 0, z)
            np.setColor(LColor(*handle_color))
            np.setTransparency(TransparencyAttrib.MAlpha)
            np.setBin("transparent", 10)
            # Tags used by hit-testing in main.py
            np.setPythonTag("polyline_id", self._data.id)
            np.setPythonTag("vertex_idx",  i)
            self._handle_nps.append(np)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _destroy_scene(self) -> None:
        # Removing the parent removes all child line geometry.
        if self._geo_np is not None:
            self._geo_np.removeNode()
            self._geo_np = None
        for np in self._handle_nps:
            np.removeNode()
        self._handle_nps.clear()


# ── PolylineManager ───────────────────────────────────────────────────────────

class PolylineManager:
    """
    Owns all PolylineNode instances and keeps them in sync with the Level data.

    Call sync_with_level(level) after any structural change to the level's
    polylines dict (add / remove). Call rebuild_one(id) after vertex edits.
    """

    def __init__(self, render_root: NodePath) -> None:
        self._root:  NodePath = render_root
        self._nodes: dict[str, PolylineNode] = {}
        self._selected_id: Optional[str] = None

    # ── Sync ──────────────────────────────────────────────────────────────────

    def sync_with_level(self, level_polylines: dict[str, Polyline]) -> None:
        """
        Add PolylineNodes for new polylines, remove nodes for deleted ones.
        Does NOT rebuild existing nodes (call rebuild_one for that).
        """
        existing_ids = set(self._nodes.keys())
        new_ids      = set(level_polylines.keys())

        for pid in existing_ids - new_ids:
            self._nodes.pop(pid).destroy()

        for pid in new_ids - existing_ids:
            pdata = level_polylines[pid]
            self._nodes[pid] = PolylineNode(
                self._root, pdata, selected=(pid == self._selected_id)
            )

    def rebuild_one(self, polyline_id: str) -> None:
        """Rebuild scene geometry for a single polyline after any mutation."""
        node = self._nodes.get(polyline_id)
        if node:
            node.rebuild()

    def rebuild_all(self) -> None:
        for node in self._nodes.values():
            node.rebuild()

    # ── Selection ─────────────────────────────────────────────────────────────

    def select(self, polyline_id: Optional[str]) -> None:
        if self._selected_id == polyline_id:
            return
        # Deselect previous.
        if self._selected_id and self._selected_id in self._nodes:
            self._nodes[self._selected_id].set_selected(False)
        self._selected_id = polyline_id
        # Select new.
        if polyline_id and polyline_id in self._nodes:
            self._nodes[polyline_id].set_selected(True)

    @property
    def selected_id(self) -> Optional[str]:
        return self._selected_id

    def set_highlights(self, highlighted_ids: set[str]) -> None:
        for pid, node in self._nodes.items():
            node.set_highlighted_error(pid in highlighted_ids)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def destroy_all(self) -> None:
        for node in self._nodes.values():
            node.destroy()
        self._nodes.clear()
        self._selected_id = None
