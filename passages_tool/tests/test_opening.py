"""S4: profiles, wall punch leftovers, 3D opening eggs."""
from __future__ import annotations

import pytest

from passages_tool.converter.arch_builder import build_arches
from passages_tool.converter.opening import (
    apply_volume_kind_defaults,
    collect_opening_punches,
    is_3d_opening,
    is_volume,
    leftover_patches,
    profile_polyline,
    project_opening_onto_edge,
    room_facing_normal,
    subtract_rect,
    WallHole,
    WallPatch,
)
from passages_tool.converter.wall_builder import build_wall_strips
from passages_tool.editor.level import Level, Polyline
from tests.test_wall_builder import get_egg_polygons, get_polygon_vertices


def test_profile_rect_four_corners():
    pts = profile_polyline("rect", 2.0, 0.0, 3.0)
    assert pts[0] == (0.0, 0.0)
    assert (2.0, 0.0) in pts
    assert (2.0, 3.0) in pts
    assert (0.0, 3.0) in pts
    assert len(pts) == 4


def test_profile_round_has_apex_and_more_points():
    pts = profile_polyline("round", 2.0, 0.0, 3.0, n=16)
    assert len(pts) > 4
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    assert max(zs) == 3.0  # apex at z_top
    assert min(xs) == 0.0
    assert max(xs) == 2.0
    # apex near center
    top = max(pts, key=lambda p: p[1])
    assert abs(top[0] - 1.0) < 0.05


def test_profile_gothic_pointed():
    pts = profile_polyline("gothic", 2.0, 0.0, 3.0, n=16)
    top = max(pts, key=lambda p: p[1])
    assert abs(top[0] - 1.0) < 0.08
    assert top[1] == 3.0
    assert len(pts) > 6


def test_is_3d_opening_defaults():
    a = Polyline.make_arch((0.0, 0.0))
    a.orientation = 90.0
    assert is_3d_opening(a) is False
    a.depth_m = 0.4
    assert is_3d_opening(a) is True
    a.kind = "niche"
    assert is_3d_opening(a) is False
    a.kind = "opening"
    a.depth_m = None
    assert is_3d_opening(a) is True
    a.orientation = "billboard"
    assert is_3d_opening(a) is False


def test_is_volume_not_opening():
    a = Polyline.make_arch((0.0, 0.0))
    a.orientation = 90.0
    a.kind = "volume"
    a.depth_m = 0.5
    assert is_volume(a) is True
    assert is_3d_opening(a) is False
    a.orientation = "billboard"
    assert is_volume(a) is False


def test_project_opening_onto_edge():
    hit = project_opening_onto_edge((4.0, 0.0), (6.0, 0.0), (0.0, 0.0), (10.0, 0.0))
    assert hit is not None
    assert abs(hit[0] - 0.4) < 1e-6
    assert abs(hit[1] - 0.6) < 1e-6
    miss = project_opening_onto_edge((4.0, 2.0), (6.0, 2.0), (0.0, 0.0), (10.0, 0.0))
    assert miss is None


def test_leftover_patches_middle_door():
    holes = [WallHole(t0=0.4, t1=0.6, z0=0.0, z1=2.2)]
    patches = leftover_patches(10.0, 4.0, holes)
    # left 0-4, right 6-10, above 4-6 x 2.2-4
    assert any(abs(p.s0) < 1e-6 and abs(p.s1 - 4.0) < 1e-6 and abs(p.z1 - 4.0) < 1e-6 for p in patches)
    assert any(abs(p.s0 - 6.0) < 1e-6 and abs(p.s1 - 10.0) < 1e-6 for p in patches)
    assert any(abs(p.z0 - 2.2) < 1e-6 and abs(p.s0 - 4.0) < 1e-6 for p in patches)
    # no patch covering the hole center (5, 1)
    def covers(s, z):
        return any(p.s0 - 1e-6 <= s <= p.s1 + 1e-6 and p.z0 - 1e-6 <= z <= p.z1 + 1e-6 for p in patches)
    assert not covers(5.0, 1.0)
    assert covers(1.0, 1.0)
    assert covers(5.0, 3.0)


