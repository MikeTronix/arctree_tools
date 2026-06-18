"""
tests/test_transition.py
────────────────────────
Tests for the transition path computation and edge-on safety checks.
"""
from __future__ import annotations

import math
import pytest

from passages_tool.editor.level import Level, Polyline
from passages_tool.renderer.transition_renderer import (
    edge_on_check,
    compute_transition_path,
)


def test_edge_on_check_billboard():
    # Billboard arches should always pass (return False = not edge-on)
    arch = Polyline.make_arch()
    arch.orientation = "billboard"
    camera_pos = (0.0, 0.0)
    view_vector = (1.0, 0.0)
    assert edge_on_check(arch, camera_pos, view_vector) is False


def test_edge_on_check_fixed_orientations():
    # Setup a fixed arch
    arch = Polyline.make_arch()
    
    # 1. Arch oriented at 0 degrees.
    # Normal vector N = (cos(0), sin(0)) = (1, 0).
    # Width vector is along Y.
    arch.orientation = 0.0
    camera_pos = (0.0, 0.0)
    
    # View vector along Y: perpendicular to normal (edge-on, angle = 90)
    # Divergence is 90 deg > 60 deg threshold. Should return True (edge-on).
    assert edge_on_check(arch, camera_pos, (0.0, 1.0), threshold_deg=60.0) is True
    
    # View vector along X: parallel/anti-parallel to normal (face-on, angle = 0/180)
    # Divergence is 0 deg. Should return False (safe).
    assert edge_on_check(arch, camera_pos, (1.0, 0.0), threshold_deg=60.0) is False

    # 2. Check threshold boundary.
    # With threshold_deg = 60:
    # If view vector makes 30 degrees with normal, divergence is 30 <= 60 (safe).
    # If view vector makes 70 degrees with normal, divergence is 70 > 60 (unsafe).
    
    # Let's test view vector at 45 degrees: (cos(45), sin(45))
    # Dot product with (1, 0) is cos(45) = 0.707.
    # Angle is 45 degrees.
    assert edge_on_check(arch, camera_pos, (1.0, 1.0), threshold_deg=60.0) is False # 45 <= 60 -> safe
    assert edge_on_check(arch, camera_pos, (1.0, 1.0), threshold_deg=30.0) is True  # 45 > 30 -> unsafe


def test_compute_transition_path_simple():
    level = Level()
    
    # Setup eyepath: v0 at (0, 0), v1 at (10, 0)
    ep = Polyline.make_eyepath()
    ep.vertices = [(0.0, 0.0), (10.0, 0.0)]
    ep.edges = [(0, 1)]
    level.add_polyline(ep)
    
    # With no arches, path should travel full target distance: min(10.0 * 0.5, 1.5) = 1.5
    frames = compute_transition_path(0, 1, 4, level)
    assert len(frames) == 4
    
    # Heading should be 0.0 (along +X)
    for x, y, heading in frames:
        assert heading == 0.0
        assert y == 0.0
        
    # Positions should be linearly interpolated from 0.0 to 1.5
    assert frames[0][0] == pytest.approx(0.0)
    assert frames[1][0] == pytest.approx(0.5)
    assert frames[2][0] == pytest.approx(1.0)
    assert frames[3][0] == pytest.approx(1.5)


def test_compute_transition_path_capped_by_fixed_arch():
    level = Level()
    
    # Setup eyepath: v0 at (0, 0), v1 at (10, 0)
    ep = Polyline.make_eyepath()
    ep.vertices = [(0.0, 0.0), (10.0, 0.0)]
    ep.edges = [(0, 1)]
    level.add_polyline(ep)
    
    # Place a fixed arch at (1.0, 0.5) with orientation 0 degrees.
    # Normal is (cos(0), sin(0)) = (1, 0).
    # Since camera view direction is (+1, 0), they are parallel (dot product = 1, angle = 0 -> face-on).
    # So this arch should NOT trigger edge-on checks.
    arch1 = Polyline.make_arch()
    arch1.vertices = [(1.0, 0.5)]
    arch1.orientation = 0.0
    level.add_polyline(arch1)
    
    # Path should still go up to 1.5
    frames = compute_transition_path(0, 1, 4, level)
    assert frames[-1][0] == pytest.approx(1.5)

    # Place a fixed arch at (1.0, 0.5) with orientation 90 degrees.
    # Normal is (0, 1). Camera view is (+1, 0).
    # Perpendicular -> angle = 90 degrees -> edge-on!
    # Because it is at X = 1.0, any camera position near it (distance <= fog_end, e.g. 40.0)
    # will see it edge-on. Since the transition path starts at X=0, the camera sees it immediately.
    # Therefore, the path safety check should cap the travel distance at 0.0!
    arch1.orientation = 90.0
    
    frames_capped = compute_transition_path(0, 1, 4, level, threshold_deg=60.0)
    # All positions should remain at (0, 0)
    for x, y, heading in frames_capped:
        assert x == pytest.approx(0.0)
        assert y == pytest.approx(0.0)
