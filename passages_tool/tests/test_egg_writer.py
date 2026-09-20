"""EggContext texture parenting — 5.5: <Texture> nodes on the written EggData."""
from __future__ import annotations

from panda3d.egg import EggData, EggGroup

from passages_tool.converter.egg_writer import EggContext, parent_textures
from passages_tool.converter.scene_builder import _write_egg
from passages_tool.converter.wall_builder import build_wall_strips
from passages_tool.editor.level import Level, Polyline, TextureInterval


def test_parent_textures_adds_unparented_egg_texture():
    ctx = EggContext("t")
    group = EggGroup("g")
    tex = ctx.get_or_create_texture("stone.png")
    v0 = ctx.add_vertex(0, 0, 0, 0.0, 0.0)
    v1 = ctx.add_vertex(1, 0, 0, 1.0, 0.0)
    v2 = ctx.add_vertex(1, 0, 1, 1.0, 1.0)
    poly = ctx.add_polygon([v0, v1, v2], tex)
    group.add_child(poly)

    assert tex.get_parent() is None

    egg = EggData()
    parent_textures(egg, [group])
    assert tex.get_parent() is not None


def test_write_egg_emits_texture_block(tmp_path):
    level = Level()
    pl = Polyline.make_wall()
    pl.vertices = [(0.0, 0.0), (2.0, 0.0)]
    pl.texture_intervals = [
        TextureInterval(from_vertex=0, to_vertex=1, texture="wall.png")
    ]
    level.add_polyline(pl)
    groups = build_wall_strips(level, texture_dir=tmp_path)
    out = tmp_path / "walls.egg"
    _write_egg(out, groups)
    text = out.read_text(encoding="utf-8")
    assert "<Texture>" in text
    assert "wall.png" in text
    assert "<TRef>" in text


def test_write_egg_no_texture_when_untextured(tmp_path):
    level = Level()
    pl = Polyline.make_wall()
    pl.vertices = [(0.0, 0.0), (2.0, 0.0)]
    level.add_polyline(pl)
    groups = build_wall_strips(level, texture_dir=tmp_path)
    out = tmp_path / "walls.egg"
    _write_egg(out, groups)
    text = out.read_text(encoding="utf-8")
    assert "<Texture>" not in text
