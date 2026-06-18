import math
import pytest
from passages_tool.editor.level import Level, Polyline
from passages_tool.editor.arch_utils import (
    nearest_wall_edge,
    is_tangent_ambiguous,
    arch_perpendicular_angle,
)

def test_arch_perpendicular_angle():
    assert arch_perpendicular_angle(0.0) == 0.0
    assert arch_perpendicular_angle(270.0) == 270.0

def test_nearest_wall_edge():
    level = Level()
    
    # Create a simple horizontal wall polyline
    wall = Polyline.make_wall()
    wall.vertices = [(0.0, 0.0), (10.0, 0.0)]
    level.add_polyline(wall)
    
    # Case 1: Point is close to the middle of the wall segment
    res = nearest_wall_edge((5.0, 1.0), level)
    assert res is not None
    wall_pid, edge_idx, tangent_ang, dist = res
    assert wall_pid == wall.id
    assert edge_idx == 0
    assert tangent_ang == 0.0
    assert math.isclose(dist, 1.0)
    
    # Case 2: Point is beyond the endpoints of the segment (clamped to segment)
    res_beyond = nearest_wall_edge((11.0, 0.0), level)
    assert res_beyond is not None
    assert res_beyond[1] == 0
    assert math.isclose(res_beyond[3], 1.0)  # distance to endpoint (10,0)

def test_is_tangent_ambiguous():
    level = Level()
    
    # Create a wall with a sharp corner at (5, 0)
    wall = Polyline.make_wall()
    wall.vertices = [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0)]
    level.add_polyline(wall)
    
    # Case 1: Placement is far from any vertex on the first segment
    assert not is_tangent_ambiguous(level, wall.id, 0, (2.5, 0.1), threshold_deg=30.0)
    
    # Case 2: Placement is very close to the corner vertex at (5, 0)
    # The two segments are horizontal (0 deg) and vertical (90 deg) -> diff is 90 deg.
    # This exceeds the threshold of 30 deg, so it should be ambiguous.
    assert is_tangent_ambiguous(level, wall.id, 0, (4.95, 0.01), threshold_deg=30.0)
    
    # Case 3: Placement is close to the endpoint at (0, 0)
    # Only one edge meets there, so it should not be ambiguous.
    assert not is_tangent_ambiguous(level, wall.id, 0, (0.05, 0.0), threshold_deg=30.0)
