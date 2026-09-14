"""Unit tests for helpers extracted from main.py (P2 split)."""
from passages_tool.app.input import _point_seg_dist2
from passages_tool.editor.level import Polyline, PolylineType, convert_polyline_type
from passages_tool.editor.polyline_data import Arch, EyePath


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
    out = convert_polyline_type(pl, PolylineType.ARCH)
    assert isinstance(out, Arch)
    assert out.id == pl.id
    assert out.vertices == [(1.0, 2.0)]
    assert not hasattr(out, "texture_intervals")
    assert not hasattr(out, "edges")


def test_convert_wall_to_eyepath_drops_intervals():
    pl = Polyline.make_wall()
    pl.vertices = [(0.0, 0.0), (1.0, 0.0)]
    out = convert_polyline_type(pl, PolylineType.EYEPATH)
    assert isinstance(out, EyePath)
    assert out.vertices == [(0.0, 0.0), (1.0, 0.0)]
    assert out.edges == []
    assert not hasattr(out, "texture_intervals")
