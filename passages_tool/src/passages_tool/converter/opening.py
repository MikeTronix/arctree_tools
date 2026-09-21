"""S4: opening profiles, wall-punch intervals, leftover patches.

3D slabs live in ``arch_builder``. This module is pure math (no Egg).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from passages_tool.editor.level import Level, PolylineType, wall_edge_index_pairs

BUILTIN_PROFILES = ("rect", "round", "gothic")
_PUNCH_DIST_M = 0.25
_MIN_SPAN = 0.02


def is_3d_opening(pl) -> bool:
    """True when this arch should punch the wall and extrude a slab."""
    if getattr(pl, "type", None) != PolylineType.ARCH:
        return False
    if getattr(pl, "orientation", None) == "billboard":
        return False
    if getattr(pl, "transparency", "") == "alpha_blend":
        return False
    kind = getattr(pl, "kind", None) or None
    if kind in ("niche", "volume"):
        return False
    depth = getattr(pl, "depth_m", None)
    if kind == "opening":
        return True
    return depth is not None and float(depth) > 0.0


def opening_profile_name(pl, pack=None) -> str:
    name = (getattr(pl, "profile", None) or "").strip()
    if not name and pack is not None:
        name = pack.default_opening.profile
    if name not in BUILTIN_PROFILES:
        return "rect"
    return name


def opening_depth_m(pl, pack=None) -> float:
    d = getattr(pl, "depth_m", None)
    if d is not None and float(d) > 0.0:
        return float(d)
    if pack is not None and pack.default_opening.depth_m > 0.0:
        return float(pack.default_opening.depth_m)
    return 0.4


@dataclass(frozen=True)
class WallHole:
    """Punch on one wall edge. ``t0,t1`` in [0,1] along the edge; z in meters."""
    t0: float
    t1: float
    z0: float
    z1: float


@dataclass(frozen=True)
class WallPatch:
    """Leftover wall rectangle in edge-local meters (s along edge, z up)."""
    s0: float
    s1: float
    z0: float
    z1: float


def profile_polyline(
    name: str, width: float, z_bottom: float, height: float, n: int = 16
) -> list[tuple[float, float]]:
    """Closed-ish CCW loop in (s, z), s=0 at left. First point is not duplicated."""
    w = max(1e-4, float(width))
    h = max(1e-4, float(height))
    zb = float(z_bottom)
    zt = zb + h
    n = max(8, int(n))
    if name == "round":
        r = min(w * 0.5, h)
        spring = zt - r
        pts: list[tuple[float, float]] = [(0.0, zb), (w, zb), (w, spring)]
        for i in range(1, n):
            ang = math.pi * i / n  # 0=right → π=left over the top
            pts.append((w * 0.5 + r * math.cos(ang), spring + r * math.sin(ang)))
        pts.append((0.0, spring))
        return pts
    if name == "gothic":
        rise = math.sqrt(max(0.0, w * w - (w * 0.5) ** 2))
        spring = zt - rise
        if spring < zb:
            spring = zb
            rise = zt - zb
        pts = [(0.0, zb), (w, zb), (w, spring)]
        n2 = max(4, n // 2)
        # Right arc: center at left base of the arch (0, spring), radius w
        for i in range(1, n2 + 1):
            a0 = 0.0
            a1 = math.atan2(rise, w * 0.5)
            a = a0 + (a1 - a0) * i / n2
            pts.append((w * math.cos(a), spring + w * math.sin(a)))
        # Left arc: center at (w, spring)
        b0 = math.atan2(rise, -w * 0.5)
        b1 = math.pi
        for i in range(1, n2 + 1):
            b = b0 + (b1 - b0) * i / n2
            pts.append((w + w * math.cos(b), spring + w * math.sin(b)))
        pts.append((0.0, spring))
        return pts
    return [(0.0, zb), (w, zb), (w, zt), (0.0, zt)]


def _dist_point_line(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / L2
    qx, qy = ax + t * dx, ay + t * dy
    return math.hypot(px - qx, py - qy)


def _project_t(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return 0.0
    return ((px - ax) * dx + (py - ay) * dy) / L2


def project_opening_onto_edge(
    p_left: tuple[float, float],
    p_right: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
    dist_eps: float = _PUNCH_DIST_M,
) -> Optional[tuple[float, float]]:
    """Overlap of the opening span with edge AB as ``(t0, t1)`` in [0,1], or None."""
    d0 = _dist_point_line(p_left[0], p_left[1], a[0], a[1], b[0], b[1])
    d1 = _dist_point_line(p_right[0], p_right[1], a[0], a[1], b[0], b[1])
    if d0 > dist_eps or d1 > dist_eps:
        return None
    t0 = _project_t(p_left[0], p_left[1], a[0], a[1], b[0], b[1])
    t1 = _project_t(p_right[0], p_right[1], a[0], a[1], b[0], b[1])
    if t0 > t1:
        t0, t1 = t1, t0
    t0 = max(0.0, min(1.0, t0))
    t1 = max(0.0, min(1.0, t1))
    if t1 - t0 < _MIN_SPAN:
        return None
    return (t0, t1)


def resolve_arch_span(
    level: Level, pl
) -> Optional[tuple[tuple[float, float], tuple[float, float], float, tuple[float, float]]]:
    """``(p_left, p_right, width, (nx, ny))`` for a fixed arch. None for billboard."""
    from passages_tool.converter.arch_builder import find_snap_points

    if not pl.vertices:
        return None
    if pl.orientation == "billboard":
        return None
    pos = pl.vertices[0]
    try:
        theta_deg = float(pl.orientation)
    except (TypeError, ValueError):
        theta_deg = 0.0
    auto_snap = bool(getattr(pl, "auto_snap", False))
    if auto_snap:
        p_left, p_right, width, normal, _mid = find_snap_points(level, pos, theta_deg)
        return p_left, p_right, width, normal
    width = float(pl.width)
    theta_rad = math.radians(theta_deg)
    nx, ny = math.cos(theta_rad), math.sin(theta_rad)
    dx_w = (width / 2.0) * (-math.sin(theta_rad))
    dy_w = (width / 2.0) * math.cos(theta_rad)
    p_left = (pos[0] - dx_w, pos[1] - dy_w)
    p_right = (pos[0] + dx_w, pos[1] + dy_w)
    return p_left, p_right, width, (nx, ny)


def collect_opening_punches(level: Level) -> dict[tuple[str, int], list[WallHole]]:
    """Map ``(wall_id, edge_start_vertex)`` → holes."""
    out: dict[tuple[str, int], list[WallHole]] = {}
    wall_h = float(level.meta.wall_height)
    for pl in level.polylines.values():
        if not is_3d_opening(pl):
            continue
        span = resolve_arch_span(level, pl)
        if span is None:
            continue
        p_left, p_right, _w, _n = span
        height = (
            pl.height_override if pl.height_override is not None else wall_h
        )
        z0 = float(pl.z_offset)
        z1 = z0 + float(height)
        z0 = max(0.0, min(wall_h, z0))
        z1 = max(0.0, min(wall_h, z1))
        if z1 - z0 < _MIN_SPAN:
            continue
        for wall in level.walls():
            for v0, v1 in wall_edge_index_pairs(wall):
                a, b = wall.vertices[v0], wall.vertices[v1]
                ts = project_opening_onto_edge(p_left, p_right, a, b)
                if ts is None:
                    continue
                hole = WallHole(t0=ts[0], t1=ts[1], z0=z0, z1=z1)
                out.setdefault((wall.id, v0), []).append(hole)
    return out


def subtract_rect(keep: WallPatch, hole: WallPatch) -> list[WallPatch]:
    """Axis-aligned leftover rectangles after punching ``hole`` out of ``keep``."""
    ix0 = max(keep.s0, hole.s0)
    ix1 = min(keep.s1, hole.s1)
    iy0 = max(keep.z0, hole.z0)
    iy1 = min(keep.z1, hole.z1)
    if ix1 - ix0 < 1e-6 or iy1 - iy0 < 1e-6:
        return [keep]
    bits: list[WallPatch] = []
    if hole.s0 > keep.s0 + 1e-6:
        bits.append(WallPatch(keep.s0, min(hole.s0, keep.s1), keep.z0, keep.z1))
    if hole.s1 < keep.s1 - 1e-6:
        bits.append(WallPatch(max(hole.s1, keep.s0), keep.s1, keep.z0, keep.z1))
    mid_s0, mid_s1 = ix0, ix1
    if hole.z0 > keep.z0 + 1e-6:
        bits.append(WallPatch(mid_s0, mid_s1, keep.z0, min(hole.z0, keep.z1)))
    if hole.z1 < keep.z1 - 1e-6:
        bits.append(WallPatch(mid_s0, mid_s1, max(hole.z1, keep.z0), keep.z1))
    return [b for b in bits if b.s1 - b.s0 > 1e-6 and b.z1 - b.z0 > 1e-6]


def leftover_patches(
    length_m: float, wall_height: float, holes: list[WallHole]
) -> list[WallPatch]:
    keep = [WallPatch(0.0, length_m, 0.0, wall_height)]
    for h in holes:
        hole = WallPatch(h.t0 * length_m, h.t1 * length_m, h.z0, h.z1)
        nxt: list[WallPatch] = []
        for r in keep:
            nxt.extend(subtract_rect(r, hole))
        keep = nxt
    return keep
