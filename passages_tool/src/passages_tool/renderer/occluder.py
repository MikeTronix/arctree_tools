"""
renderer/occluder.py
────────────────────
CPU ray-vs-geometry occlusion for baked anchor visibility, with texture-alpha
sampling for cutout ("alpha_test") arches.

See design_docs/passages_anchor_visibility_bake_06JUL26.md §3 (revised 2026-07-06:
CPU ray + arch-alpha sampling, after the GPU depth path proved unreliable).

Occluders are vertical quads:
  • WALL segments        → solid, z ∈ [0, wall_height]
  • solid arches         → solid, z ∈ [z_offset, z_offset + height]
  • cutout arches        → same quad, but a hit blocks only where the arch
                           texture's alpha ≥ threshold at the intersection UV
Excluded (non-occluding): billboard arches, `alpha_blend` arches, floor/ceiling
(horizontal planes don't block horizontal sightlines to in-room anchors — v1
simplification, §3 revision note).

The public surface is `build_occluders(level, texture_dir)` → `OccluderSet`, whose
`nearest_occluder_dist(eye, target)` is the provider consumed by
occlusion.occlusion_coverage().
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from panda3d.core import PNMImage, Filename

from passages_tool.editor.level import Level, PolylineType, wall_edge_index_pairs

Vec3 = tuple[float, float, float]

_EPS = 1e-4


@dataclass
class AlphaTex:
    """A sampled texture-alpha lookup (0 origin at texture bottom-left, matching
    the egg UV convention; PNMImage rows are top-origin so we flip)."""
    img: PNMImage
    w: int
    h: int

    def alpha_at(self, u: float, v: float) -> float:
        """u,v in egg convention: u across width [0,1], v bottom-origin. Values
        outside [0,1] clamp (arch door textures are not tiled)."""
        if not self.img.has_alpha():
            return 1.0
        px = min(max(int(u * (self.w - 1)), 0), self.w - 1)
        # egg v is bottom-origin; PNMImage y is top-origin.
        py = min(max(int((1.0 - v) * (self.h - 1)), 0), self.h - 1)
        return self.img.get_alpha(px, py)


@dataclass
class Quad:
    """A vertical occluder quad standing between XY endpoints a→b over [z0, z1]."""
    ax: float
    ay: float
    bx: float
    by: float
    z0: float
    z1: float
    # cutout support (None → solid)
    tex: Optional[AlphaTex] = None
    ppm: float = 256.0            # pixels-per-metre, for the v mapping
    v_at_floor: bool = True
    alpha_threshold: float = 0.5


@dataclass
class OccluderSet:
    quads: list[Quad] = field(default_factory=list)

    def nearest_occluder_dist(self, eye: Vec3, target: Vec3) -> float:
        """Distance from `eye` to the nearest occluding surface strictly between
        `eye` and `target` (math.inf if nothing blocks before `target`).

        Only occluders in the segment (ray param t ∈ (0, 1]) count, so geometry
        beyond the target — e.g. the wall an anchor stands in front of — never
        occludes it. A cutout-arch crossing blocks only where its texture alpha
        ≥ threshold at the intersection UV.
        """
        ex, ey, ez = eye
        dx, dy, dz = target[0] - ex, target[1] - ey, target[2] - ez
        seg_len = math.sqrt(dx * dx + dy * dy + dz * dz)
        if seg_len < _EPS:
            return math.inf

        best = math.inf
        for q in self.quads:
            # 2D ray/segment solve:  eye_xy + t*d_xy = a + u*(b-a)
            #   [dx, -abx; dy, -aby] [t; u] = [ax-ex; ay-ey]
            abx, aby = q.bx - q.ax, q.by - q.ay
            det = dx * (-aby) - (-abx) * dy
            if abs(det) < 1e-12:
                continue                       # ray parallel to the wall segment
            rx, ry = q.ax - ex, q.ay - ey
            t = (rx * (-aby) - (-abx) * ry) / det
            u = (dx * ry - dy * rx) / det
            if t <= _EPS or t > 1.0 + _EPS or u < 0.0 or u > 1.0:
                continue                       # behind eye / beyond target / off the ends
            # world hit point + height check
            hz = ez + t * dz
            if hz < q.z0 - _EPS or hz > q.z1 + _EPS:
                continue
            if q.tex is not None:
                v = self._tex_v(q, hz)
                if q.tex.alpha_at(u, v) < q.alpha_threshold:
                    continue                   # passes through the cutout opening
            dist = t * seg_len
            if dist < best:
                best = dist
        return best

    @staticmethod
    def _tex_v(q: Quad, z: float) -> float:
        """Egg v (bottom-origin) for world height z, matching arch_builder."""
        if q.tex is None:
            return 0.0
        if q.v_at_floor:
            return (z * q.ppm) / q.tex.h
        return ((z - q.z0) * q.ppm) / q.tex.h


# ── construction ──────────────────────────────────────────────────────────────

def _load_alpha_tex(texname: str, texture_dir: Path, cache: dict) -> Optional[AlphaTex]:
    if texname in cache:
        return cache[texname]
    path = texture_dir / texname
    img = PNMImage()
    at: Optional[AlphaTex] = None
    if path.is_file() and img.read(Filename.from_os_specific(str(path))):
        at = AlphaTex(img=img, w=img.get_x_size(), h=img.get_y_size())
    cache[texname] = at
    return at


def _arch_endpoints(level: Level, pl) -> tuple[tuple[float, float], tuple[float, float]]:
    """World XY endpoints (p_left, p_right) of a non-billboard arch span,
    mirroring converter/arch_builder.build_arches."""
    pos = pl.vertices[0]
    if getattr(pl, "auto_snap", False):
        from passages_tool.converter.arch_builder import find_snap_points
        try:
            theta = float(pl.orientation)
        except (ValueError, TypeError):
            theta = 0.0
        p_left, p_right, _w, _n, _mid = find_snap_points(level, pos, theta)
        return p_left, p_right
    width = pl.width
    try:
        theta = math.radians(float(pl.orientation))
    except (ValueError, TypeError):
        theta = 0.0
    dxw = (width / 2.0) * (-math.sin(theta))
    dyw = (width / 2.0) * math.cos(theta)
    return (pos[0] - dxw, pos[1] - dyw), (pos[0] + dxw, pos[1] + dyw)


def build_occluders(level: Level, texture_dir: Optional[Path] = None) -> OccluderSet:
    """Assemble the occluder quad set for a level (walls + eligible arches)."""
    tex_dir = Path(texture_dir) if texture_dir else Path(".")
    wall_h = level.meta.wall_height
    ppm = level.meta.pixels_per_meter
    tex_cache: dict = {}
    quads: list[Quad] = []

    for pl in level.walls():
        vs = pl.vertices
        for ai, bi in wall_edge_index_pairs(pl):
            a, b = vs[ai], vs[bi]
            quads.append(Quad(a[0], a[1], b[0], b[1], 0.0, wall_h))

    for pl in level.polylines.values():
        if pl.type == PolylineType.ARCH:
            if not pl.vertices:
                continue
            if pl.orientation == "billboard":
                continue                          # billboards never occlude
            if pl.transparency == "alpha_blend":
                continue                          # translucent → see-through
            p_left, p_right = _arch_endpoints(level, pl)
            height = pl.height_override if pl.height_override is not None else wall_h
            z0 = pl.z_offset
            z1 = pl.z_offset + height
            tex = None
            if pl.transparency == "alpha_test" and pl.texture:
                tex = _load_alpha_tex(pl.texture, tex_dir, tex_cache)
                # If the texture can't be loaded, fall back to solid (safe: an
                # arch we can't read is treated as a full occluder).
            quads.append(Quad(p_left[0], p_left[1], p_right[0], p_right[1],
                              z0, z1, tex=tex, ppm=ppm, v_at_floor=pl.v_at_floor))

    return OccluderSet(quads=quads)
