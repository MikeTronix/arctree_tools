"""
viewport/grid.py
────────────────
Draws the background grid using LineSegs on the `render` scene graph.

The grid is rebuilt whenever the camera zoom or pan moves enough to make the
current grid stale (i.e., when the visible world-space region changes).

Minor grid lines are drawn every GRID_CELL units.
Major grid lines (thicker / brighter) every GRID_MAJOR_EVERY minor lines.
"""
from __future__ import annotations

import math

from panda3d.core import LineSegs, NodePath, LColor

from passages_tool.config import (
    GRID_CELL,
    GRID_COLOR_MAJOR,
    GRID_COLOR_MINOR,
    GRID_MAJOR_EVERY,
)


class BackgroundGrid:
    """Manages a LineSegs-based background grid on the render node."""

    def __init__(self, render_root: NodePath) -> None:
        self._root      = render_root
        self._node_path: NodePath | None = None

    def rebuild(self, film_w: float, film_h: float, cam_x: float, cam_z: float) -> None:
        """
        Rebuild grid lines to cover the visible world region.

        Args:
            film_w / film_h: visible world-space dimensions.
            cam_x / cam_z:   camera world position (centre of view).
        """
        if self._node_path:
            self._node_path.removeNode()
            self._node_path = None

        segs = LineSegs()
        segs.setThickness(1.0)

        # Compute visible world extents with a 20 % margin.
        margin   = 0.2
        half_w   = film_w * (0.5 + margin)
        half_h   = film_h * (0.5 + margin)
        x_left   = cam_x - half_w
        x_right  = cam_x + half_w
        z_bottom = cam_z - half_h
        z_top    = cam_z + half_h

        # Snap grid start to cell boundary.
        cell = GRID_CELL
        x_start = math.floor(x_left  / cell) * cell
        z_start = math.floor(z_bottom / cell) * cell

        # Vertical lines.
        x = x_start
        col_idx = int(round(x_start / cell))
        while x <= x_right:
            is_major = (col_idx % GRID_MAJOR_EVERY) == 0
            color    = GRID_COLOR_MAJOR if is_major else GRID_COLOR_MINOR
            segs.setColor(LColor(*color))
            segs.moveTo(x, 0, z_bottom)
            segs.drawTo(x, 0, z_top)
            x       += cell
            col_idx += 1

        # Horizontal lines.
        z = z_start
        row_idx = int(round(z_start / cell))
        while z <= z_top:
            is_major = (row_idx % GRID_MAJOR_EVERY) == 0
            color    = GRID_COLOR_MAJOR if is_major else GRID_COLOR_MINOR
            segs.setColor(LColor(*color))
            segs.moveTo(x_left,  0, z)
            segs.drawTo(x_right, 0, z)
            z       += cell
            row_idx += 1

        node = segs.create(dynamic=False)
        self._node_path = self._root.attachNewNode(node)
        # Render behind everything else.
        self._node_path.setBin("background", 0)
        self._node_path.setDepthWrite(False)

    def destroy(self) -> None:
        if self._node_path:
            self._node_path.removeNode()
            self._node_path = None