def test_subtract_no_overlap():
    r = WallPatch(0, 10, 0, 4)
    h = WallPatch(20, 21, 0, 1)
    assert subtract_rect(r, h) == [r]


def test_arch_opening_fields_round_trip():
    level = Level()
    a = Polyline.make_arch((1.0, 2.0))
    a.orientation = 90.0
    a.kind = "opening"
    a.profile = "gothic"
    a.depth_m = 0.35
    a.side_texture = "jamb.png"
    level.add_polyline(a)
    restored = Level.from_dict(level.to_dict())
    ra = restored.arches()[0]
    assert ra.kind == "opening"
    assert ra.profile == "gothic"
    assert ra.depth_m == 0.35
    assert ra.side_texture == "jamb.png"
    plain = Polyline.make_arch((0.0, 0.0))
    d = plain.to_dict()
    assert "kind" not in d
    assert "depth_m" not in d


def _opening_level():
    level = Level()
    level.meta.wall_height = 4.0
    wall = Polyline.make_wall()
    wall.vertices = [(0.0, 0.0), (10.0, 0.0)]
    wall.texture_intervals = []
    from passages_tool.editor.polyline_data import TextureInterval
    wall.texture_intervals = [TextureInterval(0, 1, "wall.png")]
    level.add_polyline(wall)
    arch = Polyline.make_arch((5.0, 0.0))
    arch.orientation = 90.0
    arch.width = 2.0
    arch.height_override = 2.2
    arch.z_offset = 0.0
    arch.kind = "opening"
    arch.profile = "rect"
    arch.depth_m = 0.4
    arch.texture = "door.png"
    arch.transparency = "alpha_test"
    level.add_polyline(arch)
    return level, wall, arch


def test_collect_punches_hits_wall():
    level, wall, _arch = _opening_level()
    punches = collect_opening_punches(level)
    holes = punches.get((wall.id, 0))
    assert holes
    assert abs(holes[0].t0 - 0.4) < 0.02
    assert abs(holes[0].t1 - 0.6) < 0.02


def test_wall_punch_has_no_poly_in_hole(tmp_path):
    level, _wall, _arch = _opening_level()
    groups = build_wall_strips(level, texture_dir=tmp_path)
    assert groups
    polys = get_egg_polygons(groups[0])
    assert len(polys) >= 2
    # hole center ~ (5, 0, 1.0) should not lie in any wall quad (XZ at z=1)
    def poly_covers_xz(poly, x, z):
        verts = get_polygon_vertices(poly)
        xs = [v["pos"][0] for v in verts]
        zs = [v["pos"][2] for v in verts]
        ys = [v["pos"][1] for v in verts]
        return min(xs) - 0.05 <= x <= max(xs) + 0.05 and min(zs) - 0.05 <= z <= max(zs) + 0.05 and abs(sum(ys) / 4) < 0.2

    assert not any(poly_covers_xz(p, 5.0, 1.0) for p in polys)
    assert any(poly_covers_xz(p, 1.0, 1.0) for p in polys)


def test_opening_slab_has_inner_faces(tmp_path):
    level, _w, _a = _opening_level()
    groups = build_arches(level, texture_dir=tmp_path)
    assert len(groups) == 1
    polys = get_egg_polygons(groups[0])
    # rect tunnel 4 + front + back
    assert len(polys) >= 6


def test_opening_slab_omits_untextured_front_cards(tmp_path):
    level, _w, arch = _opening_level()
    arch.texture = None
    groups = build_arches(level, texture_dir=tmp_path)
    assert len(groups) == 1
    polys = get_egg_polygons(groups[0])
    # rect tunnel only (4 faces); no white bounding-rect cards
    assert len(polys) == 4


