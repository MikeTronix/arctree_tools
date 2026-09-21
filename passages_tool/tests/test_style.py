"""S1: style JSON load + Validate. No compose / GPU."""
from __future__ import annotations

import json

import pytest

from passages_tool.editor.level import Level
from passages_tool.editor.validator import validate_style
from passages_tool.textures.style import (
    StyleError,
    load_style,
    preset_has_diffuse,
    style_json_path,
)


def _write_style(root, *, name="crypt_ashlar", extra=None, bands=None):
    styles = root / "styles"
    styles.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "id": name,
        "wall_height_m": 4.0,
        "bands": bands
        or [
            {
                "id": "plinth",
                "z": [0.0, 0.4],
                "preset": "stone_ashlar",
                "tile_meters": [1.0, 0.4],
            },
            {
                "id": "field",
                "z": [0.4, 3.2],
                "preset": "plaster_damp",
                "tile_meters": [2.0, 2.0],
                "pom": True,
                "height_scale_m": 0.05,
            },
        ],
        "opening_profiles": ["rect", "round", "gothic"],
        "default_opening": {
            "profile": "gothic",
            "depth_m": 0.4,
            "side_preset": "stone_ashlar",
        },
        "niche": {"height_scale_m": 0.35, "pom": True},
        "overlays": {"seed": 0, "wetness": 0.15, "moss": 0.08},
        "ceiling": {"preset": "crypt_ceiling", "tile_meters": [2.0, 2.0]},
        "floor": {"preset": "crypt_floor", "tile_meters": [2.0, 2.0]},
    }
    if extra:
        data.update(extra)
    path = styles / f"{name}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _touch_preset(root, preset_id: str) -> None:
    d = root / "presets" / preset_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "diffuse.png").write_bytes(b"\x89PNG\r\n")


def test_style_json_path_id_and_relative(tmp_path):
    assert style_json_path(tmp_path, "crypt_ashlar") == tmp_path / "styles" / "crypt_ashlar.json"
    assert style_json_path(tmp_path, "styles/foo.json") == tmp_path / "styles" / "foo.json"


def test_load_style_round_trip(tmp_path):
    path = _write_style(tmp_path)
    pack = load_style(path)
    assert pack.id == "crypt_ashlar"
    assert pack.version == 1
    assert len(pack.bands) == 2
    assert pack.bands[0].id == "plinth"
    assert pack.bands[0].z0 == 0.0
    assert pack.bands[1].pom is True
    assert pack.default_opening.profile == "gothic"
    assert pack.default_opening.side_preset == "stone_ashlar"
    assert pack.ceiling.preset == "crypt_ceiling"
    assert pack.preset_ids() == (
        "stone_ashlar",
        "plaster_damp",
        "crypt_ceiling",
        "crypt_floor",
    )


def test_load_style_rejects_bad_version(tmp_path):
    path = _write_style(tmp_path, extra={"version": 2})
    with pytest.raises(StyleError, match="version"):
        load_style(path)


def test_load_style_rejects_empty_bands(tmp_path):
    path = _write_style(tmp_path, extra={"bands": []})
    with pytest.raises(StyleError, match="bands"):
        load_style(path)


def test_validate_style_skips_when_unset():
    level = Level()
    assert validate_style(level, None) == []
    assert validate_style(level, None) == validate_style(level)


def test_validate_style_missing_file(tmp_path):
    level = Level()
    level.meta.style = "nope"
    w = validate_style(level, tmp_path)
    assert [x.kind for x in w] == ["style_missing"]


def test_validate_style_no_texture_dir():
    level = Level()
    level.meta.style = "crypt_ashlar"
    w = validate_style(level, None)
    assert [x.kind for x in w] == ["style_no_texture_dir"]


def test_validate_style_missing_preset(tmp_path):
    _write_style(tmp_path)
    _touch_preset(tmp_path, "stone_ashlar")
    # plaster_damp, ceiling, floor missing
    level = Level()
    level.meta.style = "crypt_ashlar"
    kinds = {x.kind for x in validate_style(level, tmp_path)}
    assert "preset_missing_diffuse" in kinds
    assert not preset_has_diffuse(tmp_path, "plaster_damp")


def test_validate_style_ok_when_presets_exist(tmp_path):
    _write_style(tmp_path)
    for name in ("stone_ashlar", "plaster_damp", "crypt_ceiling", "crypt_floor"):
        _touch_preset(tmp_path, name)
    level = Level()
    level.meta.style = "crypt_ashlar"
    assert validate_style(level, tmp_path) == []


def test_demo_crypt_ashlar_pack_validates():
    from passages_tool.config import TOOL_ROOT
    from passages_tool.io.level_format import load

    tex = TOOL_ROOT / "assets" / "sample_textures"
    style = tex / "styles" / "crypt_ashlar.json"
    if not style.is_file():
        pytest.skip("demo style pack not present")
    pack = load_style(style)
    assert pack.id == "crypt_ashlar"
    assert len(pack.bands) == 3
    level = Level()
    level.meta.style = "crypt_ashlar"
    assert validate_style(level, tex) == []
    demo = TOOL_ROOT / "json" / "style_demo.passages.json"
    if demo.is_file():
        loaded = load(demo)
        assert loaded.meta.style == "crypt_ashlar"
        kinds = {a.kind for a in loaded.arches()}
        assert "opening" in kinds and "niche" in kinds and "volume" in kinds


def test_level_style_round_trip_omits_defaults():
    level = Level()
    d = level.to_dict()
    assert "style" not in d["meta"]
    assert "overlay_seed" not in d["meta"]
    assert "pom_enabled" not in d["meta"]

    level.meta.style = "crypt_ashlar"
    level.meta.overlay_seed = 17
    level.meta.pom_enabled = True
    restored = Level.from_dict(level.to_dict())
    assert restored.meta.style == "crypt_ashlar"
    assert restored.meta.overlay_seed == 17
    assert restored.meta.pom_enabled is True
    assert restored.to_dict()["meta"]["style"] == "crypt_ashlar"
