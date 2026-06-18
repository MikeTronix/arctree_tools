"""
tests/test_level_v2.py
───────────────────────
Unit tests for the v2 data model additions.
No Panda3D or GUI imports required.

Covers:
  - PolylineType enum
  - TextureInterval CRUD + split
  - LevelMeta new fields round-trip
  - WALL / ARCH / EYEPATH serialization round-trips
  - EyePath edge management
  - migrate_v1_to_v2 conversion
  - level_format.load() migrates v1 files transparently
"""
import json
import pytest
from pathlib import Path

from passages_tool.editor.level import (
    Level, Polyline, PolylineType, TextureInterval, LevelMeta,
)
from passages_tool.io.level_format import load, save, LevelIOError


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def round_trip(level: Level) -> Level:
    return Level.from_dict(level.to_dict())


def make_wall_level():
    level = Level()
    pl = Polyline.make_wall()
    for x in range(5):
        pl.vertices.append((float(x), 0.0))
    level.add_polyline(pl)
    return level, pl.id


# ─────────────────────────────────────────────────────────────────────────────
# PolylineType
# ─────────────────────────────────────────────────────────────────────────────

class TestPolylineType:
    def test_enum_values(self):
        assert PolylineType.WALL.value    == "wall"
        assert PolylineType.ARCH.value    == "arch"
        assert PolylineType.EYEPATH.value == "eyepath"

    def test_make_wall_default_type(self):
        pl = Polyline.make_new()
        assert pl.type == PolylineType.WALL

    def test_make_wall_factory(self):
        assert Polyline.make_wall().type == PolylineType.WALL

    def test_make_arch_factory(self):
        pl = Polyline.make_arch((3.0, 4.0))
        assert pl.type == PolylineType.ARCH
        assert pl.position == (3.0, 4.0)

    def test_make_eyepath_factory(self):
        assert Polyline.make_eyepath().type == PolylineType.EYEPATH


# ─────────────────────────────────────────────────────────────────────────────
# LevelMeta new fields
# ─────────────────────────────────────────────────────────────────────────────

class TestLevelMeta:
    def test_defaults(self):
        m = LevelMeta()
        assert m.wall_height        == 4.0
        assert m.eye_height         == 1.7
        assert m.fov_h              == 90.0
        assert m.fov_v              == 60.0
        assert m.pixels_per_meter   == 256.0
        assert m.fog_start          == 20.0
        assert m.fog_end            == 40.0
        assert m.snap_grid          == 0.25
        assert m.render_width       == 1024
        assert m.render_height      == 768
        assert m.floor_texture      is None
        assert m.ceiling_texture    is None

    def test_meta_round_trip(self):
        level = Level()
        level.meta.wall_height     = 5.0
        level.meta.eye_height      = 1.5
        level.meta.fog_start       = 15.0
        level.meta.floor_texture   = "floor.png"
        level.meta.ceiling_texture = "ceiling.png"
        level.meta.pixels_per_meter = 128.0
        level.meta.render_width    = 1920
        level.meta.render_height   = 1080
        restored = round_trip(level)
        assert restored.meta.wall_height     == 5.0
        assert restored.meta.eye_height      == 1.5
        assert restored.meta.fog_start       == 15.0
        assert restored.meta.floor_texture   == "floor.png"
        assert restored.meta.ceiling_texture == "ceiling.png"
        assert restored.meta.pixels_per_meter == 128.0
        assert restored.meta.render_width    == 1920
        assert restored.meta.render_height   == 1080

    def test_meta_missing_fields_get_defaults(self):
        """from_dict() must supply defaults for any missing meta keys."""
        data = {"version": 2, "meta": {"name": "Test"}, "polylines": []}
        level = Level.from_dict(data)
        assert level.meta.wall_height == 4.0
        assert level.meta.snap_grid   == 0.25
        assert level.meta.pixels_per_meter == 256.0
        assert level.meta.render_width == 1024
        assert level.meta.render_height == 768


    def test_legacy_texture_pixel_size_migration(self):
        """Older files with texture_pixel_size should migrate to pixels_per_meter = 1/size."""
        data = {
            "version": 2,
            "meta": {
                "name": "Test Legacy",
                "texture_pixel_size": 0.01  # equivalent to 100 pixels per meter
            },
            "polylines": []
        }
        level = Level.from_dict(data)
        assert level.meta.pixels_per_meter == 100.0


