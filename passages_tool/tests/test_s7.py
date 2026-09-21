"""S7: loop-continuous U, 3D recess, ceiling beams, no-roof."""
from __future__ import annotations

from dataclasses import replace

from passages_tool.converter.arch_builder import build_arches
from passages_tool.converter.floor_ceiling_builder import build_ceiling, ceiling_mode_for
from passages_tool.converter.opening import collect_opening_punches, is_recess
from passages_tool.converter.wall_builder import build_wall_strips
from passages_tool.editor.level import Level, Polyline
from passages_tool.editor.polyline_data import TextureInterval
from passages_tool.editor.validator import validate_textures
from passages_tool.textures.band_compose import compose_edge_diffuse
from passages_tool.textures.style import load_style
from tests.test_band_compose import _half_preset, _write_pack
from tests.test_wall_builder import get_egg_polygons, get_polygon_vertices


def test_loop_u_continues_tiling(tmp_path):
    _write_pack(tmp_path, tile=(2.0, 2.0))
    _half_preset(tmp_path / "presets" / "stone_ashlar" / "diffuse.png", 64)
    _half_preset(tmp_path / "presets" / "plaster_damp" / "diffuse.png", 64)
    pack = load_style(tmp_path / "styles" / "crypt_ashlar.json")
    assert pack.loop_u is True
    a = compose_edge_diffuse(pack, tmp_path, 1.0, 4.0, ppm=10.0, u0_m=0.0)
    b = compose_edge_diffuse(pack, tmp_path, 1.0, 4.0, ppm=10.0, u0_m=1.0)
    c = compose_edge_diffuse(pack, tmp_path, 1.0, 4.0, ppm=10.0, u0_m=2.0)
    assert a is not None and b is not None and c is not None
    # 2 m tile: offset 2 m wraps to the same strip; offset 1 m is the other half
    assert a.tobytes() == c.tobytes()
    assert a.tobytes() != b.tobytes()


def test_loop_u_false_in_style(tmp_path):
    _write_pack(tmp_path, extra={"loop_u": False})
    pack = load_style(tmp_path / "styles" / "crypt_ashlar.json")
    assert pack.loop_u is False


def test_is_recess_punches_and_has_back(tmp_path):
    a = Polyline.make_arch((5.0, 0.0))
    a.orientation = 90.0
    a.kind = "recess"
    a.depth_m = 0.5
    a.width = 2.0
    a.height_override = 2.2
    assert is_recess(a) is True
    level = Level()
    level.meta.wall_height = 4.0
    wall = Polyline.make_wall()
    wall.vertices = [(0.0, 0.0), (10.0, 0.0)]
    wall.texture_intervals = [TextureInterval(0, 1, "wall.png")]
    level.add_polyline(wall)
    level.add_polyline(a)
    punches = collect_opening_punches(level)
    assert (wall.id, 0) in punches
    groups = build_arches(level, texture_dir=tmp_path)
    assert len(get_egg_polygons(groups[0])) == 5
    wall_polys = get_egg_polygons(build_wall_strips(level, texture_dir=tmp_path)[0])

    def covers(x, z):
        for poly in wall_polys:
            verts = get_polygon_vertices(poly)
            xs = [v["pos"][0] for v in verts]
            zs = [v["pos"][2] for v in verts]
            if min(xs) - 0.05 <= x <= max(xs) + 0.05 and min(zs) - 0.05 <= z <= max(zs) + 0.05:
                return True
        return False

    assert not covers(5.0, 1.0)


def test_ceiling_mode_none_skips_fill(tmp_path):
    level = Level()
    level.meta.ceiling_mode = "none"
    level.meta.ceiling_texture = "ceil.png"
    level.meta.wall_height = 4.0
    wall = Polyline.make_wall()
    wall.vertices = [(0.0, 0.0), (0.0, 4.0), (6.0, 4.0), (6.0, 0.0)]
    wall.closed = True
    level.add_polyline(wall)
    grp = build_ceiling(level, texture_dir=tmp_path)
    assert get_egg_polygons(grp) == []
    assert ceiling_mode_for(level, None) == "none"
    level.meta.floor_texture = "floor.png"
    assert all(w.kind != "missing_ceiling" for w in validate_textures(level))


def test_ceiling_beams_add_polys(tmp_path):
    _write_pack(
        tmp_path,
        extra={
            "ceiling": {
                "preset": "crypt_ceiling",
                "tile_meters": [2.0, 2.0],
                "beams": {
                    "spacing_m": 2.0,
                    "width_m": 0.2,
                    "depth_m": 0.15,
                    "preset": "stone_ashlar",
                },
            }
        },
    )
    from tests.test_band_compose import _solid_preset

    _solid_preset(tmp_path / "presets" / "stone_ashlar" / "diffuse.png", (80, 80, 80))
    _solid_preset(tmp_path / "presets" / "plaster_damp" / "diffuse.png", (90, 90, 90))
    _solid_preset(tmp_path / "presets" / "crypt_ceiling" / "diffuse.png", (40, 40, 40))
    pack = load_style(tmp_path / "styles" / "crypt_ashlar.json")
    assert pack.ceiling is not None and pack.ceiling.beams is not None
    level = Level()
    level.meta.style = "crypt_ashlar"
    level.meta.ceiling_texture = "ceil.png"
    level.meta.wall_height = 4.0
    wall = Polyline.make_wall()
    wall.vertices = [(0.0, 0.0), (0.0, 4.0), (8.0, 4.0), (8.0, 0.0)]
    wall.closed = True
    level.add_polyline(wall)
    with_b = build_ceiling(level, texture_dir=tmp_path)
    pack_off = replace(pack, ceiling=replace(pack.ceiling, beams=None))
    # no style on a copy
    level2 = Level()
    level2.meta.ceiling_texture = "ceil.png"
    level2.meta.wall_height = 4.0
    level2.add_polyline(wall)
    plain = build_ceiling(level2, texture_dir=tmp_path)
    assert len(get_egg_polygons(with_b)) > len(get_egg_polygons(plain))


def test_ceiling_mode_round_trip():
    level = Level()
    level.meta.ceiling_mode = "none"
    restored = Level.from_dict(level.to_dict())
    assert restored.meta.ceiling_mode == "none"
    assert "ceiling_mode" in level.to_dict()["meta"]
