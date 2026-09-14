import math
from pathlib import Path

import pytest

from passages_tool.editor.level import Level, Polyline, PolylineType
from passages_tool.renderer.occluder import build_occluders, OccluderSet, Quad

SAMPLE_TEX = Path(__file__).resolve().parents[1] / "assets" / "sample_textures"


# ── walls ─────────────────────────────────────────────────────────────────────

def test_wall_blocks_and_clears():
    level = Level()
    level.meta.wall_height = 4.0
    wall = Polyline.make_wall()
    wall.vertices = [(-2.0, 3.0), (2.0, 3.0)]     # wall across Y=3
    level.add_polyline(wall)
    occ = build_occluders(level)

    eye = (0.0, 0.0, 1.7)
    behind = (0.0, 6.0, 1.7)                       # anchor beyond the wall
    d = occ.nearest_occluder_dist(eye, behind)
    assert d < math.dist(eye, behind)              # blocked before the target

    # A target in front of the wall is unobstructed.
    infront = (0.0, 2.0, 1.7)
    assert occ.nearest_occluder_dist(eye, infront) == math.inf


def test_wall_height_limit():
    # A ray that clears the top of a short wall is not blocked.
    level = Level()
    level.meta.wall_height = 1.0                    # low wall
    wall = Polyline.make_wall()
    wall.vertices = [(-2.0, 3.0), (2.0, 3.0)]
    level.add_polyline(wall)
    occ = build_occluders(level)
    eye = (0.0, 0.0, 3.0)                           # high eye
    target = (0.0, 6.0, 3.0)                        # high target — sightline is above the wall
    assert occ.nearest_occluder_dist(eye, target) == math.inf


# ── arch cutout (real door texture) ───────────────────────────────────────────

@pytest.mark.skipif(not (SAMPLE_TEX / "big_door_b.png").is_file(),
                    reason="sample door texture not present")
def test_cutout_arch_height_dependent():
    # big_door_b.png: opening is lower-centre (transparent), frame/top opaque.
    # A low sightline through the doorway is clear; a high one hits the arch.
    level = Level()
    level.meta.wall_height = 4.0
    level.meta.pixels_per_meter = 256.0
    arch = Polyline.make_arch((0.0, 3.0))
    arch.orientation = "90.0"                        # span across X at Y=3
    arch.width = 4.0
    arch.transparency = "alpha_test"
    arch.texture = "big_door_b.png"
    arch.height_override = 4.0
    arch.v_at_floor = True
    level.add_polyline(arch)
    occ = build_occluders(level, texture_dir=SAMPLE_TEX)
    assert any(q.tex is not None for q in occ.quads)   # cutout sampler attached

    eye_low = (0.0, 0.0, 0.4)
    tgt_low = (0.0, 6.0, 0.4)                       # through the doorway opening
    assert occ.nearest_occluder_dist(eye_low, tgt_low) == math.inf

    eye_high = (0.0, 0.0, 3.2)
    tgt_high = (0.0, 6.0, 3.2)                      # through the solid arch top
    assert occ.nearest_occluder_dist(eye_high, tgt_high) < math.dist(eye_high, tgt_high)


# ── exclusions ────────────────────────────────────────────────────────────────

def test_billboard_and_blend_arches_excluded():
    level = Level()
    level.meta.wall_height = 4.0
    bb = Polyline.make_arch((0.0, 3.0)); bb.orientation = "billboard"; bb.transparency = "alpha_test"
    bl = Polyline.make_arch((0.0, 3.0)); bl.orientation = "90.0"; bl.transparency = "alpha_blend"
    level.add_polyline(bb)
    level.add_polyline(bl)
    occ = build_occluders(level)
    assert occ.quads == []                           # neither contributes an occluder


def test_solid_arch_blocks_like_wall():
    level = Level()
    level.meta.wall_height = 4.0
    arch = Polyline.make_arch((0.0, 3.0))
    arch.orientation = "90.0"; arch.width = 4.0; arch.transparency = "none"; arch.height_override = 4.0
    level.add_polyline(arch)
    occ = build_occluders(level)
    eye = (0.0, 0.0, 1.7); behind = (0.0, 6.0, 1.7)
    assert occ.nearest_occluder_dist(eye, behind) < math.dist(eye, behind)
