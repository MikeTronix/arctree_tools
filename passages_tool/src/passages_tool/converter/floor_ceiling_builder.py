"""
converter/floor_ceiling_builder.py
──────────────────────────────────
Generates triangulated floor and ceiling geometries (.egg) connecting to walls.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from panda3d.core import LPoint2d
from panda3d.egg import EggGroup, EggPolygon, EggVertex
from panda3d.core import Triangulator

from passages_tool.converter.egg_writer import EggContext
from passages_tool.converter.wall_builder import get_texture_size
from passages_tool.editor.level import Level, Polyline, PolylineType


def polygon_area(vertices: list[tuple[float, float]]) -> float:
    """Calculate the 2D area of a polygon using the Shoelace formula."""
    n = len(vertices)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


def is_ccw(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]
) -> bool:
    """Check if three 2D points are wound counter-clockwise."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 0


def build_bbox_fallback(
    ctx: EggContext,
    level: Level,
    z_val: float,
    normal: tuple[float, float, float],
    tex_w: int,
    tex_h: int,
    egg_tex: Optional[EggPolygon],
) -> list[EggPolygon]:
    """Safety fallback: create a single large quad covering the bounding box."""
    left, right, bottom, top = level.bounding_box()
    # Add a 10-meter margin
    left -= 10.0
    right += 10.0
    bottom -= 10.0
    top += 10.0

    ppm = level.meta.pixels_per_meter
    u1 = (left * ppm) / tex_w
    u2 = (right * ppm) / tex_w
    v1 = (bottom * ppm) / tex_h
    v2 = (top * ppm) / tex_h

    # Add vertices to pool
    v_bl = ctx.add_vertex(left, bottom, z_val, u1, v1, normal)
    v_br = ctx.add_vertex(right, bottom, z_val, u2, v1, normal)
    v_tr = ctx.add_vertex(right, top, z_val, u2, v2, normal)
    v_tl = ctx.add_vertex(left, top, z_val, u1, v2, normal)

    if normal[2] < 0:
        # Ceiling: facing down -> clockwise in 2D
        return [ctx.add_polygon([v_bl, v_tl, v_tr, v_br], egg_tex)]
    else:
        # Floor: facing up -> counter-clockwise in 2D
        return [ctx.add_polygon([v_bl, v_br, v_tr, v_tl], egg_tex)]


import math