def test_card_arch_unchanged_without_kind(tmp_path):
    level = Level()
    pl = Polyline.make_arch((2.0, 3.0))
    pl.width = 4.0
    pl.height_override = 2.0
    pl.z_offset = 1.0
    pl.orientation = 90.0
    pl.texture = "arch.png"
    pl.transparency = "none"
    level.add_polyline(pl)
    polys = get_egg_polygons(build_arches(level, texture_dir=tmp_path)[0])
    assert len(polys) == 1


def test_volume_box_has_five_faces_no_punch(tmp_path):
    level = Level()
    level.meta.wall_height = 4.0
    wall = Polyline.make_wall()
    wall.vertices = [(0.0, 0.0), (10.0, 0.0)]
    from passages_tool.editor.polyline_data import TextureInterval
    wall.texture_intervals = [TextureInterval(0, 1, "wall.png")]
    level.add_polyline(wall)
    vol = Polyline.make_arch((5.0, 0.0))
    vol.orientation = 90.0
    vol.width = 0.6
    vol.kind = "volume"
    vol.depth_m = 0.5
    vol.height_override = 4.0
    vol.texture = "stone.png"
    level.add_polyline(vol)
    arch_polys = get_egg_polygons(build_arches(level, texture_dir=tmp_path)[0])
    assert len(arch_polys) == 5
    wall_polys = get_egg_polygons(build_wall_strips(level, texture_dir=tmp_path)[0])

    def covers(x, z):
        for poly in wall_polys:
            verts = get_polygon_vertices(poly)
            xs = [v["pos"][0] for v in verts]
            zs = [v["pos"][2] for v in verts]
            if min(xs) - 0.05 <= x <= max(xs) + 0.05 and min(zs) - 0.05 <= z <= max(zs) + 0.05:
                return True
        return False

    assert covers(5.0, 1.0)
    assert collect_opening_punches(level) == {}


def _closed_box_level():
    level = Level()
    level.meta.wall_height = 4.0
    wall = Polyline.make_wall()
    wall.vertices = [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)]
    wall.closed = True
    from passages_tool.editor.polyline_data import TextureInterval
    wall.texture_intervals = [TextureInterval(0, 1, "wall.png")]
    level.add_polyline(wall)
    return level


def test_room_facing_normal_closed_box_flips_180():
    level = _closed_box_level()
    # South wall y=0: author +Y is into the room.
    sx, sy = room_facing_normal(level, (4.4, 0.0), (5.6, 0.0), 0.0, 1.0)
    assert sx == pytest.approx(0.0)
    assert sy == pytest.approx(1.0)
    # North wall y=8: author +Y points out of the room.
    nx, ny = room_facing_normal(level, (4.4, 8.0), (5.6, 8.0), 0.0, 1.0)
    assert nx == pytest.approx(0.0)
    assert ny == pytest.approx(-1.0)


def test_room_facing_normal_open_wall_keeps_author():
    level = Level()
    wall = Polyline.make_wall()
    wall.vertices = [(0.0, 0.0), (10.0, 0.0)]
    level.add_polyline(wall)
    nx, ny = room_facing_normal(level, (4.4, 0.0), (5.6, 0.0), 0.0, 1.0)
    assert nx == pytest.approx(0.0)
    assert ny == pytest.approx(1.0)


def test_recess_flipped_azimuth_back_outside_room(tmp_path):
    """180° off on the north wall still extrudes into the wall, back facing in."""
    level = _closed_box_level()
    rec = Polyline.make_arch((5.0, 8.0))
    rec.orientation = 90.0  # +Y, opposite the room
    rec.width = 1.2
    rec.kind = "recess"
    rec.depth_m = 0.4
    rec.height_override = 2.0
    rec.texture = "back.png"
    rec.side_texture = "jamb.png"
    level.add_polyline(rec)
    polys = get_egg_polygons(build_arches(level, texture_dir=tmp_path)[0])
    assert len(polys) == 5
    far = get_polygon_vertices(polys[0])
    ys = [v["pos"][1] for v in far]
    assert min(ys) == pytest.approx(8.4)
    assert max(ys) == pytest.approx(8.4)
    for v in far:
        assert v["normal"][0] == pytest.approx(0.0)
        assert v["normal"][1] == pytest.approx(-1.0)


