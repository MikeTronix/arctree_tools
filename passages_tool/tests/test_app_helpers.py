"""Unit tests for helpers extracted from main.py (P2 split)."""
from passages_tool.app.input import _point_seg_dist2
from passages_tool.editor.level import Polyline, PolylineType, convert_polyline_type
from passages_tool.editor.polyline_data import Arch, EyePath
from passages_tool.ui.properties import outgoing_vertex_index


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


def test_outgoing_vertex_index_open_polyline():
    assert outgoing_vertex_index(5, 0, False) == 1
    assert outgoing_vertex_index(5, 4, False) is None
    assert outgoing_vertex_index(1, 0, False) is None


def test_outgoing_vertex_index_closed_wall():
    assert outgoing_vertex_index(4, 0, True) == 1
    assert outgoing_vertex_index(4, 3, True) == 0


def test_eyepath_insert_uses_open_chain():
    ep = EyePath(id="e", vertices=[(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])
    assert not hasattr(ep, "closed")
    closed = bool(getattr(ep, "closed", False))
    assert outgoing_vertex_index(len(ep.vertices), 0, closed) == 1
    assert outgoing_vertex_index(len(ep.vertices), 2, closed) is None
