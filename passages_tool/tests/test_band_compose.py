"""S2: band compose in meters; independent of preset pixel size."""
from __future__ import annotations

import json

import pytest
from PIL import Image

from passages_tool.converter.wall_builder import build_wall_strips
from passages_tool.editor.level import Level, Polyline, TextureInterval
from passages_tool.textures.band_compose import (
    COMPOSE_U_MAX,
    compose_edge_diffuse,
    compose_size_px,
    sample_wrap,
)
from passages_tool.textures.style import load_style
from tests.test_wall_builder import get_egg_polygons, get_polygon_vertices


def _half_preset(path, size: int) -> None:
    """Left half black, right half white — UV 0.25 vs 0.75 regardless of size."""
    im = Image.new("RGB", (size, size), (255, 255, 255))
    for x in range(size // 2):
        for y in range(size):
            im.putpixel((x, y), (0, 0, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "PNG")


def _solid_preset(path, rgb) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), rgb).save(path, "PNG")


def _write_pack(root, *, tile=(2.0, 2.0), bands=None, extra=None) -> None:
    styles = root / "styles"
    styles.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "id": "crypt_ashlar",
        "wall_height_m": 4.0,
        "bands": bands
        or [
            {"id": "plinth", "z": [0.0, 0.4], "preset": "stone_ashlar", "tile_meters": list(tile)},
            {"id": "field", "z": [0.4, 4.0], "preset": "plaster_damp", "tile_meters": list(tile)},
        ],
        "opening_profiles": ["rect"],
        "default_opening": {"profile": "rect", "depth_m": 0.4},
    }
    if extra:
        data.update(extra)
    (styles / "crypt_ashlar.json").write_text(json.dumps(data), encoding="utf-8")


def test_compose_size_7p3m_at_ppm_10():
    w, h = compose_size_px(7.3, 4.0, 10.0)
    assert w == 73
    assert h == 40


def test_7p3m_tiles_independent_of_preset_px(tmp_path):
    """Same tile_meters + 7.3 m edge: 64² and 512² presets sample the same world U."""
    _write_pack(tmp_path, tile=(2.0, 2.0))
    pack = load_style(tmp_path / "styles" / "crypt_ashlar.json")
    for size in (64, 512):
        _half_preset(tmp_path / "presets" / "stone_ashlar" / "diffuse.png", size)
        _half_preset(tmp_path / "presets" / "plaster_damp" / "diffuse.png", size)
        img = compose_edge_diffuse(pack, tmp_path, 7.3, 4.0, ppm=10.0)
        assert img is not None
        assert img.size == (73, 40)
        # s=0.5 m → u=0.25 → left half black; s=1.5 m → u=0.75 → white
        # z=0.2 m plinth; image y from top: z from bottom
        ppm = 10.0
        h = 40
        y_plinth = h - 1 - int(0.2 * ppm)  # near floor
        x_black = int(0.5 * ppm)
        x_white = int(1.5 * ppm)
        assert img.getpixel((x_black, y_plinth))[0] < 40
        assert img.getpixel((x_white, y_plinth))[0] > 200
        # also at 6.5 m (u = 6.5/2 = 3.25 → 0.25 wrap → black)
        x_wrap = int(6.5 * ppm)
        assert img.getpixel((x_wrap, y_plinth))[0] < 40


def test_band_z_selects_preset(tmp_path):
    _write_pack(tmp_path)
    _solid_preset(tmp_path / "presets" / "stone_ashlar" / "diffuse.png", (255, 0, 0))
    _solid_preset(tmp_path / "presets" / "plaster_damp" / "diffuse.png", (0, 255, 0))
    pack = load_style(tmp_path / "styles" / "crypt_ashlar.json")
    img = compose_edge_diffuse(pack, tmp_path, 2.0, 4.0, ppm=10.0)
    assert img is not None
    h = img.size[1]
    y_plinth = h - 1 - int(0.2 * 10)
    y_field = h - 1 - int(2.0 * 10)
    assert img.getpixel((5, y_plinth))[0] > 200
    assert img.getpixel((5, y_field))[1] > 200


