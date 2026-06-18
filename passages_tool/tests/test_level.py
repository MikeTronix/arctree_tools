"""
tests/test_level.py — Unit tests for the Level data model.
No Panda3D or GUI imports required.
"""
import pytest
from passages_tool.editor.level import Level, Polyline


def make_level() -> Level:
    level = Level()
    pl = Polyline.make_new()
    level.add_polyline(pl)
    return level, pl.id


class TestTiles:
    def test_set_and_get(self):
        level = Level()
        level.set_tile(3, 4, "stone.png")
        t = level.get_tile(3, 4)
        assert t is not None
        assert t.texture == "stone.png"
        assert level.dirty

    def test_clear_tile_with_none(self):
        level = Level()
        level.set_tile(1, 1, "floor.png")
        level.set_tile(1, 1, None)
        assert level.get_tile(1, 1) is None

    def test_missing_tile_returns_none(self):
        level = Level()
        assert level.get_tile(99, 99) is None


class TestPolylines:
    def test_add_and_get(self):
        level, pid = make_level()
        pl = level.get_polyline(pid)
        assert pl is not None
        assert pl.id == pid

    def test_add_vertex(self):
        level, pid = make_level()
        level.add_vertex(pid, 1.0, 2.0)
        pl = level.get_polyline(pid)
        assert pl.vertices == [(1.0, 2.0)]

    def test_move_vertex(self):
        level, pid = make_level()
        level.add_vertex(pid, 0.0, 0.0)
        level.move_vertex(pid, 0, 5.0, 7.0)
        assert level.get_polyline(pid).vertices[0] == (5.0, 7.0)

    def test_delete_vertex(self):
        level, pid = make_level()
        level.add_vertex(pid, 0.0, 0.0)
        level.add_vertex(pid, 1.0, 1.0)
        level.delete_vertex(pid, 0)
        assert len(level.get_polyline(pid).vertices) == 1
        assert level.get_polyline(pid).vertices[0] == (1.0, 1.0)

    def test_delete_vertex_out_of_range_is_noop(self):
        level, pid = make_level()
        level.add_vertex(pid, 0.0, 0.0)
        level.delete_vertex(pid, 99)   # should not raise
        assert len(level.get_polyline(pid).vertices) == 1

    def test_remove_polyline(self):
        level, pid = make_level()
        level.remove_polyline(pid)
        assert level.get_polyline(pid) is None

    def test_set_texture(self):
        level, pid = make_level()
        level.set_polyline_texture(pid, "wall.png")
        ivs = level.get_polyline(pid).texture_intervals
        assert len(ivs) == 1 and ivs[0].texture == "wall.png"

    def test_set_closed(self):
        level, pid = make_level()
        level.set_polyline_closed(pid, True)
        assert level.get_polyline(pid).closed is True


class TestSerialization:
    def _round_trip(self, level: Level) -> Level:
        data = level.to_dict()
        return Level.from_dict(data)

    def test_empty_level(self):
        level = Level()
        restored = self._round_trip(level)
        assert restored.tiles == {}
        assert restored.polylines == {}

    def test_tiles_survive_round_trip(self):
        level = Level()
        level.set_tile(2, 3, "brick.png")
        restored = self._round_trip(level)
        t = restored.get_tile(2, 3)
        assert t is not None and t.texture == "brick.png"

    def test_polylines_survive_round_trip(self):
        level, pid = make_level()
        level.add_vertex(pid, 1.0, 2.5)
        level.set_polyline_texture(pid, "stone.png")
        level.set_polyline_closed(pid, True)
        restored = self._round_trip(level)
        pl = restored.get_polyline(pid)
        assert pl is not None
        assert pl.vertices == [(1.0, 2.5)]
        assert pl.texture_intervals[0].texture == "stone.png"
        assert pl.closed is True

    def test_dirty_false_after_from_dict(self):
        level, _ = make_level()
        assert level.dirty
        restored = Level.from_dict(level.to_dict())
        assert not restored.dirty

    def test_version_in_dict(self):
        data = Level().to_dict()
        assert data["version"] == 2


class TestBoundingBox:
    def test_empty_returns_default(self):
        level = Level()
        bb = level.bounding_box()
        assert bb == (0.0, 10.0, 0.0, 10.0)

    def test_single_vertex(self):
        level, pid = make_level()
        level.add_vertex(pid, 3.0, 7.0)
        left, right, bottom, top = level.bounding_box()
        assert left <= 3.0 <= right
        assert bottom <= 7.0 <= top
