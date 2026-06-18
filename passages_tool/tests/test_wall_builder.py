"""
tests/test_wall_builder.py
──────────────────────────
Tests for wall and floor/ceiling geometry builders.
"""
from __future__ import annotations

import math
from pathlib import Path
import pytest

from passages_tool.converter.floor_ceiling_builder import (
    build_ceiling,
    build_floor,
    is_ccw,
    polygon_area,
)
from passages_tool.converter.wall_builder import build_wall_strips
from passages_tool.editor.level import Level, Polyline, PolylineType, TextureInterval


def get_egg_polygons(group) -> list:
    """Recursively collect all EggPolygon nodes in an EggGroup."""
    from panda3d.egg import EggPolygon

    polys = []
    # group.get_children() or similar
    child = group.get_first_child()
    while child is not None:
        if isinstance(child, EggPolygon):
            polys.append(child)
        elif hasattr(child, "get_first_child"):
            polys.extend(get_egg_polygons(child))
        child = group.get_next_child()
    return polys


def get_polygon_vertices(poly) -> list:
    """Retrieve vertex coordinates from an EggPolygon."""
    verts = []
    for i in range(poly.get_num_vertices()):
        v = poly.get_vertex(i)
        pos = tuple(v.get_pos3())
        # UV coordinate
        uv = tuple(v.get_uv()) if v.has_uv() else (0.0, 0.0)
        # Normal coordinate
        norm = tuple(v.get_normal()) if v.has_normal() else (0.0, 0.0, 0.0)
        verts.append({"pos": pos, "uv": uv, "normal": norm})
    return verts


def test_polygon_area_shoelace():
    square = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    assert polygon_area(square) == 16.0

    triangle = [(0.0, 0.0), (3.0, 0.0), (0.0, 4.0)]
    assert polygon_area(triangle) == 6.0


def test_uv_continuity(tmp_path):
    level = Level()
    level.meta.pixels_per_meter = 256.0
    level.meta.wall_height = 3.0

    pl = Polyline.make_wall()
    pl.vertices = [(0.0, 0.0), (2.0, 0.0), (5.0, 0.0)]
    # One texture interval spanning the whole wall (from 0 to 2)
    pl.texture_intervals = [
        TextureInterval(
            from_vertex=0, to_vertex=2, texture="wall.png", x_offset=0.0
        )
    ]
    level.add_polyline(pl)

    # Build wall strips (mock textures dir since files don't exist -> default 512x512)
    # Texture width = 512, pixels_per_meter = 256 -> tiles every 2.0 meters.
    groups = build_wall_strips(level, texture_dir=tmp_path)
    assert len(groups) == 1

    polys = get_egg_polygons(groups[0])
    assert len(polys) == 2  # 2 segments -> 2 quads

    # First segment: length = 2.0. U ranges from 0.0 to 2.0 * 256 / 512 = 1.0
    # Second segment: length = 3.0. U ranges from 1.0 to (2.0 + 3.0) * 256 / 512 = 2.5
    verts_s1 = get_polygon_vertices(polys[0])
    verts_s2 = get_polygon_vertices(polys[1])

    # Check UVs of first segment
    u_vals_s1 = [v["uv"][0] for v in verts_s1]
    assert min(u_vals_s1) == pytest.approx(0.0)
    assert max(u_vals_s1) == pytest.approx(1.0)

    # Check UVs of second segment
    u_vals_s2 = [v["uv"][0] for v in verts_s2]
    assert min(u_vals_s2) == pytest.approx(1.0)
    assert max(u_vals_s2) == pytest.approx(2.5)


def test_uv_reset_with_offset(tmp_path):
    level = Level()
    level.meta.pixels_per_meter = 256.0
    level.meta.wall_height = 3.0

    pl = Polyline.make_wall()
    pl.vertices = [(0.0, 0.0), (2.0, 0.0), (5.0, 0.0)]
    # Two intervals:
    # 1. 0 -> 1, x_offset = 0.0
    # 2. 1 -> 2, x_offset = 128.0 (pixels)
    pl.texture_intervals = [
        TextureInterval(
            from_vertex=0, to_vertex=1, texture="wall.png", x_offset=0.0
        ),
        TextureInterval(
            from_vertex=1, to_vertex=2, texture="wall.png", x_offset=128.0
        ),
    ]
    level.add_polyline(pl)

    groups = build_wall_strips(level, texture_dir=tmp_path)
    polys = get_egg_polygons(groups[0])
    assert len(polys) == 2

    verts_s1 = get_polygon_vertices(polys[0])
    verts_s2 = get_polygon_vertices(polys[1])

    # S1: length = 2.0. U: 0.0 -> 1.0
    u_vals_s1 = [v["uv"][0] for v in verts_s1]
    assert min(u_vals_s1) == pytest.approx(0.0)
    assert max(u_vals_s1) == pytest.approx(1.0)

    # S2: length = 3.0. U: (0 + 128)/512 = 0.25 -> (3.0*256 + 128)/512 = (768+128)/512 = 1.75
    u_vals_s2 = [v["uv"][0] for v in verts_s2]
    assert min(u_vals_s2) == pytest.approx(0.25)
    assert max(u_vals_s2) == pytest.approx(1.75)