# ─────────────────────────────────────────────────────────────────────────────
# TextureInterval CRUD
# ─────────────────────────────────────────────────────────────────────────────

class TestTextureIntervals:
    def test_add_interval(self):
        level, pid = make_wall_level()
        iv = TextureInterval(from_vertex=0, to_vertex=2, texture="stone.png")
        level.add_texture_interval(pid, iv)
        pl = level.get_polyline(pid)
        assert len(pl.texture_intervals) == 1
        assert pl.texture_intervals[0].texture == "stone.png"
        assert level.dirty

    def test_add_multiple_intervals_sorted(self):
        level, pid = make_wall_level()
        level.add_texture_interval(pid, TextureInterval(2, 4, "brick.png"))
        level.add_texture_interval(pid, TextureInterval(0, 2, "stone.png"))
        pl = level.get_polyline(pid)
        assert pl.texture_intervals[0].from_vertex == 0
        assert pl.texture_intervals[1].from_vertex == 2

    def test_remove_interval(self):
        level, pid = make_wall_level()
        level.add_texture_interval(pid, TextureInterval(0, 4, "stone.png"))
        level.remove_texture_interval(pid, 0)
        assert level.get_polyline(pid).texture_intervals == []

    def test_remove_out_of_range_is_noop(self):
        level, pid = make_wall_level()
        level.remove_texture_interval(pid, 99)   # should not raise

    def test_split_interval(self):
        level, pid = make_wall_level()
        level.add_texture_interval(pid, TextureInterval(0, 4, "stone.png"))
        level.split_texture_interval(pid, 2)
        pl = level.get_polyline(pid)
        assert len(pl.texture_intervals) == 2
        assert pl.texture_intervals[0].to_vertex   == 2
        assert pl.texture_intervals[1].from_vertex == 2
        assert pl.texture_intervals[1].to_vertex   == 4

    def test_split_copies_texture_to_second_interval(self):
        level, pid = make_wall_level()
        level.add_texture_interval(pid, TextureInterval(0, 4, "wall.png"))
        level.split_texture_interval(pid, 2)
        pl = level.get_polyline(pid)
        assert pl.texture_intervals[1].texture == "wall.png"

    def test_split_resets_x_offset_on_second(self):
        level, pid = make_wall_level()
        level.add_texture_interval(
            pid, TextureInterval(0, 4, "wall.png", x_offset=12.5))
        level.split_texture_interval(pid, 2)
        pl = level.get_polyline(pid)
        assert pl.texture_intervals[1].x_offset == 0.0

    def test_split_at_boundary_is_noop(self):
        level, pid = make_wall_level()
        level.add_texture_interval(pid, TextureInterval(0, 4, "wall.png"))
        level.split_texture_interval(pid, 0)   # at from_vertex → no split
        level.split_texture_interval(pid, 4)   # at to_vertex → no split
        assert len(level.get_polyline(pid).texture_intervals) == 1

    def test_interval_round_trip(self):
        level, pid = make_wall_level()
        level.add_texture_interval(
            pid, TextureInterval(0, 3, "stone.png", x_offset=5.0))
        level.add_texture_interval(
            pid, TextureInterval(3, 4, "brick.png"))
        restored = round_trip(level)
        ivs = restored.get_polyline(pid).texture_intervals
        assert len(ivs) == 2
        assert ivs[0].texture  == "stone.png"
        assert ivs[0].x_offset == 5.0
        assert ivs[1].texture  == "brick.png"


# ─────────────────────────────────────────────────────────────────────────────
# WALL serialization
# ─────────────────────────────────────────────────────────────────────────────