def test_recess_south_wall_back_outside_room(tmp_path):
    level = _closed_box_level()
    rec = Polyline.make_arch((5.0, 0.0))
    rec.orientation = 90.0
    rec.width = 1.2
    rec.kind = "recess"
    rec.depth_m = 0.4
    rec.height_override = 2.0
    rec.texture = "back.png"
    level.add_polyline(rec)
    polys = get_egg_polygons(build_arches(level, texture_dir=tmp_path)[0])
    far = get_polygon_vertices(polys[0])
    ys = [v["pos"][1] for v in far]
    assert max(ys) == pytest.approx(-0.4)
    for v in far:
        assert v["normal"][1] == pytest.approx(1.0)


def test_recess_back_uses_main_texture_not_side(tmp_path):
    level = Level()
    level.meta.wall_height = 4.0
    rec = Polyline.make_arch((5.0, 0.0))
    rec.orientation = 90.0
    rec.width = 1.2
    rec.kind = "recess"
    rec.depth_m = 0.4
    rec.height_override = 2.0
    rec.texture = "back.png"
    rec.side_texture = "jamb.png"
    level.add_polyline(rec)
    polys = get_egg_polygons(build_arches(level, texture_dir=tmp_path)[0])
    assert len(polys) == 5
    names = []
    for poly in polys:
        n = poly.get_num_textures()
        names.append(str(poly.get_texture(0).get_filename()) if n else "")
    assert "back.png" in names[0]
    assert all("jamb.png" in n for n in names[1:])


def test_apply_volume_kind_defaults_shrinks_door_width():
    a = Polyline.make_arch((0.0, 0.0))
    a.orientation = 90.0
    a.width = 4.0
    a.auto_snap = True
    apply_volume_kind_defaults(a)
    assert abs(a.width - 0.55) < 1e-9
    assert abs(a.depth_m - 0.45) < 1e-9
    assert a.auto_snap is False


def test_apply_volume_kind_defaults_keeps_modest_width():
    a = Polyline.make_arch((0.0, 0.0))
    a.orientation = 90.0
    a.width = 0.8
    a.depth_m = 0.3
    apply_volume_kind_defaults(a)
    assert abs(a.width - 0.8) < 1e-9
    assert abs(a.depth_m - 0.3) < 1e-9


def test_volume_ignores_auto_snap_span(tmp_path):
    level = Level()
    level.meta.wall_height = 4.0
    wall = Polyline.make_wall()
    wall.vertices = [(0.0, 0.0), (10.0, 0.0)]
    from passages_tool.editor.polyline_data import TextureInterval
    wall.texture_intervals = [TextureInterval(0, 1, "wall.png")]
    level.add_polyline(wall)
    vol = Polyline.make_arch((5.0, 0.0))
    vol.orientation = 90.0
    vol.auto_snap = True
    vol.width = 0.55
    vol.kind = "volume"
    vol.depth_m = 0.45
    vol.height_override = 4.0
    vol.texture = "stone.png"
    level.add_polyline(vol)
    polys = get_egg_polygons(build_arches(level, texture_dir=tmp_path)[0])
    xs = []
    for poly in polys:
        for v in get_polygon_vertices(poly):
            xs.append(v["pos"][0])
    assert xs
    assert max(xs) - min(xs) < 1.0


def test_billboard_ignores_depth(tmp_path):
    level = Level()
    pl = Polyline.make_arch((0.0, 0.0))
    pl.orientation = "billboard"
    pl.kind = "opening"
    pl.depth_m = 0.5
    pl.width = 2.0
    level.add_polyline(pl)
    polys = get_egg_polygons(build_arches(level, texture_dir=tmp_path)[0])
    assert len(polys) == 1
