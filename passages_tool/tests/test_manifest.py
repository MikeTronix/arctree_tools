"""
tests/test_manifest.py
──────────────────────
Tests for the render manifest system.
"""
from __future__ import annotations

from passages_tool.editor.level import Level, Polyline
from passages_tool.renderer.manifest import (
    build_manifest,
    find_missing_images,
    find_stale_images,
)


def test_build_manifest():
    level = Level()
    level.meta.eye_height = 1.6

    ep = Polyline.make_eyepath()
    ep.vertices = [(0.0, 0.0), (3.0, 4.0), (3.0, 10.0)]
    ep.edges = [(0, 1), (1, 2)]
    level.add_polyline(ep)

    manifest = build_manifest(level)
    assert len(manifest) == 2

    # Check v0000_to_v0001
    assert "v0000_to_v0001" in manifest
    m1 = manifest["v0000_to_v0001"]
    assert m1["image_path"] == "render_v0000_to_v0001.png"
    assert m1["eyepoint_xyz"] == [0.0, 0.0, 1.6]
    assert m1["facing_xyz"] == [3.0, 4.0, 1.6]
    assert m1["rendered"] is False

    # Check v0001_to_v0002
    assert "v0001_to_v0002" in manifest
    m2 = manifest["v0001_to_v0002"]
    assert m2["eyepoint_xyz"] == [3.0, 4.0, 1.6]
    assert m2["facing_xyz"] == [3.0, 10.0, 1.6]


def test_find_stale_and_missing_images(tmp_path):
    # Dummy manifest with 2 edges
    manifest = {
        "v0000_to_v0001": {"image_path": "render_v0000_to_v0001.png"},
        "v0001_to_v0002": {"image_path": "render_v0001_to_v0002.png"},
    }

    # Create dummy directory
    output_dir = tmp_path / "renders"
    output_dir.mkdir()

    # 1. Initially, both are missing and no stale files exist
    missing = find_missing_images(manifest, output_dir)
    stale = find_stale_images(manifest, output_dir)
    assert sorted(missing) == ["v0000_to_v0001", "v0001_to_v0002"]
    assert len(stale) == 0

    # 2. Add one valid image and one invalid (stale) image
    (output_dir / "render_v0000_to_v0001.png").touch()
    (output_dir / "render_v9999_to_v9999.png").touch()
    (output_dir / "other_file.txt").touch()  # ignored

    missing = find_missing_images(manifest, output_dir)
    stale = find_stale_images(manifest, output_dir)

    assert missing == ["v0001_to_v0002"]
    assert len(stale) == 1
    assert stale[0].name == "render_v9999_to_v9999.png"