class TestWallSerialization:
    def test_wall_type_in_dict(self):
        pl = Polyline.make_wall()
        assert pl.to_dict()["type"] == "wall"

    def test_wall_round_trip(self):
        pl = Polyline.make_wall()
        pl.vertices = [(0.0, 0.0), (5.0, 0.0), (5.0, 3.0)]
        pl.closed   = True
        pl.texture_intervals = [TextureInterval(0, 2, "stone.png")]
        restored = Polyline.from_dict(pl.to_dict())
        assert restored.type == PolylineType.WALL
        assert restored.vertices == [(0.0, 0.0), (5.0, 0.0), (5.0, 3.0)]
        assert restored.closed is True
        assert restored.texture_intervals[0].texture == "stone.png"

    def test_set_polyline_texture_creates_interval(self):
        level = Level()
        pl = Polyline.make_wall()
        pl.vertices = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        level.add_polyline(pl)
        level.set_polyline_texture(pl.id, "stone.png")
        ivs = level.get_polyline(pl.id).texture_intervals
        assert len(ivs) == 1
        assert ivs[0].texture == "stone.png"
        assert ivs[0].from_vertex == 0
        assert ivs[0].to_vertex   == 2   # n = len(vertices) - 1


# ─────────────────────────────────────────────────────────────────────────────
# ARCH serialization
# ─────────────────────────────────────────────────────────────────────────────

class TestArchSerialization:
    def _make_arch(self) -> Polyline:
        pl = Polyline.make_arch((3.0, 7.0))
        pl.orientation    = 45.0
        pl.width          = 3.5
        pl.texture        = "arch_gothic.png"
        pl.transparency   = "alpha_blend"
        pl.z_offset       = 0.5
        pl.v_at_floor     = True
        pl.is_light_source= True
        pl.light_color    = (1.0, 0.5, 0.2)
        pl.light_intensity= 2.5
        pl.warning        = True
        return pl

    def test_arch_type_in_dict(self):
        assert self._make_arch().to_dict()["type"] == "arch"

    def test_arch_position_round_trip(self):
        pl = self._make_arch()
        restored = Polyline.from_dict(pl.to_dict())
        assert restored.position == (3.0, 7.0)

    def test_arch_fields_round_trip(self):
        pl = self._make_arch()
        restored = Polyline.from_dict(pl.to_dict())
        assert restored.orientation     == 45.0
        assert restored.width           == 3.5
        assert restored.texture         == "arch_gothic.png"
        assert restored.transparency    == "alpha_blend"
        assert restored.z_offset        == 0.5
        assert restored.v_at_floor      is True
        assert restored.is_light_source is True
        assert restored.light_color     == (1.0, 0.5, 0.2)
        assert restored.light_intensity == 2.5
        assert restored.warning         is True

    def test_arch_billboard_orientation(self):
        pl = Polyline.make_arch()
        pl.orientation = "billboard"
        restored = Polyline.from_dict(pl.to_dict())
        assert restored.orientation == "billboard"

    def test_arch_position_property_setter(self):
        pl = Polyline.make_arch((0.0, 0.0))
        pl.position = (9.0, 11.0)
        assert pl.vertices[0] == (9.0, 11.0)

    def test_set_polyline_texture_sets_arch_texture_directly(self):
        level = Level()
        pl = Polyline.make_arch((1.0, 1.0))
        level.add_polyline(pl)
        level.set_polyline_texture(pl.id, "torch.png")
        assert level.get_polyline(pl.id).texture == "torch.png"


# ─────────────────────────────────────────────────────────────────────────────
# EYEPATH serialization + edge management
# ─────────────────────────────────────────────────────────────────────────────

