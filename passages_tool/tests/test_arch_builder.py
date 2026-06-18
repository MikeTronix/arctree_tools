"""
tests/test_arch_builder.py
──────────────────────────
Tests for arch and lighting geometry builders.
"""
from __future__ import annotations

import math
from pathlib import Path
import pytest

from panda3d.egg import EggGroup, EggTexture, EggTransform
from panda3d.core import LVecBase3d, NodePath, PointLight, AmbientLight

from passages_tool.converter.arch_builder import build_arches
from passages_tool.converter.lighting_builder import setup_lighting
from passages_tool.editor.level import Level, Polyline, PolylineType, TextureInterval
from tests.test_wall_builder import get_egg_polygons, get_polygon_vertices


def test_fixed_arch_quad(tmp_path):
    level = Level()
    level.meta.wall_height = 3.0
    level.meta.pixels_per_meter = 256.0

    pl = Polyline.make_arch((2.0, 3.0))
    pl.width = 4.0
    pl.height_override = 2.0
    pl.z_offset = 1.0
    # orientation = 90.0 (points along Y, width along Y axis)
    pl.orientation = 90.0
    pl.texture = "arch.png"
    pl.transparency = "none"
    level.add_polyline(pl)

    groups = build_arches(level, texture_dir=tmp_path)
    assert len(groups) == 1

    # Check EGG group
    grp = groups[0]
    assert grp.get_name() == f"arch_{pl.id}"

    polys = get_egg_polygons(grp)
    assert len(polys) == 1

    verts = get_polygon_vertices(polys[0])
    assert len(verts) == 4

    # Rotated by 90 deg: cos(90)=0, sin(90)=1.
    # Facing normal points along Y: (0.0, 1.0, 0.0).
    # Width vector is perpendicular to normal: (dx_w, dy_w) = (2.0 * -sin(90), 2.0 * cos(90)) = (-2.0, 0.0).
    # Left edge = (2.0 - (-2.0), 3.0 - 0.0) = (4.0, 3.0)
    # Right edge = (2.0 + (-2.0), 3.0 + 0.0) = (0.0, 3.0)
    # Z ranges from z_offset (1.0) to z_offset + height (3.0)
    expected_positions = {
        (0.0, 3.0, 1.0),
        (4.0, 3.0, 1.0),
        (4.0, 3.0, 3.0),
        (0.0, 3.0, 3.0),
    }

    actual_positions = [v["pos"] for v in verts]

    # Matches expected positions set
    for exp in expected_positions:
        assert any(
            act[0] == pytest.approx(exp[0])
            and act[1] == pytest.approx(exp[1])
            and act[2] == pytest.approx(exp[2])
            for act in actual_positions
        )

    # Normal should point along facing direction: (cos(90), sin(90), 0.0) = (0.0, 1.0, 0.0)
    for v in verts:
        assert v["normal"] == pytest.approx((0.0, 1.0, 0.0))


def test_billboard_arch(tmp_path):
    level = Level()
    pl = Polyline.make_arch((5.0, 10.0))
    pl.width = 3.0
    pl.height_override = 3.5
    pl.z_offset = 0.5
    pl.orientation = "billboard"
    pl.texture = "sprite.png"
    level.add_polyline(pl)

    groups = build_arches(level, texture_dir=tmp_path)
    assert len(groups) == 1
    grp = groups[0]

    # Verify billboard flag is BT_axis
    assert grp.get_billboard_type() == EggGroup.BT_axis

    # Verify transform translates to (5.0, 10.0, 0.0)
    assert grp.has_transform3d()
    t3d = grp.get_transform3d()
    row3 = t3d.get_row(3)
    assert row3[0] == pytest.approx(5.0)
    assert row3[1] == pytest.approx(10.0)
    assert row3[2] == pytest.approx(0.0)

    # Verify local vertices are centered at X = -1.5 to 1.5, Y = 0
    polys = get_egg_polygons(grp)
    verts = get_polygon_vertices(polys[0])

    xs = [v["pos"][0] for v in verts]
    ys = [v["pos"][1] for v in verts]
    zs = [v["pos"][2] for v in verts]

    assert min(xs) == pytest.approx(-1.5)
    assert max(xs) == pytest.approx(1.5)
    for y in ys:
        assert y == pytest.approx(0.0)
    assert min(zs) == pytest.approx(0.5)
    assert max(zs) == pytest.approx(4.0)