def test_compose_too_wide_returns_none(tmp_path):
    _write_pack(tmp_path)
    _solid_preset(tmp_path / "presets" / "stone_ashlar" / "diffuse.png", (1, 1, 1))
    _solid_preset(tmp_path / "presets" / "plaster_damp" / "diffuse.png", (2, 2, 2))
    pack = load_style(tmp_path / "styles" / "crypt_ashlar.json")
    length = (COMPOSE_U_MAX + 10) / 256.0
    assert compose_edge_diffuse(pack, tmp_path, length, 4.0, ppm=256.0) is None


def test_sample_wrap_v0_is_image_bottom():
    im = Image.new("RGB", (2, 2), (0, 0, 0))
    im.putpixel((0, 1), (255, 0, 0))  # bottom-left
    assert sample_wrap(im, 0.0, 0.0)[0] > 200


def test_no_style_keeps_legacy_uv(tmp_path):
    level = Level()
    level.meta.pixels_per_meter = 256.0
    level.meta.wall_height = 3.0
    pl = Polyline.make_wall()
    pl.vertices = [(0.0, 0.0), (2.0, 0.0), (5.0, 0.0)]
    pl.texture_intervals = [
        TextureInterval(from_vertex=0, to_vertex=2, texture="wall.png", x_offset=0.0)
    ]
    level.add_polyline(pl)
    groups = build_wall_strips(level, texture_dir=tmp_path)
    u_s1 = [v["uv"][0] for v in get_polygon_vertices(get_egg_polygons(groups[0])[0])]
    assert min(u_s1) == pytest.approx(0.0)
    assert max(u_s1) == pytest.approx(1.0)


def test_style_wall_uses_unique_uv_0_1(tmp_path):
    _write_pack(tmp_path)
    _solid_preset(tmp_path / "presets" / "stone_ashlar" / "diffuse.png", (255, 0, 0))
    _solid_preset(tmp_path / "presets" / "plaster_damp" / "diffuse.png", (0, 255, 0))
    level = Level()
    level.meta.style = "crypt_ashlar"
    level.meta.pixels_per_meter = 10.0
    level.meta.wall_height = 4.0
    pl = Polyline.make_wall()
    pl.vertices = [(0.0, 0.0), (7.3, 0.0)]
    level.add_polyline(pl)
    groups = build_wall_strips(level, texture_dir=tmp_path)
    verts = get_polygon_vertices(get_egg_polygons(groups[0])[0])
    us = [v["uv"][0] for v in verts]
    vs = [v["uv"][1] for v in verts]
    assert min(us) == pytest.approx(0.0)
    assert max(us) == pytest.approx(1.0)
    assert min(vs) == pytest.approx(0.0)
    assert max(vs) == pytest.approx(1.0)
    cache = list((tmp_path / "_style_cache").rglob("*.png"))
    assert cache, "unique map should be written"


def test_interval_png_override_keeps_legacy_uv(tmp_path):
    _write_pack(tmp_path)
    _solid_preset(tmp_path / "presets" / "stone_ashlar" / "diffuse.png", (255, 0, 0))
    _solid_preset(tmp_path / "presets" / "plaster_damp" / "diffuse.png", (0, 255, 0))
    level = Level()
    level.meta.style = "crypt_ashlar"
    level.meta.pixels_per_meter = 256.0
    level.meta.wall_height = 3.0
    pl = Polyline.make_wall()
    pl.vertices = [(0.0, 0.0), (2.0, 0.0)]
    pl.texture_intervals = [
        TextureInterval(from_vertex=0, to_vertex=1, texture="wall.png")
    ]
    level.add_polyline(pl)
    groups = build_wall_strips(level, texture_dir=tmp_path)
    us = [v["uv"][0] for v in get_polygon_vertices(get_egg_polygons(groups[0])[0])]
    # 2 m * 256 / 512 = 1.0 — override, not unique 0..1 of a 2m map
    assert min(us) == pytest.approx(0.0)
    assert max(us) == pytest.approx(1.0)
    assert not list((tmp_path / "_style_cache").rglob("*.png"))