class TestEyePathSerialization:
    def _make_eyepath(self) -> Polyline:
        pl = Polyline.make_eyepath()
        pl.vertices = [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0)]
        pl.edges    = [(0, 1), (1, 2)]
        return pl

    def test_eyepath_type_in_dict(self):
        assert self._make_eyepath().to_dict()["type"] == "eyepath"

    def test_eyepath_round_trip(self):
        pl = self._make_eyepath()
        restored = Polyline.from_dict(pl.to_dict())
        assert restored.type     == PolylineType.EYEPATH
        assert restored.vertices == [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0)]
        assert (0, 1) in restored.edges
        assert (1, 2) in restored.edges

    def test_add_eyepath_edge(self):
        level = Level()
        pl = Polyline.make_eyepath()
        pl.vertices = [(0.0, 0.0), (1.0, 0.0)]
        level.add_polyline(pl)
        level.add_eyepath_edge(pl.id, 0, 1)
        assert (0, 1) in level.get_polyline(pl.id).edges
        assert level.dirty

    def test_add_eyepath_edge_no_duplicate(self):
        level = Level()
        pl = Polyline.make_eyepath()
        pl.vertices = [(0.0, 0.0), (1.0, 0.0)]
        level.add_polyline(pl)
        level.add_eyepath_edge(pl.id, 0, 1)
        level.add_eyepath_edge(pl.id, 0, 1)
        assert len(level.get_polyline(pl.id).edges) == 1

    def test_remove_eyepath_edge(self):
        level = Level()
        pl = Polyline.make_eyepath()
        pl.vertices = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        level.add_polyline(pl)
        level.add_eyepath_edge(pl.id, 0, 1)
        level.add_eyepath_edge(pl.id, 1, 2)
        level.remove_eyepath_edge(pl.id, 0, 1)
        edges = level.get_polyline(pl.id).edges
        assert (0, 1) not in edges
        assert (1, 2) in edges

    def test_remove_nonexistent_edge_is_noop(self):
        level = Level()
        pl = Polyline.make_eyepath()
        level.add_polyline(pl)
        level.remove_eyepath_edge(pl.id, 0, 1)   # should not raise

    def test_add_edge_only_on_eyepath_type(self):
        """add_eyepath_edge must be a no-op on non-EYEPATH polylines."""
        level = Level()
        pl = Polyline.make_wall()
        pl.vertices = [(0.0, 0.0), (1.0, 0.0)]
        level.add_polyline(pl)
        level.add_eyepath_edge(pl.id, 0, 1)
        assert level.get_polyline(pl.id).edges == []


# ─────────────────────────────────────────────────────────────────────────────
# migrate_v1_to_v2
# ─────────────────────────────────────────────────────────────────────────────

class TestMigrateV1ToV2:
    def _v1_data(self):
        return {
            "version": 1,
            "meta":    {"name": "OldLevel", "author": "Bob"},
            "grid":    {"cell_size": 1.0},
            "tiles":   [],
            "polylines": [
                {
                    "id":       "abc-123",
                    "vertices": [[0.0, 0.0], [5.0, 0.0], [5.0, 3.0]],
                    "texture":  "stone.png",
                    "closed":   False,
                },
                {
                    "id":       "def-456",
                    "vertices": [[1.0, 1.0]],
                    "texture":  None,
                    "closed":   False,
                },
            ],
        }

    def test_version_bumped_to_2(self):
        data = Level.migrate_v1_to_v2(self._v1_data())
        assert data["version"] == 2

    def test_type_defaults_to_wall(self):
        data = Level.migrate_v1_to_v2(self._v1_data())
        for pd in data["polylines"]:
            assert pd["type"] == "wall"

    def test_texture_converted_to_interval(self):
        data = Level.migrate_v1_to_v2(self._v1_data())
        pl0 = data["polylines"][0]
        assert "texture_intervals" in pl0
        assert len(pl0["texture_intervals"]) == 1
        iv = pl0["texture_intervals"][0]
        assert iv["texture"]      == "stone.png"
        assert iv["from_vertex"]  == 0
        assert iv["to_vertex"]    == 2   # len(vertices) - 1
        assert iv["x_offset"]     == 0.0

    def test_null_texture_produces_empty_intervals(self):
        data = Level.migrate_v1_to_v2(self._v1_data())
        pl1 = data["polylines"][1]
        assert pl1["texture_intervals"] == []

    def test_texture_field_removed_after_migration(self):
        data = Level.migrate_v1_to_v2(self._v1_data())
        for pd in data["polylines"]:
            assert "texture" not in pd

    def test_meta_gains_new_fields(self):
        data = Level.migrate_v1_to_v2(self._v1_data())
        meta = data["meta"]
        assert meta["wall_height"]  == 4.0
        assert meta["eye_height"]   == 1.7
        assert meta["snap_grid"]    == 0.25
        assert meta["fog_start"]    == 20.0
        assert meta["floor_texture"] is None

    def test_existing_meta_fields_preserved(self):
        data = Level.migrate_v1_to_v2(self._v1_data())
        assert data["meta"]["name"]   == "OldLevel"
        assert data["meta"]["author"] == "Bob"

    def test_original_data_not_mutated(self):
        original = self._v1_data()
        Level.migrate_v1_to_v2(original)
        assert original["version"] == 1   # deep copy; original untouched

    def test_migrated_data_loads_as_level(self):
        data    = Level.migrate_v1_to_v2(self._v1_data())
        level   = Level.from_dict(data)
        pl      = level.get_polyline("abc-123")
        assert pl is not None
        assert pl.type == PolylineType.WALL
        assert pl.texture_intervals[0].texture == "stone.png"
        assert level.meta.wall_height == 4.0


