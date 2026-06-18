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
    "floor_texture": str | null, "ceiling_texture": str | null
  },
  "tiles": [...],           # legacy; retained for future use
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

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Union

from passages_tool import config


# ── Enums ─────────────────────────────────────────────────────────────────────

class PolylineType(Enum):
    WALL    = "wall"
    ARCH    = "arch"
    EYEPATH = "eyepath"
    ANCHOR  = "anchor"


# ── Supporting data classes ───────────────────────────────────────────────────

@dataclass
class TextureInterval:
    """
    A contiguous range of Wall edges sharing one texture.

    from_vertex and to_vertex are inclusive vertex indices.
    The interval covers edges (from_vertex→from_vertex+1) …
    (to_vertex-1→to_vertex), i.e. to_vertex is the LAST vertex,
    not one past it, so there are (to_vertex - from_vertex) edges.

    x_offset: horizontal pixel offset into the texture at the start
    of this interval.  Carry-over from the previous interval is
    applied automatically by the converter when texture is the same.
    """
    from_vertex: int
    to_vertex:   int
    texture:     Optional[str] = None
    x_offset:    float = 0.0


@dataclass
class Tile:
    x:       int
    y:       int
    texture: Optional[str] = None


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




@dataclass
class GridConfig:
    cell_size: float = 1.0


# ── Polyline ──────────────────────────────────────────────────────────────────

