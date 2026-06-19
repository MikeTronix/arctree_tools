import math
from passages_tool.editor.level import Level, Polyline, PolylineType
from passages_tool.renderer.manifest import build_manifest, segments_intersect


def test_anchor_serialization():
    # Create anchor
    pl = Polyline.make_anchor((2.5, -1.0))
    assert pl.type == PolylineType.ANCHOR
    assert pl.position == (2.5, -1.0)
    assert pl.radius == 0.5
    assert pl.max_distance == 10.0
    assert pl.z_offset == 0.0
    assert pl.fov_limit is None
    assert pl.sprite_count == 1
    assert pl.tags == []

    # Modify fields
    pl.radius = 1.2
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
    assert pl2.max_distance == 15.0
    assert pl2.z_offset == 0.5
    assert pl2.fov_limit == 35.0
    assert pl2.sprite_count == 3
    assert pl2.tags == ["altar", "gate"]


def test_anchor_visibility_and_occlusion():
    level = Level()
    level.meta.eye_height = 1.7
    level.meta.fov_h = 90.0
    level.meta.fov_v = 60.0

    # 1. Create EyePath: camera at (0, 0) looking at (0, 5)
    eyepath = Polyline.make_eyepath()
    eyepath.vertices = [(0.0, 0.0), (0.0, 5.0)]
    eyepath.edges = [(0, 1)]
    level.add_polyline(eyepath)

    # 2. Place Anchor directly in front at (0, 3.0)
    anchor = Polyline.make_anchor((0.0, 3.0))
    level.add_polyline(anchor)

    # 3. Test baseline visibility (unobstructed)
    m = build_manifest(level)
    assert "v0000_to_v0001" in m
    edge_info = m["v0000_to_v0001"]
    assert anchor.id in edge_info["visible_anchors"]
    proj = edge_info["visible_anchors"][anchor.id]
    assert proj["distance"] == 3.0
    assert abs(proj["screen_x"]) < 1e-4  # centered horizontally
    # camera eye_height is 1.7, anchor z_offset is 0.0, so anchor is below camera.
    # screen_y should be negative.
    assert proj["screen_y"] < 0.0

    # 4. Test max_distance gating: set limit to 2.0 (distance is 3.0)
    anchor.max_distance = 2.0
    m = build_manifest(level)
    assert anchor.id not in m["v0000_to_v0001"]["visible_anchors"]

    # Restore visibility
    anchor.max_distance = 10.0

    # 5. Test FOV gating: place anchor at (5.0, 0.0) (90 degrees to view direction)
    anchor.vertices = [(5.0, 0.0)]
    m = build_manifest(level)
    assert anchor.id not in m["v0000_to_v0001"]["visible_anchors"]

    # Restore position
    anchor.vertices = [(0.0, 3.0)]

    # 6. Test occlusion blocking by Wall
    # Place wall segment running horizontally at Y = 1.5, separating camera and anchor
    wall = Polyline.make_wall()
    wall.vertices = [(-2.0, 1.5), (2.0, 1.5)]
    level.add_polyline(wall)

    m = build_manifest(level)
    assert anchor.id not in m["v0000_to_v0001"]["visible_anchors"]


def test_segment_intersection():
    # Crossing lines
    assert segments_intersect((0, 0), (2, 2), (0, 2), (2, 0)) is True
    # Non-crossing lines
    assert segments_intersect((0, 0), (1, 1), (2, 2), (3, 3)) is False
    # Parallel offsets
    assert segments_intersect((0, 0), (0, 2), (1, 0), (1, 2)) is False
