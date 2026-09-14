"""Unit tests for helpers extracted from main.py (P2 split)."""
from passages_tool.app.commands import convert_polyline_type
from passages_tool.app.input import _point_seg_dist2
from passages_tool.editor.level import Polyline, PolylineType


def test_point_seg_dist2_at_endpoint():
    assert _point_seg_dist2(0.0, 0.0, 0.0, 0.0, 1.0, 0.0) == 0.0


def test_point_seg_dist2_mid_perpendicular():
    d2 = _point_seg_dist2(0.5, 1.0, 0.0, 0.0, 1.0, 0.0)
    assert abs(d2 - 1.0) < 1e-9


def test_convert_wall_to_arch_keeps_first_vertex():
    pl = Polyline.make_wall()
    pl.vertices = [(1.0, 2.0), (3.0, 4.0)]
    pl.closed = True
    pl.edges = [(0, 1)]
    convert_polyline_type(pl, PolylineType.ARCH)
    assert pl.type == PolylineType.ARCH
    assert pl.vertices == [(1.0, 2.0)]
    assert pl.texture_intervals == []
    assert pl.edges == []
    assert pl.closed is False


def test_convert_wall_to_eyepath_drops_intervals():
    pl = Polyline.make_wall()
    pl.vertices = [(0.0, 0.0), (1.0, 0.0)]
    convert_polyline_type(pl, PolylineType.EYEPATH)
    assert pl.type == PolylineType.EYEPATH
    assert pl.texture_intervals == []
    assert pl.closed is False
    assert pl.vertices == [(0.0, 0.0), (1.0, 0.0)]
