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
    assert manifest["version"] == 2
    edges = manifest["edges"]
    assert len(edges) == 4                       # 2 undirected edges → 4 directed

    # Check v0000_to_v0001
    assert "v0000_to_v0001" in edges
    m1 = edges["v0000_to_v0001"]
    assert m1["image_path"] == "render_v0000_to_v0001.png"
    assert m1["eyepoint_xyz"] == [0.0, 0.0, 1.6]
    assert m1["facing_xyz"] == [3.0, 4.0, 1.6]
    assert m1["rendered"] is False
    assert "visible_anchors" not in m1           # visibility moved to eyepoints

    # Check v0001_to_v0002
    assert "v0001_to_v0002" in edges
    m2 = edges["v0001_to_v0002"]
    assert m2["eyepoint_xyz"] == [3.0, 4.0, 1.6]
    assert m2["facing_xyz"] == [3.0, 10.0, 1.6]

    # One eyepoint entry per EyePath vertex
    assert set(manifest["eyepoints"].keys()) == {"v0000", "v0001", "v0002"}
    assert manifest["eyepoints"]["v0000"]["xyz"] == [0.0, 0.0, 1.6]
    assert "yaw_strip" not in manifest["eyepoints"]["v0000"]


def test_build_manifest_yaw_strip_key_only_when_file_exists(tmp_path):
    level = Level()
    ep = Polyline.make_eyepath()
    ep.vertices = [(0.0, 0.0), (1.0, 0.0)]
    ep.edges = [(0, 1)]
    level.add_polyline(ep)
    (tmp_path / "yaw_v0000.png").write_bytes(b"")
    manifest = build_manifest(level, output_dir=tmp_path)
    assert manifest["eyepoints"]["v0000"]["yaw_strip"] == "yaw_v0000.png"
    assert "yaw_strip" not in manifest["eyepoints"]["v0001"]


def test_stale_yaw_only_when_manifest_opted_in(tmp_path):
    manifest = {
        "version": 2,
        "edges": {"v0000_to_v0001": {"image_path": "render_v0000_to_v0001.png"}},
        "eyepoints": {},
    }
    (tmp_path / "yaw_v0000.png").write_bytes(b"")
    assert find_stale_images(manifest, tmp_path) == []

    manifest["eyepoints"] = {"v0000": {"xyz": [0, 0, 1.7], "yaw_strip": "yaw_v0000.png"}}
    (tmp_path / "yaw_v0009.png").write_bytes(b"")
    stale_names = {p.name for p in find_stale_images(manifest, tmp_path)}
    assert "yaw_v0009.png" in stale_names
    assert "yaw_v0000.png" not in stale_names


def test_build_manifest_two_eyepaths_uses_global_offsets():
    """Second path continues the vertex index space so keys do not collide."""
    level = Level()
    a = Polyline.make_eyepath()
    a.vertices = [(0.0, 0.0), (1.0, 0.0)]
    a.edges = [(0, 1)]
    b = Polyline.make_eyepath()
    b.vertices = [(10.0, 0.0), (11.0, 0.0)]
    b.edges = [(0, 1)]
    level.add_polyline(a)
    level.add_polyline(b)

    edges = build_manifest(level)["edges"]
    assert "v0000_to_v0001" in edges
    assert "v0001_to_v0000" in edges
    assert "v0002_to_v0003" in edges
    assert "v0003_to_v0002" in edges
    assert edges["v0002_to_v0003"]["eyepoint_xyz"][:2] == [10.0, 0.0]
    assert set(build_manifest(level)["eyepoints"].keys()) == {
        "v0000", "v0001", "v0002", "v0003",
    }


def test_find_stale_and_missing_images(tmp_path):
    # Dummy manifest (version 2 nested) with 2 edges
    manifest = {
        "version": 2,
        "edges": {
            "v0000_to_v0001": {"image_path": "render_v0000_to_v0001.png"},
            "v0001_to_v0002": {"image_path": "render_v0001_to_v0002.png"},
        },
        "eyepoints": {},
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
