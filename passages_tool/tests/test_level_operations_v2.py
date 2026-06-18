"""
tests/test_level_operations_v2.py
───────────────────────────────────
Phase 3 focused operation tests:

  - set_interval_texture  / set_interval_x_offset (new mutators)
  - full interval workflow: add → assign → split → remove
  - add_eyepath_edge / remove_eyepath_edge full workflow
  - type-guards (ops only work on correct polyline type)
"""
from __future__ import annotations

import pytest

from passages_tool.editor.level import (
    Level,
    Polyline,
    PolylineType,
    TextureInterval,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _wall_with_verts(n: int) -> tuple[Level, Polyline]:
    """Return a Level + a Wall polyline with *n* vertices (at x=i, z=0)."""
    level = Level()
    pl    = Polyline.make_wall()
    for i in range(n):
        pl.vertices.append((float(i), 0.0))
    level.add_polyline(pl)
    return level, level.polylines[pl.id]


def _eyepath_with_verts(n: int) -> tuple[Level, Polyline]:
    """Return a Level + an EyePath polyline with *n* vertices."""
    level = Level()
    pl    = Polyline.make_eyepath()
    for i in range(n):
        pl.vertices.append((float(i), 0.0))
    level.add_polyline(pl)
    return level, level.polylines[pl.id]


# ══════════════════════════════════════════════════════════════════════════════
#  set_interval_texture
# ══════════════════════════════════════════════════════════════════════════════

class TestSetIntervalTexture:
    def test_assigns_texture(self):
        level, pl = _wall_with_verts(5)
        level.add_texture_interval(pl.id, TextureInterval(0, 4))
        level.set_interval_texture(pl.id, 0, "stone.png")
        assert pl.texture_intervals[0].texture == "stone.png"

    def test_clears_texture_with_none(self):
        level, pl = _wall_with_verts(5)
        level.add_texture_interval(pl.id, TextureInterval(0, 4, texture="brick.png"))
        level.set_interval_texture(pl.id, 0, None)
        assert pl.texture_intervals[0].texture is None

    def test_out_of_range_index_is_noop(self):
        level, pl = _wall_with_verts(5)
        level.add_texture_interval(pl.id, TextureInterval(0, 4))
        level.set_interval_texture(pl.id, 99, "stone.png")
        assert pl.texture_intervals[0].texture is None   # unchanged

    def test_marks_dirty(self):
        level, pl = _wall_with_verts(5)
        level.add_texture_interval(pl.id, TextureInterval(0, 4))
        level.dirty = False
        level.set_interval_texture(pl.id, 0, "stone.png")
        assert level.dirty

    def test_noop_on_nonexistent_pid(self):
        level, _ = _wall_with_verts(3)
        # Should not raise
        level.set_interval_texture("ghost-pid", 0, "stone.png")


# ══════════════════════════════════════════════════════════════════════════════
#  set_interval_x_offset
# ══════════════════════════════════════════════════════════════════════════════

class TestSetIntervalXOffset:
    def test_updates_offset(self):
        level, pl = _wall_with_verts(5)
        level.add_texture_interval(pl.id, TextureInterval(0, 4))
        level.set_interval_x_offset(pl.id, 0, 128.5)
        assert pl.texture_intervals[0].x_offset == pytest.approx(128.5)

    def test_out_of_range_is_noop(self):
        level, pl = _wall_with_verts(5)
        level.add_texture_interval(pl.id, TextureInterval(0, 4))
        level.set_interval_x_offset(pl.id, 5, 100.0)
        assert pl.texture_intervals[0].x_offset == pytest.approx(0.0)

    def test_marks_dirty(self):
        level, pl = _wall_with_verts(5)
        level.add_texture_interval(pl.id, TextureInterval(0, 4))
        level.dirty = False
        level.set_interval_x_offset(pl.id, 0, 50.0)
        assert level.dirty


# ══════════════════════════════════════════════════════════════════════════════
#  Full interval workflow: add → assign texture → split → remove
# ══════════════════════════════════════════════════════════════════════════════

class TestIntervalWorkflow:
    def test_add_full_span(self):
        level, pl = _wall_with_verts(6)  # 5 edges (0-5)
        level.add_texture_interval(pl.id, TextureInterval(0, 5))
        assert len(pl.texture_intervals) == 1
        iv = pl.texture_intervals[0]
        assert iv.from_vertex == 0 and iv.to_vertex == 5

    def test_add_two_non_overlapping(self):
        level, pl = _wall_with_verts(8)
        level.add_texture_interval(pl.id, TextureInterval(0, 4))
        level.add_texture_interval(pl.id, TextureInterval(4, 7))
        assert len(pl.texture_intervals) == 2

    def test_sorted_after_add(self):
        level, pl = _wall_with_verts(8)
        level.add_texture_interval(pl.id, TextureInterval(4, 7))
        level.add_texture_interval(pl.id, TextureInterval(0, 4))
        assert pl.texture_intervals[0].from_vertex == 0
        assert pl.texture_intervals[1].from_vertex == 4

    def test_assign_then_split(self):
        level, pl = _wall_with_verts(8)
        level.add_texture_interval(pl.id, TextureInterval(0, 7, texture="stone.png"))
        level.split_texture_interval(pl.id, at_vertex=3)
        assert len(pl.texture_intervals) == 2
        first, second = pl.texture_intervals
        assert first.from_vertex == 0 and first.to_vertex == 3
        assert second.from_vertex == 3 and second.to_vertex == 7
        assert first.texture == "stone.png"
        assert second.texture == "stone.png"  # texture propagated
        assert second.x_offset == pytest.approx(0.0)  # offset resets

    def test_split_second_interval_independent(self):
        level, pl = _wall_with_verts(8)
        level.add_texture_interval(pl.id, TextureInterval(0, 7, texture="stone.png"))
        level.split_texture_interval(pl.id, at_vertex=3)
        # Assign different texture to second half
        level.set_interval_texture(pl.id, 1, "brick.png")
        assert pl.texture_intervals[0].texture == "stone.png"
        assert pl.texture_intervals[1].texture == "brick.png"

    def test_remove_first_interval(self):
        level, pl = _wall_with_verts(8)
        level.add_texture_interval(pl.id, TextureInterval(0, 4))
        level.add_texture_interval(pl.id, TextureInterval(4, 7))
        level.remove_texture_interval(pl.id, 0)
        assert len(pl.texture_intervals) == 1
        assert pl.texture_intervals[0].from_vertex == 4

    def test_remove_out_of_range_is_noop(self):
        level, pl = _wall_with_verts(5)
        level.add_texture_interval(pl.id, TextureInterval(0, 4))
        level.remove_texture_interval(pl.id, 99)
        assert len(pl.texture_intervals) == 1

    def test_interval_only_on_wall_type(self):
        level = Level()
        arch = Polyline.make_arch()
        level.add_polyline(arch)
        level.add_texture_interval(arch.id, TextureInterval(0, 1))
        # Arch type → interval should NOT be added
        assert len(arch.texture_intervals) == 0

    def test_round_trip_preserves_intervals(self):
        level, pl = _wall_with_verts(6)
        level.add_texture_interval(pl.id, TextureInterval(0, 3, texture="stone.png"))
        level.add_texture_interval(pl.id, TextureInterval(3, 5, texture="brick.png"))
        restored = Level.from_dict(level.to_dict())
        r_pl = list(restored.polylines.values())[0]
        assert len(r_pl.texture_intervals) == 2
        assert r_pl.texture_intervals[0].texture == "stone.png"
        assert r_pl.texture_intervals[1].texture == "brick.png"


# ══════════════════════════════════════════════════════════════════════════════
#  EyePath edge operations
# ══════════════════════════════════════════════════════════════════════════════

class TestEyePathEdgeWorkflow:
    def test_add_edge(self):
        level, pl = _eyepath_with_verts(4)
        level.add_eyepath_edge(pl.id, 0, 1)
        assert (0, 1) in pl.edges

    def test_add_edge_both_directions_independent(self):
        level, pl = _eyepath_with_verts(4)
        level.add_eyepath_edge(pl.id, 0, 1)
        level.add_eyepath_edge(pl.id, 1, 0)
        assert (0, 1) in pl.edges
        assert (1, 0) in pl.edges
        assert len(pl.edges) == 2

    def test_duplicate_edge_ignored(self):
        level, pl = _eyepath_with_verts(4)
        level.add_eyepath_edge(pl.id, 0, 1)
        level.add_eyepath_edge(pl.id, 0, 1)
        assert pl.edges.count((0, 1)) == 1

    def test_remove_edge(self):
        level, pl = _eyepath_with_verts(4)
        level.add_eyepath_edge(pl.id, 0, 1)
        level.add_eyepath_edge(pl.id, 1, 2)
        level.remove_eyepath_edge(pl.id, 0, 1)
        assert (0, 1) not in pl.edges
        assert (1, 2) in pl.edges

    def test_remove_nonexistent_edge_is_noop(self):
        level, pl = _eyepath_with_verts(4)
        level.add_eyepath_edge(pl.id, 0, 1)
        level.remove_eyepath_edge(pl.id, 2, 3)  # not present
        assert len(pl.edges) == 1

    def test_edge_only_on_eyepath_type(self):
        level = Level()
        wall = Polyline.make_wall()
        wall.vertices = [(0.0, 0.0), (1.0, 0.0)]
        level.add_polyline(wall)
        level.add_eyepath_edge(wall.id, 0, 1)
        # Wall type → edge should NOT be added
        assert len(wall.edges) == 0

    def test_add_edge_out_of_bounds_is_noop(self):
        level, pl = _eyepath_with_verts(4)
        level.add_eyepath_edge(pl.id, 0, 4)   # index 4 is out of bounds
        level.add_eyepath_edge(pl.id, -1, 1)  # negative index
        assert len(pl.edges) == 0

    def test_marks_dirty_on_add(self):
        level, pl = _eyepath_with_verts(4)
        level.dirty = False
        level.add_eyepath_edge(pl.id, 0, 1)
        assert level.dirty

    def test_marks_dirty_on_remove(self):
        level, pl = _eyepath_with_verts(4)
        level.add_eyepath_edge(pl.id, 0, 1)
        level.dirty = False
        level.remove_eyepath_edge(pl.id, 0, 1)
        assert level.dirty

    def test_round_trip_preserves_edges(self):
        level, pl = _eyepath_with_verts(4)
        level.add_eyepath_edge(pl.id, 0, 1)
        level.add_eyepath_edge(pl.id, 1, 2)
        level.add_eyepath_edge(pl.id, 2, 3)
        restored = Level.from_dict(level.to_dict())
        r_pl = list(restored.polylines.values())[0]
        assert (0, 1) in r_pl.edges
        assert (1, 2) in r_pl.edges
        assert (2, 3) in r_pl.edges
        assert len(r_pl.edges) == 3


# ══════════════════════════════════════════════════════════════════════════════
#  delete_vertex adjustments
# ══════════════════════════════════════════════════════════════════════════════

class TestDeleteVertexAdjustments:
    def test_delete_vertex_adjusts_texture_intervals(self):
        level, pl = _wall_with_verts(5)
        iv1 = TextureInterval(from_vertex=1, to_vertex=3, texture="stone.png")
        iv2 = TextureInterval(from_vertex=3, to_vertex=4, texture="brick.png")
        level.add_texture_interval(pl.id, iv1)
        level.add_texture_interval(pl.id, iv2)

        # Delete vertex index 2 (inside iv1)
        level.delete_vertex(pl.id, 2)

        # iv1 should shrink to covering 1 to 2
        # iv2 should shift to covering 2 to 3
        assert len(pl.texture_intervals) == 2
        assert pl.texture_intervals[0].from_vertex == 1
        assert pl.texture_intervals[0].to_vertex == 2
        assert pl.texture_intervals[1].from_vertex == 2
        assert pl.texture_intervals[1].to_vertex == 3

    def test_delete_vertex_removes_collapsed_intervals(self):
        level, pl = _wall_with_verts(4)
        iv1 = TextureInterval(from_vertex=1, to_vertex=2, texture="stone.png")
        level.add_texture_interval(pl.id, iv1)

        # Delete vertex 1 (boundaries become 1 to 1, collapsing the interval)
        level.delete_vertex(pl.id, 1)
        assert len(pl.texture_intervals) == 0

    def test_delete_vertex_adjusts_eyepath_edges(self):
        level, pl = _eyepath_with_verts(4)
        level.add_eyepath_edge(pl.id, 0, 1)
        level.add_eyepath_edge(pl.id, 1, 2)
        level.add_eyepath_edge(pl.id, 2, 3)

        # Delete vertex index 1 (connected to edge (0,1) and (1,2))
        level.delete_vertex(pl.id, 1)

        # Edges (0,1) and (1,2) should be removed.
        # Edge (2,3) should shift down to (1,2).
        assert len(pl.edges) == 1
        assert (1, 2) in pl.edges
