"""4.2: combined scene.egg is File-includes, not a second tessellation."""
from __future__ import annotations

from panda3d.core import DSearchPath, Filename
from panda3d.egg import EggData, EggPolygon

from passages_tool.converter import scene_builder as sb
from passages_tool.converter.scene_builder import (
    COMPONENT_EGG_STEMS,
    build_scene,
)
from passages_tool.editor.level import Level, Polyline, TextureInterval


def _level_with_textured_wall() -> Level:
    level = Level()
    pl = Polyline.make_wall()
    pl.vertices = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
    pl.closed = True
    pl.texture_intervals = [
        TextureInterval(from_vertex=0, to_vertex=3, texture="wall.png")
    ]
    level.add_polyline(pl)
    return level


def _count_polygons(egg: EggData) -> int:
    n = 0

    def walk(node) -> None:
        nonlocal n
        if isinstance(node, EggPolygon):
            n += 1
        if hasattr(node, "get_first_child"):
            child = node.get_first_child()
            while child is not None:
                walk(child)
                child = node.get_next_child()

    walk(egg)
    return n


def test_combined_scene_is_file_includes_not_meshes(tmp_path, monkeypatch):
    calls = {"wall": 0, "floor": 0, "ceil": 0, "arch": 0}
    orig = {
        "wall": sb.build_wall_strips,
        "floor": sb.build_floor,
        "ceil": sb.build_ceiling,
        "arch": sb.build_arches,
    }

    def wrap(key, fn):
        def inner(*args, **kwargs):
            calls[key] += 1
            return fn(*args, **kwargs)

        return inner

    monkeypatch.setattr(sb, "build_wall_strips", wrap("wall", orig["wall"]))
    monkeypatch.setattr(sb, "build_floor", wrap("floor", orig["floor"]))
    monkeypatch.setattr(sb, "build_ceiling", wrap("ceil", orig["ceil"]))
    monkeypatch.setattr(sb, "build_arches", wrap("arch", orig["arch"]))

    scene_path = build_scene(_level_with_textured_wall(), tmp_path, tmp_path, write_combined=True)
    assert scene_path == tmp_path / "scene.egg"
    assert calls == {"wall": 1, "floor": 1, "ceil": 1, "arch": 1}

    text = scene_path.read_text(encoding="utf-8")
    assert "<Polygon>" not in text
    assert "<VertexPool>" not in text
    for stem in COMPONENT_EGG_STEMS:
        assert f"{stem}.egg" in text
        assert (tmp_path / f"{stem}.egg").is_file()
    assert "<File>" in text


def test_combined_scene_load_externals_pulls_component_meshes(tmp_path):
    build_scene(_level_with_textured_wall(), tmp_path, tmp_path, write_combined=True)
    walls = EggData()
    assert walls.read(Filename.from_os_specific(str(tmp_path / "walls.egg")))
    wall_polys = _count_polygons(walls)
    assert wall_polys > 0

    scene = EggData()
    scene_fn = Filename.from_os_specific(str(tmp_path / "scene.egg"))
    assert scene.read(scene_fn)
    path = DSearchPath()
    path.append_directory(Filename.from_os_specific(str(tmp_path)))
    assert scene.load_externals(path)
    assert _count_polygons(scene) >= wall_polys


def test_write_combined_false_skips_scene_egg(tmp_path):
    out = build_scene(
        _level_with_textured_wall(), tmp_path, tmp_path, write_combined=False
    )
    assert out == tmp_path / "walls.egg"
    assert not (tmp_path / "scene.egg").exists()
    assert (tmp_path / "walls.egg").is_file()
