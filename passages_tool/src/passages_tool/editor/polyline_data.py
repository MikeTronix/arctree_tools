"""Typed polyline records: Wall | Arch | EyePath | Anchor.

`Polyline` is a factory namespace so existing `Polyline.make_wall()` call sites
keep working. Runtime values are the four dataclasses; converting a type
returns a new object instead of mutating leftover fields in place.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Union


class PolylineType(Enum):
    WALL = "wall"
    ARCH = "arch"
    EYEPATH = "eyepath"
    ANCHOR = "anchor"


@dataclass
class TextureInterval:
    """A contiguous range of Wall edges sharing one texture.

    from_vertex and to_vertex are inclusive vertex indices.
    The interval covers edges (from_vertex→from_vertex+1) …
    (to_vertex-1→to_vertex), i.e. to_vertex is the LAST vertex,
    not one past it, so there are (to_vertex - from_vertex) edges.
    """
    from_vertex: int
    to_vertex: int
    texture: Optional[str] = None
    x_offset: float = 0.0


def wall_edge_index_pairs(pl: "Wall") -> list[tuple[int, int]]:
    """Vertex-index pairs for each wall segment, including the closing edge."""
    n = len(pl.vertices)
    if n < 2:
        return []
    pairs = [(i, i + 1) for i in range(n - 1)]
    if pl.closed and n >= 3:
        pairs.append((n - 1, 0))
    return pairs


def _texture_intervals_overlap(a: TextureInterval, b: TextureInterval) -> bool:
    """True if two wall intervals cover a shared edge ([from, to) in vertex space)."""
    return a.from_vertex < b.to_vertex and b.from_vertex < a.to_vertex


def carve_untextured_intervals(
    intervals: list[TextureInterval], span: TextureInterval,
) -> Optional[list[TextureInterval]]:
    """Drop untextured coverage on ``span`` so a PNG override can be inserted.

    Returns None if a textured interval already occupies any of that range.
    """
    for other in intervals:
        if other.texture and _texture_intervals_overlap(span, other):
            return None
    out: list[TextureInterval] = []
    for other in intervals:
        if other.texture or not _texture_intervals_overlap(span, other):
            out.append(other)
            continue
        if other.from_vertex < span.from_vertex:
            out.append(TextureInterval(
                other.from_vertex, span.from_vertex, None, other.x_offset,
            ))
        if span.to_vertex < other.to_vertex:
            out.append(TextureInterval(span.to_vertex, other.to_vertex, None, 0.0))
    return out


def interval_edge_indices(pl: "Wall", iv: TextureInterval) -> list[int]:
    """Edge indices covered by a texture interval.

    Matches converter/wall_builder: edges ``from … to-1``, plus the closing
    edge ``n-1 → 0`` when the wall is closed and the interval reaches the
    last vertex.
    """
    n = len(pl.vertices)
    if n < 2:
        return []
    idxs: list[int] = []
    for i in range(iv.from_vertex, iv.to_vertex):
        if 0 <= i < n - 1:
            idxs.append(i)
    if pl.closed and iv.to_vertex == n - 1:
        closing = n - 1
        if closing not in idxs:
            idxs.append(closing)
    return idxs


@dataclass
class Wall:
    id: str
    vertices: list[tuple[float, float]] = field(default_factory=list)
    closed: bool = False
    texture_intervals: list[TextureInterval] = field(default_factory=list)

    @property
    def type(self) -> PolylineType:
        return PolylineType.WALL

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "vertices": [list(v) for v in self.vertices],
            "closed": self.closed,
            "texture_intervals": [
                {
                    "from_vertex": iv.from_vertex,
                    "to_vertex": iv.to_vertex,
                    "texture": iv.texture,
                    "x_offset": iv.x_offset,
                }
                for iv in self.texture_intervals
            ],
        }


@dataclass
class Arch:
    id: str
    vertices: list[tuple[float, float]] = field(default_factory=list)
    orientation: Union[str, float] = "billboard"
    width: float = 4.0
    height_override: Optional[float] = None
    texture: Optional[str] = None
    transparency: str = "alpha_test"
    z_offset: float = 0.0
    v_at_floor: bool = False  # dressing cards: PNG from z_offset. Doors check Lock V to floor.
    is_light_source: bool = False
    light_color: tuple[float, float, float] = (1.0, 0.75, 0.4)
    light_intensity: float = 1.0
    warning: bool = False
    auto_snap: bool = False
    target_walls: list[str] = field(default_factory=list)
    # S4 3D opening (omit on save when unset). kind=opening or depth_m>0.
    kind: Optional[str] = None
    profile: Optional[str] = None
    depth_m: Optional[float] = None
    side_texture: Optional[str] = None

    @property
    def type(self) -> PolylineType:
        return PolylineType.ARCH

    @property
    def position(self) -> tuple[float, float]:
        return self.vertices[0] if self.vertices else (0.0, 0.0)

    @position.setter
    def position(self, value: tuple[float, float]) -> None:
        if self.vertices:
            self.vertices[0] = tuple(value)
        else:
            self.vertices.append(tuple(value))

    def to_dict(self) -> dict:
        pos = self.vertices[0] if self.vertices else (0.0, 0.0)
        d = {
            "id": self.id,
            "type": self.type.value,
            "position": list(pos),
            "orientation": self.orientation,
            "width": self.width,
            "height_override": self.height_override,
            "texture": self.texture,
            "transparency": self.transparency,
            "z_offset": self.z_offset,
            "v_at_floor": self.v_at_floor,
            "is_light_source": self.is_light_source,
            "light_color": list(self.light_color),
            "light_intensity": self.light_intensity,
            "warning": self.warning,
            "auto_snap": self.auto_snap,
            "target_walls": list(self.target_walls),
        }
        if self.kind:
            d["kind"] = self.kind
        if self.profile:
            d["profile"] = self.profile
        if self.depth_m is not None:
            d["depth_m"] = float(self.depth_m)
        if self.side_texture:
            d["side_texture"] = self.side_texture
        return d


@dataclass
class EyePath:
    id: str
    vertices: list[tuple[float, float]] = field(default_factory=list)
    edges: list[tuple[int, int]] = field(default_factory=list)

    @property
    def type(self) -> PolylineType:
        return PolylineType.EYEPATH

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "vertices": [list(v) for v in self.vertices],
            "edges": [list(e) for e in self.edges],
        }


@dataclass
class Anchor:
    id: str
    vertices: list[tuple[float, float]] = field(default_factory=list)
    z_offset: float = 0.0
    radius: float = 0.5
    height: float = 2.0
    max_distance: float = 10.0
    fov_limit: Optional[float] = None
    sprite_count: int = 1
    tags: list[str] = field(default_factory=list)

    @property
    def type(self) -> PolylineType:
        return PolylineType.ANCHOR

    @property
    def position(self) -> tuple[float, float]:
        return self.vertices[0] if self.vertices else (0.0, 0.0)

    @position.setter
    def position(self, value: tuple[float, float]) -> None:
        if self.vertices:
            self.vertices[0] = tuple(value)
        else:
            self.vertices.append(tuple(value))

    def to_dict(self) -> dict:
        pos = self.vertices[0] if self.vertices else (0.0, 0.0)
        return {
            "id": self.id,
            "type": self.type.value,
            "position": list(pos),
            "z_offset": self.z_offset,
            "radius": self.radius,
            "height": self.height,
            "max_distance": self.max_distance,
            "fov_limit": self.fov_limit,
            "sprite_count": self.sprite_count,
            "tags": list(self.tags),
        }


AnyPolyline = Wall | Arch | EyePath | Anchor


def make_wall() -> Wall:
    return Wall(id=str(uuid.uuid4()))


def make_arch(position: tuple[float, float] = (0.0, 0.0)) -> Arch:
    return Arch(id=str(uuid.uuid4()), vertices=[tuple(position)])


def make_eyepath() -> EyePath:
    return EyePath(id=str(uuid.uuid4()))


def make_anchor(position: tuple[float, float] = (0.0, 0.0)) -> Anchor:
    return Anchor(id=str(uuid.uuid4()), vertices=[tuple(position)])


def polyline_from_dict(pd: dict) -> AnyPolyline:
    pl_type = PolylineType(pd.get("type", "wall"))

    if pl_type == PolylineType.WALL:
        pl = Wall(
            id=pd["id"],
            vertices=[tuple(v) for v in pd.get("vertices", [])],
            closed=pd.get("closed", False),
        )
        kept: list[TextureInterval] = []
        for ivd in pd.get("texture_intervals", []):
            iv = TextureInterval(
                from_vertex=int(ivd["from_vertex"]),
                to_vertex=int(ivd["to_vertex"]),
                texture=ivd.get("texture"),
                x_offset=float(ivd.get("x_offset", 0.0)),
            )
            if iv.from_vertex >= iv.to_vertex:
                continue
            if any(_texture_intervals_overlap(iv, other) for other in kept):
                continue
            kept.append(iv)
        kept.sort(key=lambda x: x.from_vertex)
        pl.texture_intervals = kept
        return pl

    if pl_type == PolylineType.ARCH:
        pos = tuple(pd.get("position", [0.0, 0.0]))
        lc = pd.get("light_color", [1.0, 0.75, 0.4])
        return Arch(
            id=pd["id"],
            vertices=[pos],
            orientation=pd.get("orientation", "billboard"),
            width=float(pd.get("width", 4.0)),
            height_override=pd.get("height_override"),
            texture=pd.get("texture"),
            transparency=pd.get("transparency", "alpha_test"),
            z_offset=float(pd.get("z_offset", 0.0)),
            v_at_floor=bool(pd.get("v_at_floor", True)),
            is_light_source=bool(pd.get("is_light_source", False)),
            light_color=(float(lc[0]), float(lc[1]), float(lc[2])),
            light_intensity=float(pd.get("light_intensity", 1.0)),
            warning=bool(pd.get("warning", False)),
            auto_snap=bool(pd.get("auto_snap", False)),
            target_walls=list(pd.get("target_walls", [])),
            kind=pd.get("kind"),
            profile=pd.get("profile"),
            depth_m=(float(pd["depth_m"]) if pd.get("depth_m") is not None else None),
            side_texture=pd.get("side_texture"),
        )

    if pl_type == PolylineType.EYEPATH:
        return EyePath(
            id=pd["id"],
            vertices=[tuple(v) for v in pd.get("vertices", [])],
            edges=[tuple(e) for e in pd.get("edges", [])],
        )

    if pl_type == PolylineType.ANCHOR:
        pos = tuple(pd.get("position", [0.0, 0.0]))
        pl = Anchor(
            id=pd["id"],
            vertices=[pos],
            z_offset=float(pd.get("z_offset", 0.0)),
            radius=float(pd.get("radius", 0.5)),
            height=float(pd.get("height", 2.0)),
            max_distance=float(pd.get("max_distance", 10.0)),
            fov_limit=pd.get("fov_limit"),
            sprite_count=int(pd.get("sprite_count", 1)),
            tags=list(pd.get("tags", [])),
        )
        if pl.fov_limit is not None:
            pl.fov_limit = float(pl.fov_limit)
        return pl

    raise ValueError(f"Unknown polyline type: {pl_type!r}")


def convert_polyline_type(pl: AnyPolyline, new_type: PolylineType) -> AnyPolyline:
    """Build a new record of `new_type`, keeping compatible fields. Does not mutate `pl`."""
    if pl.type == new_type:
        return pl
    pid = pl.id
    verts = list(pl.vertices)
    if new_type in (PolylineType.ARCH, PolylineType.ANCHOR):
        pos = verts[0] if verts else (0.0, 0.0)
        if new_type == PolylineType.ARCH:
            return Arch(id=pid, vertices=[pos])
        return Anchor(id=pid, vertices=[pos])
    if new_type == PolylineType.WALL:
        return Wall(id=pid, vertices=verts, closed=False, texture_intervals=[])
    if new_type == PolylineType.EYEPATH:
        return EyePath(id=pid, vertices=verts, edges=[])
    raise ValueError(f"Unknown polyline type: {new_type!r}")


class Polyline:
    """Factory namespace. Runtime values are Wall | Arch | EyePath | Anchor."""

    make_new = staticmethod(make_wall)
    make_wall = staticmethod(make_wall)
    make_arch = staticmethod(make_arch)
    make_eyepath = staticmethod(make_eyepath)
    make_anchor = staticmethod(make_anchor)
    from_dict = staticmethod(polyline_from_dict)