@dataclass
class Polyline:
    """
    Universal polyline container for all three types.

    Field usage by type
    ───────────────────
    WALL:     vertices, closed, texture_intervals
    ARCH:     vertices[0] = position (x,z); orientation, width, height_override,
              texture, transparency, z_offset, v_at_floor,
              is_light_source, light_color, light_intensity
    EYEPATH:  vertices, edges
    """
    id:   str
    type: PolylineType = PolylineType.WALL

    # ── WALL / EYEPATH ──────────────────────────────────────────────────────
    vertices: list[tuple[float, float]] = field(default_factory=list)
    closed:   bool = False

    # WALL — texture intervals (replaces single texture in v1)
    texture_intervals: list[TextureInterval] = field(default_factory=list)

    # EYEPATH — connectivity graph
    edges: list[tuple[int, int]] = field(default_factory=list)

    # ── ARCH ─────────────────────────────────────────────────────────────────
    # Position is stored as vertices[0]; use the .position property.
    orientation:    Union[str, float] = "billboard"  # "billboard" or degrees
    width:          float = 4.0
    height_override: Optional[float] = None          # None → use level wall_height
    texture:        Optional[str] = None             # Arch texture (also v1 compat)
    transparency:   str = "alpha_test"               # "none"|"alpha_test"|"alpha_blend"
    z_offset:       float = 0.0
    v_at_floor:     bool = True     # V=0 of texture always at world Z=0
    is_light_source: bool = False
    light_color:    tuple[float, float, float] = (1.0, 0.75, 0.4)
    light_intensity: float = 1.0
    warning:        bool = False

    # ── ANCHOR ───────────────────────────────────────────────────────────────
    radius:         float = 0.5
    max_distance:   float = 10.0
    fov_limit:      Optional[float] = None
    sprite_count:   int = 1

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def position(self) -> tuple[float, float]:
        """ARCH only: placement point in XZ. Stored as vertices[0]."""
        return self.vertices[0] if self.vertices else (0.0, 0.0)

    @position.setter
    def position(self, value: tuple[float, float]) -> None:
        if self.vertices:
            self.vertices[0] = tuple(value)
        else:
            self.vertices.append(tuple(value))

    # ── Factory methods ───────────────────────────────────────────────────────

    @staticmethod
    def make_new() -> "Polyline":
        """Create a new empty WALL polyline (backward-compatible default)."""
        return Polyline(id=str(uuid.uuid4()), type=PolylineType.WALL)

    @staticmethod
    def make_wall() -> "Polyline":
        return Polyline(id=str(uuid.uuid4()), type=PolylineType.WALL)

    @staticmethod
    def make_arch(position: tuple[float, float] = (0.0, 0.0)) -> "Polyline":
        pl = Polyline(id=str(uuid.uuid4()), type=PolylineType.ARCH)
        pl.vertices = [tuple(position)]
        return pl

    @staticmethod
    def make_eyepath() -> "Polyline":
        return Polyline(id=str(uuid.uuid4()), type=PolylineType.EYEPATH)

    @staticmethod
    def make_anchor(position: tuple[float, float] = (0.0, 0.0)) -> "Polyline":
        pl = Polyline(id=str(uuid.uuid4()), type=PolylineType.ANCHOR)
        pl.vertices = [tuple(position)]
        return pl

    # ── Serialisation helpers ─────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d: dict = {"id": self.id, "type": self.type.value}
        if self.type == PolylineType.WALL:
            d["vertices"] = [list(v) for v in self.vertices]
            d["closed"]   = self.closed
            d["texture_intervals"] = [
                {
                    "from_vertex": iv.from_vertex,
                    "to_vertex":   iv.to_vertex,
                    "texture":     iv.texture,
                    "x_offset":    iv.x_offset,
                }
                for iv in self.texture_intervals
            ]
        elif self.type == PolylineType.ARCH:
            pos = self.vertices[0] if self.vertices else (0.0, 0.0)
            d["position"]       = list(pos)
            d["orientation"]    = self.orientation
            d["width"]          = self.width
            d["height_override"]= self.height_override
            d["texture"]        = self.texture
            d["transparency"]   = self.transparency
            d["z_offset"]       = self.z_offset
            d["v_at_floor"]     = self.v_at_floor
            d["is_light_source"]= self.is_light_source
            d["light_color"]    = list(self.light_color)
            d["light_intensity"]= self.light_intensity
            d["warning"]        = self.warning
        elif self.type == PolylineType.EYEPATH:
            d["vertices"] = [list(v) for v in self.vertices]
            d["edges"]    = [list(e) for e in self.edges]
        elif self.type == PolylineType.ANCHOR:
            pos = self.vertices[0] if self.vertices else (0.0, 0.0)
            d["position"]       = list(pos)
            d["z_offset"]       = self.z_offset
            d["radius"]         = self.radius
            d["max_distance"]   = self.max_distance
            d["fov_limit"]      = self.fov_limit
            d["sprite_count"]   = self.sprite_count
        return d

    @staticmethod
    def from_dict(pd: dict) -> "Polyline":
        pl_type = PolylineType(pd.get("type", "wall"))

        if pl_type == PolylineType.WALL:
            pl = Polyline(
                id       = pd["id"],
                type     = pl_type,
                vertices = [tuple(v) for v in pd.get("vertices", [])],
                closed   = pd.get("closed", False),
            )
            for ivd in pd.get("texture_intervals", []):
                pl.texture_intervals.append(TextureInterval(
                    from_vertex = int(ivd["from_vertex"]),
                    to_vertex   = int(ivd["to_vertex"]),
                    texture     = ivd.get("texture"),
                    x_offset    = float(ivd.get("x_offset", 0.0)),
                ))

        elif pl_type == PolylineType.ARCH:
            pos = tuple(pd.get("position", [0.0, 0.0]))
            lc  = pd.get("light_color", [1.0, 0.75, 0.4])
            pl  = Polyline(
                id             = pd["id"],
                type           = pl_type,
                vertices       = [pos],
                orientation    = pd.get("orientation", "billboard"),
                width          = float(pd.get("width", 4.0)),
                height_override= pd.get("height_override"),
                texture        = pd.get("texture"),
                transparency   = pd.get("transparency", "alpha_test"),
                z_offset       = float(pd.get("z_offset", 0.0)),
                v_at_floor     = bool(pd.get("v_at_floor", True)),
                is_light_source= bool(pd.get("is_light_source", False)),
                light_color    = (float(lc[0]), float(lc[1]), float(lc[2])),
                light_intensity= float(pd.get("light_intensity", 1.0)),
                warning        = bool(pd.get("warning", False)),
            )

        elif pl_type == PolylineType.EYEPATH:
            pl = Polyline(
                id       = pd["id"],
                type     = pl_type,
                vertices = [tuple(v) for v in pd.get("vertices", [])],
                edges    = [tuple(e) for e in pd.get("edges", [])],
            )

        elif pl_type == PolylineType.ANCHOR:
            pos = tuple(pd.get("position", [0.0, 0.0]))
            pl  = Polyline(
                id             = pd["id"],
                type           = pl_type,
                vertices       = [pos],
                z_offset       = float(pd.get("z_offset", 0.0)),
                radius         = float(pd.get("radius", 0.5)),
                max_distance   = float(pd.get("max_distance", 10.0)),
                fov_limit      = pd.get("fov_limit"),
                sprite_count   = int(pd.get("sprite_count", 1)),
            )
            if pl.fov_limit is not None:
                pl.fov_limit = float(pl.fov_limit)

        else:
            raise ValueError(f"Unknown polyline type: {pl_type!r}")

        return pl


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
        self.tiles:     dict[tuple[int, int], Tile]  = {}
        self.polylines: dict[str, Polyline]          = {}
        self.dirty:     bool = False

    # ── Tiles ─────────────────────────────────────────────────────────────────

    def set_tile(self, x: int, y: int, texture: Optional[str]) -> None:
        key = (x, y)
        if texture is None and key in self.tiles:
            del self.tiles[key]
        else:
            self.tiles[key] = Tile(x=x, y=y, texture=texture)
        self.dirty = True

    def get_tile(self, x: int, y: int) -> Optional[Tile]:
        return self.tiles.get((x, y))

    def clear_tiles(self) -> None:
        self.tiles.clear()
        self.dirty = True

    # ── Polylines (shared) ────────────────────────────────────────────────────

    def add_polyline(self, polyline: Polyline) -> None:
        self.polylines[polyline.id] = polyline
        self.dirty = True

    def remove_polyline(self, polyline_id: str) -> None:
        self.polylines.pop(polyline_id, None)
        self.dirty = True

    def get_polyline(self, polyline_id: str) -> Optional[Polyline]:
        return self.polylines.get(polyline_id)

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
            
            # Adjust texture intervals
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

            # Adjust edges
            new_edges = []
            for vi, vj in pl.edges:
                if vi == idx or vj == idx:
                    continue  # remove the edge
                new_vi = vi - 1 if vi > idx else vi
                new_vj = vj - 1 if vj > idx else vj
                new_edges.append((new_vi, new_vj))
            pl.edges = new_edges

            self.dirty = True

    def set_polyline_closed(self, polyline_id: str, closed: bool) -> None:
        pl = self.polylines.get(polyline_id)
        if pl is not None:
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
        if pl.type == PolylineType.ARCH:
            pl.texture = texture
        else:
            # WALL fallback: replace all intervals with one spanning the whole line
            n = max(0, len(pl.vertices) - 1)
            pl.texture_intervals = (
                [TextureInterval(from_vertex=0, to_vertex=n, texture=texture)]
                if texture is not None else []
            )
        self.dirty = True

    # ── Wall: texture intervals ───────────────────────────────────────────────

    def add_texture_interval(self, polyline_id: str,
                             interval: TextureInterval) -> None:
        pl = self.polylines.get(polyline_id)
        if pl is not None and pl.type == PolylineType.WALL:
            if interval.from_vertex >= interval.to_vertex:
                return          # zero- or negative-length interval is a no-op
            pl.texture_intervals.append(interval)
            pl.texture_intervals.sort(key=lambda iv: iv.from_vertex)
            self.dirty = True

    def remove_texture_interval(self, polyline_id: str, index: int) -> None:
        pl = self.polylines.get(polyline_id)
        if pl is not None and 0 <= index < len(pl.texture_intervals):
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
        if pl is None:
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
        if pl is not None and 0 <= index < len(pl.texture_intervals):
            pl.texture_intervals[index].texture = texture
            self.dirty = True

    def set_interval_x_offset(self, polyline_id: str,
                              index: int, x_offset: float) -> None:
        """Update the x_offset on an existing interval (by index)."""
        pl = self.polylines.get(polyline_id)
        if pl is not None and 0 <= index < len(pl.texture_intervals):
            pl.texture_intervals[index].x_offset = x_offset
            self.dirty = True

    # ── EyePath: edge management ──────────────────────────────────────────────

    def add_eyepath_edge(self, polyline_id: str,
                         v_from: int, v_to: int) -> None:
        pl = self.polylines.get(polyline_id)
        if pl is not None and pl.type == PolylineType.EYEPATH:
            n_verts = len(pl.vertices)
            if 0 <= v_from < n_verts and 0 <= v_to < n_verts:
                edge = (v_from, v_to)
                if edge not in pl.edges:
                    pl.edges.append(edge)
                    self.dirty = True

    def remove_eyepath_edge(self, polyline_id: str,
                            v_from: int, v_to: int) -> None:
        pl = self.polylines.get(polyline_id)
        if pl is not None and pl.type == PolylineType.EYEPATH:
            try:
                pl.edges.remove((v_from, v_to))
                self.dirty = True
            except ValueError:
                pass

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        m = self.meta
        return {
            "version": 2,
            "meta": {
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
            },
            "grid": {"cell_size": self.grid.cell_size},
            "tiles": [
                {"x": t.x, "y": t.y, "texture": t.texture}
                for t in self.tiles.values()
            ],
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

        grid = data.get("grid", {})
        level.grid.cell_size = float(grid.get("cell_size", 1.0))

        for td in data.get("tiles", []):
            level.set_tile(td["x"], td["y"], td.get("texture"))

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
        for tile in self.tiles.values():
            xs += [float(tile.x), float(tile.x + 1)]
            zs += [float(tile.y), float(tile.y + 1)]
        if not xs:
            return (0.0, 10.0, 0.0, 10.0)
        return (min(xs), max(xs), min(zs), max(zs))
