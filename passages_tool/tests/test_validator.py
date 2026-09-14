"""
tests/test_validator.py
───────────────────────
Tests for the level validator (arch visibility and edge-on checks).
"""
from __future__ import annotations

import pytest

from passages_tool.editor.level import Level, Polyline, TextureInterval
from passages_tool.editor.validator import (
    validate_arch_visibility,
    validate_structure,
    validate_textures,
)


def test_validator_billboard_arches():
    level = Level()
    
    # Setup eyepath: v0 at (0, 0), v1 at (10, 0)
    ep = Polyline.make_eyepath()
    ep.vertices = [(0.0, 0.0), (10.0, 0.0)]
    ep.edges = [(0, 1)]
    level.add_polyline(ep)

    # Billboard arch placed at (5, 0)
    # Even though it's directly on the path, billboards are immune to edge-on warnings.
    arch = Polyline.make_arch()
    arch.vertices = [(5.0, 0.0)]
    arch.orientation = "billboard"
    level.add_polyline(arch)

    warnings = validate_arch_visibility(level)
    assert len(warnings) == 0


def test_validator_face_on_fixed_arch():
    level = Level()
    
    # Setup eyepath: v0 at (0, 0), v1 at (10, 0)
    ep = Polyline.make_eyepath()
    ep.vertices = [(0.0, 0.0), (10.0, 0.0)]
    ep.edges = [(0, 1)]
    level.add_polyline(ep)

    # Fixed arch at (5, 0) oriented at 0 degrees.
    # Normal is (cos(0), sin(0)) = (1, 0).
    # Gaze direction is (+1, 0) -> parallel/face-on -> divergence is 0 deg.
    # Should not produce any warning.
    arch = Polyline.make_arch()
    arch.vertices = [(5.0, 0.0)]
    arch.orientation = 0.0
    level.add_polyline(arch)

    warnings = validate_arch_visibility(level)
    assert len(warnings) == 0


def test_validator_edge_on_fixed_arch():
    level = Level()
    
    # Setup eyepath: v0 at (0, 0), v1 at (10, 0)
    ep = Polyline.make_eyepath()
    ep.vertices = [(0.0, 0.0), (10.0, 0.0)]
    ep.edges = [(0, 1)]
    level.add_polyline(ep)

    # Fixed arch at (5, 0) oriented at 90 degrees.
    # Normal is (0, 1). Gaze is (+1, 0).
    # Perpendicular -> angle is 90 degrees -> edge-on!
    # Should generate a warning.
    arch = Polyline.make_arch()
    arch.vertices = [(5.0, 0.0)]
    arch.orientation = 90.0
    level.add_polyline(arch)

    warnings = validate_arch_visibility(level, threshold_deg=30.0)
    # Both directed viewpoints (0→1 and 1→0) are baked; both see the arch edge-on.
    assert len(warnings) == 2
    pairs = {(w.v_from, w.v_to) for w in warnings}
    assert pairs == {(0, 1), (1, 0)}
    for w in warnings:
        assert w.kind == "arch_edge_on"
        assert w.target_id == arch.id
        assert w.arch_id == arch.id
        assert w.angle_deg == pytest.approx(0.0)
        assert "edge-on" in w.message


def test_validator_out_of_range_arch():
    level = Level()
    level.meta.fog_end = 2.0  # short visibility range
    
    # Setup eyepath: v0 at (0, 0), v1 at (10, 0)
    ep = Polyline.make_eyepath()
    ep.vertices = [(0.0, 0.0), (10.0, 0.0)]
    ep.edges = [(0, 1)]
    level.add_polyline(ep)

    # Fixed arch placed at (5.0, 0.0) oriented at 90 degrees (edge-on).
    # Distance to camera (v0 at 0,0) is 5.0, which is > fog_end (2.0).
    # Should not produce warning because it's completely invisible/hidden in fog.
    arch = Polyline.make_arch()
    arch.vertices = [(5.0, 0.0)]
    arch.orientation = 90.0
    level.add_polyline(arch)

    warnings = validate_arch_visibility(level, threshold_deg=30.0)
    assert len(warnings) == 0


def test_validate_structure_multiple_eyepaths():
    level = Level()
    a = Polyline.make_eyepath()
    b = Polyline.make_eyepath()
    a.vertices = [(0.0, 0.0), (1.0, 0.0)]
    b.vertices = [(2.0, 0.0), (3.0, 0.0)]
    level.add_polyline(a)
    level.add_polyline(b)
    warnings = validate_structure(level)
    assert warnings == []


def test_validate_textures_closed_wall_full_interval():
    """A closed wall with one 0..n-1 interval covers the closing edge too."""
    level = Level()
    level.meta.floor_texture = "floor.png"
    level.meta.ceiling_texture = "ceil.png"
    wall = Polyline.make_wall()
    wall.vertices = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    wall.closed = True
    wall.texture_intervals = [
        TextureInterval(from_vertex=0, to_vertex=3, texture="stone.png")
    ]
    level.add_polyline(wall)

    warnings = validate_textures(level)
    assert warnings == []


def test_validate_textures_closed_wall_missing_closing_not_false_positive():
    """Open interval that does not reach the last vertex still flags later edges."""
    level = Level()
    level.meta.floor_texture = "floor.png"
    level.meta.ceiling_texture = "ceil.png"
    wall = Polyline.make_wall()
    wall.vertices = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    wall.closed = True
    wall.texture_intervals = [
        TextureInterval(from_vertex=0, to_vertex=2, texture="stone.png")
    ]
    level.add_polyline(wall)

    warnings = validate_textures(level)
    assert len(warnings) == 1
    assert "untextured" in warnings[0].message


def test_webp_mislabeled_as_png(tmp_path):
    from PIL import Image
    from passages_tool.textures.manager import TextureManager
    
    # Create a valid WebP image but save it with .png extension
    img_path = tmp_path / "mislabeled.png"
    img = Image.new("RGBA", (10, 10), (255, 0, 0, 255))
    img.save(img_path, format="WEBP")
    
    # Use TextureManager to load it
    mgr = TextureManager()
    mgr.scan_directory(tmp_path)
    
    tex = mgr.get_panda_texture("mislabeled.png")
    assert tex is not None
    assert tex.getXSize() == 10
    assert tex.getYSize() == 10

