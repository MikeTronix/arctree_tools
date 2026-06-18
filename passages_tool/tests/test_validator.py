"""
tests/test_validator.py
───────────────────────
Tests for the level validator (arch visibility and edge-on checks).
"""
from __future__ import annotations

import pytest

from passages_tool.editor.level import Level, Polyline
from passages_tool.editor.validator import validate_arch_visibility


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

    warnings = validate_arch_visibility(level, threshold_deg=60.0)
    assert len(warnings) == 1
    w = warnings[0]
    assert w.arch_id == arch.id
    assert w.v_from == 0
    assert w.v_to == 1
    assert w.angle_deg == pytest.approx(90.0)
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

    warnings = validate_arch_visibility(level, threshold_deg=60.0)
    assert len(warnings) == 0


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

