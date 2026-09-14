import math
from passages_tool.editor.level import Level, Polyline, PolylineType
from passages_tool.renderer.manifest import build_manifest


def test_anchor_serialization():
    # Create anchor
    pl = Polyline.make_anchor((2.5, -1.0))
    assert pl.type == PolylineType.ANCHOR
    assert pl.position == (2.5, -1.0)
    assert pl.radius == 0.5
    assert pl.height == 2.0
    assert pl.max_distance == 10.0
    assert pl.z_offset == 0.0
    assert pl.fov_limit is None
    assert pl.sprite_count == 1
    assert pl.tags == []

    # Modify fields
    pl.radius = 1.2
    pl.height = 3.5
    pl.max_distance = 15.0
    pl.z_offset = 0.5
    pl.fov_limit = 35.0
    pl.sprite_count = 3
    pl.tags = ["altar", "gate"]

    # Serialize
    d = pl.to_dict()
    assert d["type"] == "anchor"
    assert d["position"] == [2.5, -1.0]
    assert d["radius"] == 1.2
    assert d["height"] == 3.5
    assert d["max_distance"] == 15.0
    assert d["z_offset"] == 0.5
    assert d["fov_limit"] == 35.0
    assert d["sprite_count"] == 3
    assert d["tags"] == ["altar", "gate"]

    # Deserialize
    pl2 = Polyline.from_dict(d)
    assert pl2.type == PolylineType.ANCHOR
    assert pl2.position == (2.5, -1.0)
    assert pl2.radius == 1.2
    assert pl2.height == 3.5
    assert pl2.max_distance == 15.0
    assert pl2.z_offset == 0.5
    assert pl2.fov_limit == 35.0
    assert pl2.sprite_count == 3
    assert pl2.tags == ["altar", "gate"]

    # Legacy files without "height" fall back to the nominal default
    d_legacy = dict(d)
    del d_legacy["height"]
    pl3 = Polyline.from_dict(d_legacy)
    assert pl3.height == 2.0


def test_eyepoint_visibility_and_occlusion():
    level = Level()
    level.meta.eye_height = 1.7
    level.meta.wall_height = 4.0

    # EyePath vertex at (0, 0)
    eyepath = Polyline.make_eyepath()
    eyepath.vertices = [(0.0, 0.0), (0.0, 5.0)]
    eyepath.edges = [(0, 1)]
    level.add_polyline(eyepath)

    # Anchor in front at (0, 3.0)
    anchor = Polyline.make_anchor((0.0, 3.0))
    level.add_polyline(anchor)

    def vis(m, vid="v0000"):
        return m["eyepoints"][vid]["visible_anchors"]

    # 1. Baseline: unobstructed → visible with full coverage; visibility is now
    #    view-independent (no baked FOV cone), keyed by eyepoint not edge.
    m = build_manifest(level)
    assert anchor.id in vis(m)
    rec = vis(m)[anchor.id]
    assert rec["distance"] == 3.0
    assert rec["occ_coverage"] == 1.0
    assert "screen_x" not in rec                 # projection deferred to runtime

    # 2. max_distance gating: distance 3.0 > limit 2.0 → dropped
    anchor.max_distance = 2.0
    assert anchor.id not in vis(build_manifest(level))
    anchor.max_distance = 10.0

    # 3. An anchor 90° off the eyepoint is STILL a candidate — the FOV cull is a
    #    runtime concern now, not baked (that's the whole point of the rework).
    anchor.vertices = [(5.0, 0.0)]
    assert anchor.id in vis(build_manifest(level))
    anchor.vertices = [(0.0, 3.0)]

    # 4. Occlusion by a full-height wall between eyepoint and anchor → dropped
    wall = Polyline.make_wall()
    wall.vertices = [(-2.0, 1.5), (2.0, 1.5)]
    level.add_polyline(wall)
    assert anchor.id not in vis(build_manifest(level))