def build_triangulated_polygons(
    ctx: EggContext,
    level: Level,
    z_val: float,
    normal: tuple[float, float, float],
    tex_w: int,
    tex_h: int,
    egg_tex: Optional[EggPolygon],
) -> list[EggPolygon]:
    """Triangulate the level floor/ceiling boundary using closed wall loops."""
    # Find all closed wall polylines (either marked closed or geometrically closed)
    def is_wall_closed(pl: Polyline) -> bool:
        if pl.type != PolylineType.WALL or len(pl.vertices) < 3:
            return False
        if pl.closed:
            return True
        return math.dist(pl.vertices[0], pl.vertices[-1]) < 1e-4

    closed_walls = [
        pl
        for pl in level.polylines.values()
        if is_wall_closed(pl)
    ]

    if not closed_walls:
        # Fallback to bbox quad if no closed wall loop exists
        return build_bbox_fallback(ctx, level, z_val, normal, tex_w, tex_h, egg_tex)

    # Outermost wall is the one with the largest 2D area
    outer_wall = max(closed_walls, key=lambda pl: polygon_area(pl.vertices))
    hole_walls = [pl for pl in closed_walls if pl != outer_wall]

    # Initialize Triangulator
    t = Triangulator()
    ppm = level.meta.pixels_per_meter

    # Keep a dictionary of vertex index to its 3D coordinate/UV vertex object
    egg_verts: dict[int, EggVertex] = {}

    def get_or_add_egg_vertex(vx: float, vy: float) -> int:
        # Add vertex to the Triangulator pool
        idx = t.add_vertex(vx, vy)
        if idx not in egg_verts:
            # Map layout coordinate to U, V
            u = (vx * ppm) / tex_w
            v = (vy * ppm) / tex_h
            egg_verts[idx] = ctx.add_vertex(vx, vy, z_val, u, v, normal)
        return idx

    # Add outer boundary
    outer_verts = list(outer_wall.vertices)
    if len(outer_verts) >= 2 and math.dist(outer_verts[0], outer_verts[-1]) < 1e-4:
        outer_verts.pop()

    for vx, vy in outer_verts:
        idx = get_or_add_egg_vertex(vx, vy)
        t.add_polygon_vertex(idx)

    # Add holes
    for hw in hole_walls:
        t.begin_hole()
        hw_verts = list(hw.vertices)
        if len(hw_verts) >= 2 and math.dist(hw_verts[0], hw_verts[-1]) < 1e-4:
            hw_verts.pop()
        for vx, vy in hw_verts:
            idx = get_or_add_egg_vertex(vx, vy)
            t.add_hole_vertex(idx)

    # Perform triangulation
    try:
        t.triangulate()
    except Exception:
        # Triangulation failed (e.g. self-intersecting path), fallback to bbox
        return build_bbox_fallback(ctx, level, z_val, normal, tex_w, tex_h, egg_tex)

    num_tris = t.get_num_triangles()
    if num_tris == 0:
        return build_bbox_fallback(ctx, level, z_val, normal, tex_w, tex_h, egg_tex)

    polys: list[EggPolygon] = []
    for i in range(num_tris):
        idx0 = t.get_triangle_v0(i)
        idx1 = t.get_triangle_v1(i)
        idx2 = t.get_triangle_v2(i)

        ev0 = egg_verts[idx0]
        ev1 = egg_verts[idx1]
        ev2 = egg_verts[idx2]

        # Check winding direction of triangle in 2D space
        # get_vertex returns LPoint2d
        p0: LPoint2d = t.get_vertex(idx0)
        p1: LPoint2d = t.get_vertex(idx1)
        p2: LPoint2d = t.get_vertex(idx2)

        pt0 = (p0.get_x(), p0.get_y())
        pt1 = (p1.get_x(), p1.get_y())
        pt2 = (p2.get_x(), p2.get_y())

        ccw = is_ccw(pt0, pt1, pt2)

        # Re-wind to match requirements
        if normal[2] > 0:
            # Floor: wants CCW
            tri_verts = [ev0, ev1, ev2] if ccw else [ev0, ev2, ev1]
        else:
            # Ceiling: wants CW
            tri_verts = [ev0, ev2, ev1] if ccw else [ev0, ev1, ev2]

        poly = ctx.add_polygon(tri_verts, egg_tex)
        polys.append(poly)

    return polys


def build_floor(level: Level, texture_dir: Optional[Path] = None) -> EggGroup:
    """Build the triangulated floor geometry group."""
    group = EggGroup("floor")
    ctx = EggContext("floor")
    group.add_child(ctx.vpool)

    tex_name = level.meta.floor_texture
    tex_w, tex_h = get_texture_size(tex_name, texture_dir)
    egg_tex = ctx.get_or_create_texture(tex_name) if tex_name else None

    # Floor at Z=0, normal points up (0, 0, 1)
    polys = build_triangulated_polygons(
        ctx, level, 0.0, (0.0, 0.0, 1.0), tex_w, tex_h, egg_tex
    )
    for poly in polys:
        group.add_child(poly)

    return group


def build_ceiling(level: Level, texture_dir: Optional[Path] = None) -> EggGroup:
    """Build the triangulated ceiling geometry group."""
    group = EggGroup("ceiling")
    ctx = EggContext("ceiling")
    group.add_child(ctx.vpool)

    tex_name = level.meta.ceiling_texture
    tex_w, tex_h = get_texture_size(tex_name, texture_dir)
    egg_tex = ctx.get_or_create_texture(tex_name) if tex_name else None

    # Ceiling at Z=wall_height, normal points down (0, 0, -1)
    polys = build_triangulated_polygons(
        ctx, level, level.meta.wall_height, (0.0, 0.0, -1.0), tex_w, tex_h, egg_tex
    )
    for poly in polys:
        group.add_child(poly)

    return group