def test_v_at_floor(tmp_path):
    level = Level()
    level.meta.pixels_per_meter = 256.0

    # Texture size default is 512x512
    # Case A: v_at_floor = False
    pl_a = Polyline.make_arch((0.0, 0.0))
    pl_a.height_override = 2.0
    pl_a.z_offset = 1.0
    pl_a.v_at_floor = False
    pl_a.texture = "a.png"
    level.add_polyline(pl_a)

    # Case B: v_at_floor = True
    pl_b = Polyline.make_arch((0.0, 0.0))
    pl_b.height_override = 2.0
    pl_b.z_offset = 1.0
    pl_b.v_at_floor = True
    pl_b.texture = "b.png"
    level.add_polyline(pl_b)

    groups = build_arches(level, texture_dir=tmp_path)
    assert len(groups) == 2

    # Verify Case A
    polys_a = get_egg_polygons(groups[0])
    verts_a = get_polygon_vertices(polys_a[0])
    v_vals_a = [v["uv"][1] for v in verts_a]
    # Height = 2.0, ppm = 256, tex_h = 512 -> 2.0*256/512 = 1.0
    assert min(v_vals_a) == pytest.approx(0.0)
    assert max(v_vals_a) == pytest.approx(1.0)

    # Verify Case B
    polys_b = get_egg_polygons(groups[1])
    verts_b = get_polygon_vertices(polys_b[0])
    v_vals_b = [v["uv"][1] for v in verts_b]
    # z_offset = 1.0 -> v_bottom = 1.0*256/512 = 0.5
    # z_top = 3.0 -> v_top = 3.0*256/512 = 1.5
    assert min(v_vals_b) == pytest.approx(0.5)
    assert max(v_vals_b) == pytest.approx(1.5)


def test_transparency_mode(tmp_path):
    level = Level()
    
    pl_none = Polyline.make_arch((0.0, 0.0))
    pl_none.texture = "none.png"
    pl_none.transparency = "none"
    level.add_polyline(pl_none)

    pl_test = Polyline.make_arch((0.0, 0.0))
    pl_test.texture = "test.png"
    pl_test.transparency = "alpha_test"
    level.add_polyline(pl_test)

    pl_blend = Polyline.make_arch((0.0, 0.0))
    pl_blend.texture = "blend.png"
    pl_blend.transparency = "alpha_blend"
    level.add_polyline(pl_blend)

    # We can retrieve textures from the generated EGG context inside the group
    groups = build_arches(level, texture_dir=tmp_path)
    assert len(groups) == 3

    def get_texture_node(group) -> EggTexture:
        polys = get_egg_polygons(group)
        return polys[0].get_texture()

    tex_none = get_texture_node(groups[0])
    assert tex_none.get_alpha_mode() == EggTexture.AM_off

    tex_test = get_texture_node(groups[1])
    assert tex_test.get_alpha_mode() == EggTexture.AM_binary

    tex_blend = get_texture_node(groups[2])
    assert tex_blend.get_alpha_mode() == EggTexture.AM_blend


def test_setup_lighting():
    level = Level()
    pl = Polyline.make_arch((4.0, 5.0))
    pl.is_light_source = True
    pl.light_color = (1.0, 0.5, 0.2)
    pl.light_intensity = 3.0
    pl.z_offset = 0.5
    pl.height_override = 2.0
    level.add_polyline(pl)

    root = NodePath("scene_root")
    light_paths = setup_lighting(root, level)
    
    # Verify paths list: 1 ambient + 1 point light
    assert len(light_paths) == 2
    
    # Verify ambient light is attached
    ambient_found = False
    point_found = False
    for lp in light_paths:
        node = lp.node()
        if isinstance(node, AmbientLight):
            ambient_found = True
        elif isinstance(node, PointLight):
            point_found = True
            # Check position: (4.0, 5.0, z_offset + height/2 = 0.5 + 1.0 = 1.5)
            pos = lp.get_pos()
            assert pos[0] == pytest.approx(4.0)
            assert pos[1] == pytest.approx(5.0)
            assert pos[2] == pytest.approx(1.5)
            
            # Check color: (1.0*3, 0.5*3, 0.2*3) = (3.0, 1.5, 0.6)
            color = node.get_color()
            assert color[0] == pytest.approx(3.0)
            assert color[1] == pytest.approx(1.5)
            assert color[2] == pytest.approx(0.6)

    assert ambient_found
    assert point_found