def test_wall_normals(tmp_path):
    level = Level()
    pl = Polyline.make_wall()
    # Horizontal line pointing right: (0,0) -> (3,0). Tangent: (1,0). Normal: (0, -1)
    pl.vertices = [(0.0, 0.0), (3.0, 0.0)]
    pl.texture_intervals = [
        TextureInterval(
            from_vertex=0, to_vertex=1, texture="wall.png", x_offset=0.0
        )
    ]
    level.add_polyline(pl)

    groups = build_wall_strips(level, texture_dir=tmp_path)
    polys = get_egg_polygons(groups[0])
    verts = get_polygon_vertices(polys[0])

    for v in verts:
        nx, ny, nz = v["normal"]
        assert nx == pytest.approx(0.0)
        assert ny == pytest.approx(-1.0)
        assert nz == pytest.approx(0.0)


def test_floor_ceiling_triangulation(tmp_path):
    level = Level()
    level.meta.wall_height = 3.0
    level.meta.pixels_per_meter = 256.0
    level.meta.floor_texture = "floor.png"
    level.meta.ceiling_texture = "ceiling.png"

    # Outer wall loop (CCW): 4x4 square
    outer = Polyline.make_wall()
    outer.closed = True
    outer.vertices = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    outer.texture_intervals = [
        TextureInterval(from_vertex=0, to_vertex=3, texture="wall.png")
    ]
    level.add_polyline(outer)

    # Inner column hole (CW): 1x1 square
    hole = Polyline.make_wall()
    hole.closed = True
    hole.vertices = [(1.0, 1.0), (1.0, 2.0), (2.0, 2.0), (2.0, 1.0)]
    hole.texture_intervals = [
        TextureInterval(from_vertex=0, to_vertex=3, texture="wall.png")
    ]
    level.add_polyline(hole)

    # 1. Test Floor
    floor_grp = build_floor(level, texture_dir=tmp_path)
    floor_polys = get_egg_polygons(floor_grp)

    # Area is 16 - 1 = 15. The triangles should sum to 15.0 area
    total_floor_area = 0.0
    for poly in floor_polys:
        verts = get_polygon_vertices(poly)
        assert len(verts) == 3  # Triangles

        # Check winding: Floor must be CCW (normal points up)
        pt0 = (verts[0]["pos"][0], verts[0]["pos"][1])
        pt1 = (verts[1]["pos"][0], verts[1]["pos"][1])
        pt2 = (verts[2]["pos"][0], verts[2]["pos"][1])
        assert is_ccw(pt0, pt1, pt2)

        # Normal must point up (0, 0, 1)
        for v in verts:
            assert v["normal"] == pytest.approx((0.0, 0.0, 1.0))
            assert v["pos"][2] == pytest.approx(0.0)

        total_floor_area += polygon_area([pt0, pt1, pt2])

    assert total_floor_area == pytest.approx(15.0)

    # 2. Test Ceiling
    ceil_grp = build_ceiling(level, texture_dir=tmp_path)
    ceil_polys = get_egg_polygons(ceil_grp)

    total_ceil_area = 0.0
    for poly in ceil_polys:
        verts = get_polygon_vertices(poly)
        assert len(verts) == 3

        # Check winding: Ceiling must be CW (normal points down)
        pt0 = (verts[0]["pos"][0], verts[0]["pos"][1])
        pt1 = (verts[1]["pos"][0], verts[1]["pos"][1])
        pt2 = (verts[2]["pos"][0], verts[2]["pos"][1])
        assert not is_ccw(pt0, pt1, pt2)

        # Normal must point down (0, 0, -1) and Z = wall_height
        for v in verts:
            assert v["normal"] == pytest.approx((0.0, 0.0, -1.0))
            assert v["pos"][2] == pytest.approx(3.0)

        total_ceil_area += polygon_area([pt0, pt1, pt2])

    assert total_ceil_area == pytest.approx(15.0)


def test_floor_ceiling_geometrically_closed_wall(tmp_path):
    level = Level()
    level.meta.wall_height = 3.0
    level.meta.floor_texture = "floor.png"

    # Wall loop with closed=False, but starting/ending at same coordinate
    wall = Polyline.make_wall()
    wall.closed = False
    wall.vertices = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0), (0.0, 0.0)]
    wall.texture_intervals = [
        TextureInterval(from_vertex=0, to_vertex=4, texture="wall.png")
    ]
    level.add_polyline(wall)

    # Test Floor
    floor_grp = build_floor(level, texture_dir=tmp_path)
    floor_polys = get_egg_polygons(floor_grp)

    # Area should be 16.0 (4x4 square)
    total_floor_area = 0.0
    for poly in floor_polys:
        verts = get_polygon_vertices(poly)
        assert len(verts) == 3
        pt0 = (verts[0]["pos"][0], verts[0]["pos"][1])
        pt1 = (verts[1]["pos"][0], verts[1]["pos"][1])
        pt2 = (verts[2]["pos"][0], verts[2]["pos"][1])
        total_floor_area += polygon_area([pt0, pt1, pt2])

    assert total_floor_area == pytest.approx(16.0)
