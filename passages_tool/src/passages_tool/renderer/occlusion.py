"""
renderer/occlusion.py
─────────────────────
Pure geometry for baked anchor-visibility occlusion coverage.

See design_docs/passages_anchor_visibility_bake_06JUL26.md §4.1.

This module is deliberately GPU-free: it produces the world-space sample grid
over an anchor's *nominal extent* and turns per-sample occluder distances into a
coverage fraction. The Panda3D aimed-depth capture (occlusion_render.py) supplies
the `nearest_occluder_dist` callable; keeping the math here means it is fully
unit-testable without a graphics context.

Extent model (matches the axis-billboard the runtime will place): a vertical
rectangle centred on the anchor's floor position, standing from z=`z_offset`
(base) to z=`z_offset + height`, whose width axis is horizontal and
perpendicular to the eye→anchor direction (so it "faces" the eye regardless of
which way the runtime later looks — view-independent by construction).
"""
from __future__ import annotations

import math
from typing import Callable

Vec3 = tuple[float, float, float]


def _dist(a: Vec3, b: Vec3) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def sample_grid_points(
    eye: Vec3,
    anchor_xy: tuple[float, float],
    z_offset: float,
    radius: float,
    height: float,
    n_wide: int = 3,
    n_tall: int = 4,
) -> list[Vec3]:
    """World-space sample points over the anchor's nominal extent rectangle.

    Points are placed at cell centres (inset from the silhouette edges, where
    alpha aliasing is worst). Width spans [-radius, +radius] along the axis
    perpendicular to the horizontal eye→anchor direction; height spans
    [z_offset, z_offset + height] in world Z.
    """
    ax, ay = anchor_xy
    # Horizontal eye→anchor direction; perpendicular is the billboard width axis.
    dx, dy = ax - eye[0], ay - eye[1]
    dlen = math.hypot(dx, dy)
    if dlen < 1e-9:
        # Degenerate (anchor directly above/below eye): pick an arbitrary axis.
        px, py = 1.0, 0.0
    else:
        px, py = -dy / dlen, dx / dlen  # left-perpendicular, unit length

    pts: list[Vec3] = []
    for i in range(n_wide):
        # cell-centre in [-1, 1]
        u = (2.0 * (i + 0.5) / n_wide - 1.0) * radius
        wx, wy = ax + u * px, ay + u * py
        for j in range(n_tall):
            z = z_offset + height * (j + 0.5) / n_tall
            pts.append((wx, wy, z))
    return pts


def occlusion_coverage(
    eye: Vec3,
    points: list[Vec3],
    nearest_occluder_dist: Callable[[Vec3], float],
    bias: float = 0.05,
) -> float:
    """Fraction of `points` unoccluded from `eye`.

    `nearest_occluder_dist(p)` returns the distance from `eye` to the nearest
    occluding surface along the ray toward `p` (math.inf if nothing lies before
    `p`). A sample counts as visible when that surface is no nearer than the
    sample itself, minus `bias` (which absorbs self-occlusion by the surface the
    anchor rests against / on).
    """
    if not points:
        return 0.0
    visible = 0
    for p in points:
        d_sample = _dist(eye, p)
        d_occ = nearest_occluder_dist(p)
        if d_occ >= d_sample - bias:
            visible += 1
    return visible / len(points)
