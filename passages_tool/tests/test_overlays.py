"""S3: seeded overlay stamps. Density 0 = S2 golden."""
from __future__ import annotations

from dataclasses import replace

from PIL import Image

from passages_tool.textures.band_compose import compose_edge_diffuse
from passages_tool.textures.overlays import apply_overlays, stamp_count, overlay_rng
from passages_tool.textures.style import load_style
from tests.test_band_compose import _solid_preset, _write_pack


def _pack(tmp_path, **overlay_kw):
    _write_pack(tmp_path)
    _solid_preset(tmp_path / "presets" / "stone_ashlar" / "diffuse.png", (180, 180, 180))
    _solid_preset(tmp_path / "presets" / "plaster_damp" / "diffuse.png", (200, 200, 200))
    pack = load_style(tmp_path / "styles" / "crypt_ashlar.json")
    if overlay_kw:
        pack = replace(pack, overlays=replace(pack.overlays, **overlay_kw))
    return pack


def test_stamp_count_zero_density():
    rng = overlay_rng("x")
    assert stamp_count(0.0, 100.0, 1.0, rng) == 0
    assert stamp_count(-1.0, 100.0, 1.0, rng) == 0


def test_density_zero_matches_s2_golden(tmp_path):
    pack = _pack(tmp_path)
    a = compose_edge_diffuse(pack, tmp_path, 4.0, 4.0, ppm=8.0, wall_id="w", edge_idx=0)
    pack_wet = replace(pack, overlays=replace(pack.overlays, wetness=0.0, moss=0.0, graffiti=0.0))
    b = compose_edge_diffuse(pack_wet, tmp_path, 4.0, 4.0, ppm=8.0, wall_id="w", edge_idx=0)
    pack_on = replace(pack, overlays=replace(pack.overlays, wetness=1.0))
    c = compose_edge_diffuse(pack_on, tmp_path, 4.0, 4.0, ppm=8.0, wall_id="w", edge_idx=0)
    assert a is not None and b is not None and c is not None
    assert a.tobytes() == b.tobytes()
    assert a.tobytes() != c.tobytes()


def test_same_seed_same_pixels(tmp_path):
    pack = _pack(tmp_path, wetness=1.0, moss=0.5)
    a = compose_edge_diffuse(
        pack, tmp_path, 8.0, 4.0, ppm=8.0, wall_id="wallA", edge_idx=0, overlay_seed=17
    )
    b = compose_edge_diffuse(
        pack, tmp_path, 8.0, 4.0, ppm=8.0, wall_id="wallA", edge_idx=0, overlay_seed=17
    )
    assert a is not None and b is not None
    assert a.tobytes() == b.tobytes()


def test_overlay_seed_and_wall_id_change_pixels(tmp_path):
    pack = _pack(tmp_path, wetness=1.0)
    kwargs = dict(texture_dir=tmp_path, length_m=8.0, height_m=4.0, ppm=8.0)
    a = compose_edge_diffuse(pack, wall_id="w0", edge_idx=0, overlay_seed=1, **kwargs)
    b = compose_edge_diffuse(pack, wall_id="w0", edge_idx=0, overlay_seed=2, **kwargs)
    c = compose_edge_diffuse(pack, wall_id="w1", edge_idx=0, overlay_seed=1, **kwargs)
    d = compose_edge_diffuse(pack, wall_id="w0", edge_idx=1, overlay_seed=1, **kwargs)
    assert a is not None
    assert a.tobytes() != b.tobytes()
    assert a.tobytes() != c.tobytes()
    assert a.tobytes() != d.tobytes()


def test_apply_overlays_noop_on_zero_density():
    im = Image.new("RGB", (16, 16), (10, 20, 30))
    from passages_tool.textures.style import (
        StyleOpeningDefaults,
        StyleNiche,
        StylePack,
        StyleBand,
        StyleOverlays as Ov,
    )

    pack = StylePack(
        version=1,
        id="t",
        wall_height_m=4.0,
        bands=(StyleBand("f", 0.0, 4.0, "p"),),
        opening_profiles=("rect",),
        default_opening=StyleOpeningDefaults(),
        niche=StyleNiche(),
        overlays=Ov(wetness=0.0, moss=0.0, graffiti=0.0),
    )
    before = im.tobytes()
    apply_overlays(im, pack, 2.0, 2.0, 8.0, wall_id="x", edge_idx=0)
    assert im.tobytes() == before


def test_optional_overlay_mask(tmp_path):
    pack = _pack(tmp_path, wetness=1.0, moss=0.0, graffiti=0.0)
    mask_dir = tmp_path / "overlays"
    mask_dir.mkdir()
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(mask_dir / "wetness.png")
    img = compose_edge_diffuse(
        pack, tmp_path, 8.0, 4.0, ppm=8.0, wall_id="w", edge_idx=0, overlay_seed=3
    )
    assert img is not None
    pix = img.load()
    w, h = img.size
    assert any(pix[x, y][0] > pix[x, y][1] + 20 for y in range(h) for x in range(w))