# ─────────────────────────────────────────────────────────────────────────────
# level_format.load() migration integration
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadMigratesV1Files:
    def _write_v1(self, tmp_path: Path) -> Path:
        data = {
            "version": 1,
            "meta":    {"name": "Legacy"},
            "grid":    {"cell_size": 1.0},
            "tiles":   [],
            "polylines": [
                {"id": "pl-1",
                 "vertices": [[0.0, 0.0], [3.0, 0.0]],
                 "texture": "brick.png",
                 "closed": False}
            ],
        }
        p = tmp_path / "legacy.passages.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    def test_v1_file_loads_without_error(self, tmp_path):
        p = self._write_v1(tmp_path)
        level = load(p)
        assert level is not None

    def test_v1_file_polylines_migrated(self, tmp_path):
        p = self._write_v1(tmp_path)
        level = load(p)
        pl = level.get_polyline("pl-1")
        assert pl.type == PolylineType.WALL
        assert pl.texture_intervals[0].texture == "brick.png"

    def test_v1_file_meta_migrated(self, tmp_path):
        p = self._write_v1(tmp_path)
        level = load(p)
        assert level.meta.wall_height == 4.0
        assert level.meta.name        == "Legacy"

    def test_save_then_load_v2_roundtrip(self, tmp_path):
        """Save a v2 level, reload it; all fields survive."""
        level = Level()
        level.meta.wall_height   = 3.5
        level.meta.floor_texture = "cobble.png"
        wall = Polyline.make_wall()
        wall.vertices = [(0.0, 0.0), (4.0, 0.0)]
        wall.texture_intervals = [TextureInterval(0, 1, "stone.png")]
        level.add_polyline(wall)

        arch = Polyline.make_arch((2.0, 0.0))
        arch.is_light_source = True
        arch.light_color     = (1.0, 0.6, 0.2)
        level.add_polyline(arch)

        eye = Polyline.make_eyepath()
        eye.vertices = [(1.0, 1.0), (3.0, 1.0)]
        eye.edges    = [(0, 1)]
        level.add_polyline(eye)

        p = tmp_path / "test.passages.json"
        save(level, p)
        restored = load(p)

        assert restored.meta.wall_height   == 3.5
        assert restored.meta.floor_texture == "cobble.png"

        rwall = list(
            pl for pl in restored.polylines.values()
            if pl.type == PolylineType.WALL
        )[0]
        assert rwall.texture_intervals[0].texture == "stone.png"

        rarch = list(
            pl for pl in restored.polylines.values()
            if pl.type == PolylineType.ARCH
        )[0]
        assert rarch.is_light_source is True
        assert rarch.light_color     == (1.0, 0.6, 0.2)

        reye = list(
            pl for pl in restored.polylines.values()
            if pl.type == PolylineType.EYEPATH
        )[0]
        assert (0, 1) in reye.edges
