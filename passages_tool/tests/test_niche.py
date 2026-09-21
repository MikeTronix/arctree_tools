"""S5: POM niches — height dip, no wall punch."""
from __future__ import annotations

from PIL import Image

from passages_tool.converter.opening import (
    WallHole,
    collect_niche_spans,
    collect_opening_punches,
    is_3d_opening,
    is_niche,
)
from passages_tool.converter.wall_builder import build_wall_strips
from passages_tool.editor.level import Level, Polyline
from passages_tool.editor.polyline_data import TextureInterval
from passages_tool.renderer.pom import height_sibling_path
from passages_tool.renderer.shader_probe import SHADER_DIR
from passages_tool.textures.band_compose import write_edge_diffuse
from passages_tool.textures.niche import apply_niche_dip
from passages_tool.textures.style import load_style
from tests.test_band_compose import _solid_preset, _write_pack
from tests.test_wall_builder import get_egg_polygons, get_polygon_vertices


def test_pom_shaders_exist():
    assert (SHADER_DIR / "pom.vert.glsl").is_file()
    assert (SHADER_DIR / "pom.frag.glsl").is_file()


def test_is_niche_not_opening():
    a = Polyline.make_arch((0.0, 0.0))
    a.orientation = 90.0
    a.kind = "niche"
    a.depth_m = 0.4
    assert is_niche(a) is True
    assert is_3d_opening(a) is False
    a.kind = "opening"
    assert is_niche(a) is False
    assert is_3d_opening(a) is True


def test_apply_niche_dip_lowers_center():
    albedo = Image.new("RGB", (80, 40), (200, 200, 200))
    height = Image.new("L", (80, 40), 255)
    apply_niche_dip(
        albedo, height, [WallHole(0.4, 0.6, 0.0, 2.2)], 8.0, 4.0, 10.0
    )
    # s=4 m, z=1 m → x=40, y = 39 - 10 = 29
    assert height.getpixel((40, 29)) < 80
    assert albedo.getpixel((40, 29))[0] < 185
    assert height.getpixel((5, 20)) == 255
    assert albedo.getpixel((5, 20))[0] >= 195


def test_height_sibling_path(tmp_path):
    d = tmp_path / "_style_cache" / "s"
    d.mkdir(parents=True)
    (d / "wall_a_e0.png").write_bytes(b"x")
    (d / "wall_a_e0_h.png").write_bytes(b"h")
    p = height_sibling_path(tmp_path, "_style_cache/s/wall_a_e0.png")
    assert p is not None and p.name == "wall_a_e0_h.png"
    assert height_sibling_path(tmp_path, "plain.png") is None


def _styled_wall_with_arch(tmp_path, kind: str):
    _write_pack(tmp_path)
    _solid_preset(tmp_path / "presets" / "stone_ashlar" / "diffuse.png", (180, 180, 180))
    _solid_preset(tmp_path / "presets" / "plaster_damp" / "diffuse.png", (200, 200, 200))
    level = Level()
    level.meta.style = "crypt_ashlar"
    level.meta.wall_height = 4.0
    level.meta.pixels_per_meter = 10.0
    wall = Polyline.make_wall()
    wall.vertices = [(0.0, 0.0), (10.0, 0.0)]
    level.add_polyline(wall)
    arch = Polyline.make_arch((5.0, 0.0))
    arch.orientation = 90.0
    arch.width = 2.0
    arch.height_override = 2.2
    arch.z_offset = 0.0
    arch.kind = kind
    arch.depth_m = 0.4
    level.add_polyline(arch)
    return level, wall


def test_niche_span_collected_not_punched():
    level = Level()
    level.meta.wall_height = 4.0
    wall = Polyline.make_wall()
    wall.vertices = [(0.0, 0.0), (10.0, 0.0)]
    level.add_polyline(wall)
    arch = Polyline.make_arch((5.0, 0.0))
    arch.orientation = 90.0
    arch.width = 2.0
    arch.height_override = 2.2
    arch.kind = "niche"
    level.add_polyline(arch)
    assert collect_opening_punches(level) == {}
    spans = collect_niche_spans(level)
    assert (wall.id, 0) in spans


def test_niche_does_not_punch_wall(tmp_path):
    level, _wall = _styled_wall_with_arch(tmp_path, "niche")
    groups = build_wall_strips(level, texture_dir=tmp_path)
    polys = get_egg_polygons(groups[0])

    def covers(x, z):
        for poly in polys:
            verts = get_polygon_vertices(poly)
            xs = [v["pos"][0] for v in verts]
            zs = [v["pos"][2] for v in verts]
            if min(xs) - 0.05 <= x <= max(xs) + 0.05 and min(zs) - 0.05 <= z <= max(zs) + 0.05:
                return True
        return False

    assert covers(5.0, 1.0)
    hs = list(tmp_path.rglob("*_h.png"))
    assert hs, "niche should write a height map"


def test_write_edge_with_niche_writes_height(tmp_path):
    _write_pack(tmp_path)
    _solid_preset(tmp_path / "presets" / "stone_ashlar" / "diffuse.png", (180, 180, 180))
    _solid_preset(tmp_path / "presets" / "plaster_damp" / "diffuse.png", (200, 200, 200))
    pack = load_style(tmp_path / "styles" / "crypt_ashlar.json")
    holes = [WallHole(0.2, 0.5, 0.0, 2.0)]
    rel = write_edge_diffuse(
        pack, tmp_path, "wid", 0, 8.0, 4.0, 10.0, niches=holes
    )
    assert rel
    h = tmp_path / rel.replace(".png", "_h.png")
    assert h.is_file()
    himg = Image.open(h)
    assert himg.mode in ("L", "RGB")
    # center of hole s=2.8 z=1
    x = int(2.8 * 10)
    y = himg.size[1] - 1 - int(1.0 * 10)
    px = himg.getpixel((x, y))
    val = px if isinstance(px, int) else px[0]
    assert val < 200
