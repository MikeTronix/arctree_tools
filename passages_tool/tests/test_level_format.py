"""
tests/test_level_format.py — Integration tests for JSON save/load.
Uses a tmp_path fixture so no real files are left on disk.
"""
import json
import pytest

from passages_tool.editor.level import Level, Polyline
from passages_tool.io.level_format import LevelIOError, load, save


def make_populated_level() -> Level:
    level = Level()
    level.meta.name = "Test Level"
    level.set_tile(0, 0, "floor.png")
    pl = Polyline.make_new()
    level.add_polyline(pl)
    level.add_vertex(pl.id, 1.0, 2.0)
    level.add_vertex(pl.id, 3.0, 4.0)
    level.set_polyline_texture(pl.id, "wall.png")
    return level


def test_save_creates_file(tmp_path):
    level = make_populated_level()
    out = tmp_path / "test.passages.json"
    save(level, out)
    assert out.exists()


def test_save_appends_extension(tmp_path):
    level = make_populated_level()
    out = tmp_path / "test"
    save(level, out)
    # The file should have been created with the full extension.
    files = list(tmp_path.glob("*.passages.json"))
    assert len(files) == 1


def test_save_clears_dirty(tmp_path):
    level = make_populated_level()
    level.dirty = True
    out = tmp_path / "test.passages.json"
    save(level, out)
    assert not level.dirty


def test_round_trip(tmp_path):
    level = make_populated_level()
    out = tmp_path / "rt.passages.json"
    save(level, out)
    restored = load(out)

    assert restored.meta.name == "Test Level"
    t = restored.get_tile(0, 0)
    assert t is not None and t.texture == "floor.png"
    pls = list(restored.polylines.values())
    assert len(pls[0].texture_intervals) == 1
    assert pls[0].texture_intervals[0].texture == "wall.png"
    assert len(pls[0].vertices) == 2


def test_load_nonexistent_raises(tmp_path):
    with pytest.raises(LevelIOError, match="File not found"):
        load(tmp_path / "no_such_file.passages.json")


def test_load_bad_json_raises(tmp_path):
    bad = tmp_path / "bad.passages.json"
    bad.write_text("{ not valid json }", encoding="utf-8")
    with pytest.raises(LevelIOError, match="Invalid JSON"):
        load(bad)


def test_load_future_version_raises(tmp_path):
    data = Level().to_dict()
    data["version"] = 9999
    future = tmp_path / "future.passages.json"
    future.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(LevelIOError, match="newer than this tool"):
        load(future)
