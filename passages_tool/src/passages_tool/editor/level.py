"""
editor/level.py
───────────────
Level data model (v2) — pure Python, no Panda3D dependencies.

The Level object is the single source of truth for the editable document.
All mutations go through Level methods so that the history module can
snapshot them for undo/redo.

Polyline types
──────────────
  WALL      Vertical planar surface.  Vertices define the floor-level path;
            the 3D converter extrudes upward by wall_height.  Interior side
            is the RIGHT-HAND side when traversing vertices in creation order.
            Textures are assigned via texture_intervals.

  ARCH      A single flat quad placed at one point in the level.  Stored as
            a Polyline with exactly one vertex (the position).  Orientation
            is either a fixed angle (degrees) or "billboard" (always faces
            the camera).  May also act as a point-light source.

  EYEPATH   A set of viewpoint positions connected by an undirected edge
            graph.  Each directed edge (v_i → v_j) defines one rendered
            image: the camera placed at vertex v_i, looking toward v_j.
            Image filename: render_v{i:04d}_to_v{j:04d}.png

File format v2 summary
──────────────────────
{
  "version": 2,
  "meta": {
    "name": str, "author": str,
    "wall_height": float, "eye_height": float,
    "fov_h": float, "fov_v": float,
    "texture_pixel_size": float,
    "fog_start": float, "fog_end": float,
    "snap_grid": float,
    "floor_texture": str | null, "ceiling_texture": str | null,
    "style": str (optional), "overlay_seed": int (optional),
    "pom_enabled": bool (optional, default false)
  },
  "polylines": [
    { "id": str, "type": "wall",
      "vertices": [[x,z],...], "closed": bool,
      "texture_intervals": [
        {"from_vertex":int, "to_vertex":int, "texture":str|null,
         "x_offset":float}
      ]
    },
    { "id": str, "type": "arch",
      "position": [x, z], "orientation": "billboard"|float,
      "width": float, "height_override": float|null,
      "texture": str|null, "transparency": "none"|"alpha_test"|"alpha_blend",
      "z_offset": float, "v_at_floor": bool,
      "is_light_source": bool, "light_color": [r,g,b],
      "light_intensity": float
    },
    { "id": str, "type": "eyepath",
      "vertices": [[x,z],...],
      "edges": [[v_from, v_to],...]
    }
  ]
}

Migration
─────────
  v1 files (no "type" field; single "texture" per polyline) are migrated
  automatically by migrate_v1_to_v2() when loaded.  All v1 polylines
  become WALL type.  A single non-null "texture" is converted to a
  single TextureInterval spanning all vertices.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional

from passages_tool import config
from passages_tool.editor.polyline_data import (
    Anchor,
    AnyPolyline,
    Arch,
    EyePath,
    Polyline,
    PolylineType,
    TextureInterval,
    Wall,
    _texture_intervals_overlap,
    carve_untextured_intervals,
    convert_polyline_type,
    interval_edge_indices,
    wall_edge_index_pairs,
)

__all__ = [
    "Anchor",
    "AnyPolyline",
    "Arch",
    "EyePath",
    "GridConfig",
    "Level",
    "LevelMeta",
    "Polyline",
    "PolylineType",
    "TextureInterval",
    "Wall",
    "convert_polyline_type",
    "interval_edge_indices",
    "wall_edge_index_pairs",
]


@dataclass
class LevelMeta:
    # Identity
    name:   str = "Untitled"
    author: str = ""

    # 3-D geometry
    wall_height:        float = config.DEFAULT_WALL_HEIGHT    # world units; also = ceiling height
    eye_height:         float = config.DEFAULT_EYE_HEIGHT     # camera Y above floor for all EyePath points
    fov_h:              float = config.DEFAULT_FOV_H          # horizontal FOV in degrees
    fov_v:              float = config.DEFAULT_FOV_V          # vertical FOV in degrees
    pixels_per_meter:   float = config.DEFAULT_PIXELS_PER_METER  # pixels per meter (texture resolution scaling constant)

    # Depth/fog
    fog_start: float = config.DEFAULT_FOG_START   # world units at which fog begins
    fog_end:   float = config.DEFAULT_FOG_END     # world units at which fog is fully opaque

    # Editor
    snap_grid: float = config.DEFAULT_SNAP_GRID   # editor snap grid size in world units

    # Render settings
    render_width:       int = config.DEFAULT_RENDER_WIDTH     # width of baked images (pixels)
    render_height:      int = config.DEFAULT_RENDER_HEIGHT    # height of baked images (pixels)

    # Floor / ceiling textures
    floor_texture:   Optional[str] = None
    ceiling_texture: Optional[str] = None

    # Style dressing (S1). Absent / None ⇒ today’s interval PNGs. No visual
    # change until S2 compose. ``style`` is an id (``styles/<id>.json``) or a
    # path relative to the texture directory.
    style: Optional[str] = None
    overlay_seed: Optional[int] = None
    pom_enabled: bool = False
    # S7: "closed" (default) or "none" (no ceiling fill). None = follow style.
    ceiling_mode: Optional[str] = None




@dataclass
class GridConfig:
    cell_size: float = 1.0


# ── Level ─────────────────────────────────────────────────────────────────────

class Level:
    """
    Mutable document model (v2).

    All structural mutations set the `dirty` flag so the UI can show the
    unsaved-changes indicator and the history module can snapshot correctly.
    """

    def __init__(self) -> None:
        self.meta:      LevelMeta  = LevelMeta()
        self.grid:      GridConfig = GridConfig()
        self.polylines: dict[str, AnyPolyline] = {}
        self.dirty:     bool = False

    # ── Polylines (shared) ────────────────────────────────────────────────────

    def add_polyline(self, polyline: AnyPolyline) -> None:
        self.polylines[polyline.id] = polyline
        self.dirty = True

    def remove_polyline(self, polyline_id: str) -> None:
        self.polylines.pop(polyline_id, None)
        self.dirty = True

    def replace_polyline(self, polyline: AnyPolyline) -> None:
        """Swap the record at `polyline.id` (used when converting type)."""
        self.polylines[polyline.id] = polyline
        self.dirty = True

    def get_polyline(self, polyline_id: str) -> Optional[AnyPolyline]:
        return self.polylines.get(polyline_id)

    def eyepaths(self) -> list[EyePath]:
        return [pl for pl in self.polylines.values() if isinstance(pl, EyePath)]

    def walls(self) -> list[Wall]:
        return [pl for pl in self.polylines.values() if isinstance(pl, Wall)]

    def anchors(self) -> list[Anchor]:
        return [pl for pl in self.polylines.values() if isinstance(pl, Anchor)]

    def arches(self) -> list[Arch]:
        return [pl for pl in self.polylines.values() if isinstance(pl, Arch)]

    def eyepath_offset(self, path_id: str) -> int:
        """Global vertex index of local 0 on this EyePath (sum of earlier paths)."""
        offset = 0
        for pl in self.eyepaths():
            if pl.id == path_id:
                return offset
            offset += len(pl.vertices)
        return 0

    def eyepath_vertex(self, global_index: int) -> Optional[tuple[float, float]]:
        """Look up a vertex across every EyePath using the bake/client global index."""
        n = 0
        for pl in self.eyepaths():
            if global_index < n + len(pl.vertices):
                return pl.vertices[global_index - n]
            n += len(pl.vertices)
        return None

    def iter_eyepath_directed_edges(
        self,
    ) -> Iterator[tuple[int, int, tuple[float, float], tuple[float, float]]]:
        """Yield (g_from, g_to, p_from, p_to) for both directions of every EyePath edge."""
        offset = 0
        seen: set[tuple[int, int]] = set()
        for pl in self.eyepaths():
            for a, b in pl.edges:
                for e in ((a, b), (b, a)):
                    if e[0] >= len(pl.vertices) or e[1] >= len(pl.vertices):
                        continue
                    g = (e[0] + offset, e[1] + offset)
                    if g in seen:
                        continue
                    seen.add(g)
                    yield g[0], g[1], pl.vertices[e[0]], pl.vertices[e[1]]
            offset += len(pl.vertices)

    def add_vertex(self, polyline_id: str, x: float, z: float) -> None:
        pl = self.polylines.get(polyline_id)
        if pl is not None:
            pl.vertices.append((x, z))
            self.dirty = True

    def move_vertex(self, polyline_id: str, idx: int,
                    x: float, z: float) -> None:
        pl = self.polylines.get(polyline_id)
        if pl is not None and 0 <= idx < len(pl.vertices):
            pl.vertices[idx] = (x, z)
            self.dirty = True

    def delete_vertex(self, polyline_id: str, idx: int) -> None:
        pl = self.polylines.get(polyline_id)
        if pl is not None and 0 <= idx < len(pl.vertices):
            pl.vertices.pop(idx)

            if isinstance(pl, Wall):
                new_intervals = []
                for iv in pl.texture_intervals:
                    fv = iv.from_vertex
                    tv = iv.to_vertex
                    if fv > idx:
                        fv -= 1
                    if tv > idx:
                        tv -= 1
                    if fv < tv:
                        iv.from_vertex = fv
                        iv.to_vertex = tv
                        new_intervals.append(iv)
                pl.texture_intervals = new_intervals

            if isinstance(pl, EyePath):
                new_edges = []
                for vi, vj in pl.edges:
                    if vi == idx or vj == idx:
                        continue
                    new_vi = vi - 1 if vi > idx else vi
                    new_vj = vj - 1 if vj > idx else vj
                    new_edges.append((new_vi, new_vj))
                pl.edges = new_edges

            self.dirty = True

    def insert_vertex(self, polyline_id: str, after_idx: int,
                      x: float, z: float) -> None:
        """Insert a vertex immediately after `after_idx`, reindexing texture
        intervals and eyepath edges. This is the inverse of delete_vertex():
        any vertex index strictly greater than `after_idx` shifts up by one.

        For a texture interval that covered the split edge (its to_vertex was
        after_idx+1), the +1 shift extends it to after_idx+2 so it keeps
        covering both new sub-edges — no texture gap is introduced.
        """
        pl = self.polylines.get(polyline_id)
        if pl is None or not (0 <= after_idx < len(pl.vertices)):
            return

        pl.vertices.insert(after_idx + 1, (x, z))

        if isinstance(pl, Wall):
            for iv in pl.texture_intervals:
                if iv.from_vertex > after_idx:
                    iv.from_vertex += 1
                if iv.to_vertex > after_idx:
                    iv.to_vertex += 1

        if isinstance(pl, EyePath):
            new_idx = after_idx + 1
            shifted: list[tuple[int, int]] = [
                (vi + 1 if vi > after_idx else vi,
                 vj + 1 if vj > after_idx else vj)
                for (vi, vj) in pl.edges
            ]
            split: list[tuple[int, int]] = []
            for vi, vj in shifted:
                if vi == after_idx and vj == new_idx + 1:
                    split.append((after_idx, new_idx))
                    split.append((new_idx, new_idx + 1))
                elif vj == after_idx and vi == new_idx + 1:
                    split.append((new_idx + 1, new_idx))
                    split.append((new_idx, after_idx))
                else:
                    split.append((vi, vj))
            pl.edges = split

        self.dirty = True

    def set_polyline_closed(self, polyline_id: str, closed: bool) -> None:
        pl = self.polylines.get(polyline_id)
        if isinstance(pl, Wall):
            pl.closed = closed
            self.dirty = True

    # Legacy single-texture setter kept for backward compatibility.
    # For WALL, prefer add_texture_interval().
    # For ARCH, this sets the arch texture directly.
    def set_polyline_texture(self, polyline_id: str,
                             texture: Optional[str]) -> None:
        pl = self.polylines.get(polyline_id)
        if pl is None:
            return
        if isinstance(pl, Arch):
            pl.texture = texture
        elif isinstance(pl, Wall):
            n = max(0, len(pl.vertices) - 1)
            pl.texture_intervals = (
                [TextureInterval(from_vertex=0, to_vertex=n, texture=texture)]
                if texture is not None else []
            )
        else:
            return
        self.dirty = True

    # ── Wall: texture intervals ───────────────────────────────────────────────

    def add_texture_interval(self, polyline_id: str,
                             interval: TextureInterval) -> bool:
        pl = self.polylines.get(polyline_id)
        if not isinstance(pl, Wall):
            return False
        if interval.from_vertex >= interval.to_vertex:
            return False
        carved = carve_untextured_intervals(pl.texture_intervals, interval)
        if carved is None:
            return False
        pl.texture_intervals = carved
        pl.texture_intervals.append(interval)
        pl.texture_intervals.sort(key=lambda iv: iv.from_vertex)
        self.dirty = True
        return True

    def remove_texture_interval(self, polyline_id: str, index: int) -> None:
        pl = self.polylines.get(polyline_id)
        if isinstance(pl, Wall) and 0 <= index < len(pl.texture_intervals):
            pl.texture_intervals.pop(index)
            self.dirty = True

    def split_texture_interval(self, polyline_id: str,
                               at_vertex: int) -> None:
        """
        Split the texture interval that contains at_vertex into two intervals.
        The second interval starts at at_vertex with x_offset reset to 0.
        No-op if at_vertex is not inside any interval or is at a boundary.
        """
        pl = self.polylines.get(polyline_id)
        if not isinstance(pl, Wall):
            return
        for i, iv in enumerate(pl.texture_intervals):
            if iv.from_vertex < at_vertex < iv.to_vertex:
                second = TextureInterval(
                    from_vertex = at_vertex,
                    to_vertex   = iv.to_vertex,
                    texture     = iv.texture,
                    x_offset    = 0.0,
                )
                iv.to_vertex = at_vertex
                pl.texture_intervals.insert(i + 1, second)
                self.dirty = True
                return

    def set_interval_texture(self, polyline_id: str,
                            index: int, texture: Optional[str]) -> None:
        """Replace the texture on an existing interval (by index)."""
        pl = self.polylines.get(polyline_id)
        if isinstance(pl, Wall) and 0 <= index < len(pl.texture_intervals):
            pl.texture_intervals[index].texture = texture
            self.dirty = True

    def clear_wall_png_overrides(self, polyline_id: str) -> None:
        """Remove all intervals so a level style dresses every edge.

        Leaving a full-span untextured interval would block Add (overlap).
        Uncovered edges still compose from the style pack.
        """
        pl = self.polylines.get(polyline_id)
        if not isinstance(pl, Wall):
            return
        if pl.texture_intervals:
            pl.texture_intervals.clear()
            self.dirty = True

    def set_interval_x_offset(self, polyline_id: str,
                              index: int, x_offset: float) -> None:
        """Update the x_offset on an existing interval (by index)."""
        pl = self.polylines.get(polyline_id)
        if isinstance(pl, Wall) and 0 <= index < len(pl.texture_intervals):
            pl.texture_intervals[index].x_offset = x_offset
            self.dirty = True

    # ── EyePath: edge management ──────────────────────────────────────────────

    def add_eyepath_edge(self, polyline_id: str,
                         v_from: int, v_to: int) -> None:
        pl = self.polylines.get(polyline_id)
        if isinstance(pl, EyePath):
            n_verts = len(pl.vertices)
            if 0 <= v_from < n_verts and 0 <= v_to < n_verts:
                edge = (v_from, v_to)
                if edge not in pl.edges:
                    pl.edges.append(edge)
                    self.dirty = True

    def remove_eyepath_edge(self, polyline_id: str,
                            v_from: int, v_to: int) -> None:
        pl = self.polylines.get(polyline_id)
        if isinstance(pl, EyePath):
            try:
                pl.edges.remove((v_from, v_to))
                self.dirty = True
            except ValueError:
                pass

    # ── Serialisation ─────────────────────────────────────────────────────────

    def sync_derived_fov_h(self) -> None:
        """Set meta.fov_h from fov_v and render aspect. Does not touch dirty."""
        self.meta.fov_h = config.derived_fov_h(
            self.meta.fov_v, self.meta.render_width, self.meta.render_height
        )

    def to_dict(self) -> dict:
        self.sync_derived_fov_h()
        m = self.meta
        meta = {
            "name":               m.name,
            "author":             m.author,
            "wall_height":        m.wall_height,
            "eye_height":         m.eye_height,
            "fov_h":              m.fov_h,
            "fov_v":              m.fov_v,
            "pixels_per_meter":   m.pixels_per_meter,
            "fog_start":          m.fog_start,
            "fog_end":            m.fog_end,
            "snap_grid":          m.snap_grid,
            "render_width":       m.render_width,
            "render_height":      m.render_height,
            "floor_texture":      m.floor_texture,
            "ceiling_texture":    m.ceiling_texture,
        }
        if m.style:
            meta["style"] = m.style
        if m.overlay_seed is not None:
            meta["overlay_seed"] = int(m.overlay_seed)
        if m.pom_enabled:
            meta["pom_enabled"] = True
        if m.ceiling_mode:
            meta["ceiling_mode"] = m.ceiling_mode
        return {
            "version": 2,
            "meta": meta,
            "grid": {"cell_size": m.snap_grid},
            "polylines": [pl.to_dict() for pl in self.polylines.values()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Level":
        level = cls()
        meta  = data.get("meta", {})
        m     = level.meta

        m.name               = meta.get("name", "Untitled")
        m.author             = meta.get("author", "")
        m.wall_height        = float(meta.get("wall_height", config.DEFAULT_WALL_HEIGHT))
        m.eye_height         = float(meta.get("eye_height", config.DEFAULT_EYE_HEIGHT))
        m.fov_h              = float(meta.get("fov_h", config.DEFAULT_FOV_H))
        m.fov_v              = float(meta.get("fov_v", config.DEFAULT_FOV_V))
        if "pixels_per_meter" in meta:
            m.pixels_per_meter = float(meta["pixels_per_meter"])
        elif "texture_pixel_size" in meta:
            tps = float(meta["texture_pixel_size"])
            m.pixels_per_meter = 1.0 / tps if tps > 0 else config.DEFAULT_PIXELS_PER_METER
        else:
            m.pixels_per_meter = config.DEFAULT_PIXELS_PER_METER
        m.fog_start          = float(meta.get("fog_start", config.DEFAULT_FOG_START))
        m.fog_end            = float(meta.get("fog_end", config.DEFAULT_FOG_END))
        m.snap_grid          = float(meta.get("snap_grid", config.DEFAULT_SNAP_GRID))
        m.render_width       = int(meta.get("render_width", config.DEFAULT_RENDER_WIDTH))
        m.render_height      = int(meta.get("render_height", config.DEFAULT_RENDER_HEIGHT))
        m.floor_texture      = meta.get("floor_texture")
        m.ceiling_texture    = meta.get("ceiling_texture")
        raw_style = meta.get("style")
        if isinstance(raw_style, str) and raw_style.strip():
            m.style = raw_style.strip()
        else:
            m.style = None
        raw_seed = meta.get("overlay_seed")
        if isinstance(raw_seed, bool) or raw_seed is None:
            m.overlay_seed = None
        else:
            try:
                m.overlay_seed = int(raw_seed)
            except (TypeError, ValueError):
                m.overlay_seed = None
        m.pom_enabled = bool(meta.get("pom_enabled", False))
        raw_cm = meta.get("ceiling_mode")
        if isinstance(raw_cm, str) and raw_cm.strip() in ("closed", "none"):
            m.ceiling_mode = raw_cm.strip()
        else:
            m.ceiling_mode = None
        # fov_h is derived from fov_v + render aspect; ignore any stored value.
        level.sync_derived_fov_h()

        # grid.cell_size is an on-disk alias of snap_grid (viewport uses snap_grid).
        level.grid.cell_size = m.snap_grid

        # Legacy `tiles` (floor-cell map) is ignored; the baker never used it.

        for pd in data.get("polylines", []):
            level.add_polyline(Polyline.from_dict(pd))

        level.dirty = False
        return level

    @staticmethod
    def migrate_v1_to_v2(data: dict) -> dict:
        """
        Convert a version-1 level dict to version-2 format in-place copy.

        Changes made:
        - version: 1 → 2
        - meta: gains all new LevelMeta fields with defaults
        - polylines: each gains "type": "wall"; single "texture" field is
          converted to a one-element "texture_intervals" list; "edges" added
        """
        import copy
        data = copy.deepcopy(data)
        data["version"] = 2

        # Migrate meta
        meta = data.setdefault("meta", {})
        
        # If the file has texture_pixel_size, migrate it to pixels_per_meter
        if "texture_pixel_size" in meta and "pixels_per_meter" not in meta:
            tps = float(meta["texture_pixel_size"])
            meta["pixels_per_meter"] = 1.0 / tps if tps > 0 else config.DEFAULT_PIXELS_PER_METER
            meta.pop("texture_pixel_size", None)

        defaults = {
            "wall_height": config.DEFAULT_WALL_HEIGHT, "eye_height": config.DEFAULT_EYE_HEIGHT,
            "fov_h": config.DEFAULT_FOV_H,      "fov_v": config.DEFAULT_FOV_V,
            "pixels_per_meter": config.DEFAULT_PIXELS_PER_METER,
            "fog_start": config.DEFAULT_FOG_START,  "fog_end": config.DEFAULT_FOG_END,
            "snap_grid": config.DEFAULT_SNAP_GRID,
            "render_width": config.DEFAULT_RENDER_WIDTH,
            "render_height": config.DEFAULT_RENDER_HEIGHT,
            "floor_texture": None, "ceiling_texture": None,
        }
        for k, v in defaults.items():
            meta.setdefault(k, v)

        # Migrate polylines
        for pd in data.get("polylines", []):
            pd.setdefault("type", "wall")
            pd.setdefault("edges", [])
            if "texture_intervals" not in pd:
                tex = pd.pop("texture", None)
                n   = max(0, len(pd.get("vertices", [])) - 1)
                pd["texture_intervals"] = (
                    [{"from_vertex": 0, "to_vertex": n,
                      "texture": tex, "x_offset": 0.0}]
                    if tex is not None else []
                )
            else:
                pd.pop("texture", None)   # remove stale field if present
            # Arch/EyePath polylines should not appear in v1 files, but if
            # they somehow do, leave them as-is.

        return data

    # ── Helpers ───────────────────────────────────────────────────────────────

    def bounding_box(self) -> tuple[float, float, float, float]:
        """Return (left, right, bottom, top) in world units, or (0,10,0,10) if empty."""
        xs: list[float] = []
        zs: list[float] = []
        for pl in self.polylines.values():
            for x, z in pl.vertices:
                xs.append(x)
                zs.append(z)
        if not xs:
            return (0.0, 10.0, 0.0, 10.0)
        return (min(xs), max(xs), min(zs), max(zs))
