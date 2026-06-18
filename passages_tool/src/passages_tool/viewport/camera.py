"""
viewport/camera.py
──────────────────
2D orthographic camera for the level viewport.

Coordinate convention
─────────────────────
  - The level is laid out in the XZ plane (Panda3D is Z-up).
  - The camera sits at Y = -100, looking in the +Y direction.
  - "World X" maps to screen left/right; "World Z" maps to screen up/down.
  - Pan moves the camera's X and Z position.
  - Zoom adjusts the OrthographicLens film size.

Usage
─────
    cam = ViewportCamera(base, win_w, win_h)
    cam.pan(dx, dz)      # world-unit offset
    cam.zoom_by(delta)   # positive = zoom in (smaller film)
    wx, wz = cam.screen_to_world(mx, my)   # normalised screen → world
"""
from __future__ import annotations

from panda3d.core import (
    NodePath,
    OrthographicLens,
    Point2,
    Point3,
)

from passages_tool.config import (
    VIEWPORT_DEFAULT_FILM_W,
    ZOOM_MAX,
    ZOOM_MIN,
    ZOOM_STEP,
)


class ViewportCamera:
    """Wraps Panda3D's default camera with an orthographic lens and pan/zoom."""

    def __init__(self, base, win_w: int, win_h: int) -> None:
        self._base   = base
        self._win_w  = win_w
        self._win_h  = win_h

        # Remove the default mouse-flight controller.
        base.disableMouse()

        # Set up orthographic lens.
        self._lens = OrthographicLens()
        self._film_w: float = VIEWPORT_DEFAULT_FILM_W
        self._set_film()
        self._lens.setNearFar(-1000, 1000)
        base.cam.node().setLens(self._lens)

        # Position camera: X=0, Y=-100, Z=0, looking in +Y.
        base.cam.setPos(0, -100, 0)
        base.cam.lookAt(Point3(0, 0, 0))

        # Track camera world-space position (X/Z only; Y is fixed).
        self._cam_x: float = 0.0
        self._cam_z: float = 0.0

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def film_w(self) -> float:
        return self._film_w

    @property
    def zoom(self) -> float:
        """Effective zoom: world units per screen pixel (approx)."""
        return self._film_w / self._win_w

    # ── Pan ───────────────────────────────────────────────────────────────────

    def pan(self, dx_world: float, dz_world: float) -> None:
        """Move the camera by (dx_world, dz_world) in world units."""
        self._cam_x -= dx_world
        self._cam_z -= dz_world
        self._base.cam.setPos(self._cam_x, -100, self._cam_z)

    # ── Zoom ──────────────────────────────────────────────────────────────────

    def zoom_by(self, delta: int) -> None:
        """
        Zoom in (delta < 0) or out (delta > 0) by ZOOM_STEP per scroll click.
        Keeps the view centred on the current camera position.
        """
        factor = 1.0 - ZOOM_STEP * (-delta)  # scroll up → delta<0 → factor<1 → film shrinks
        self._film_w = max(ZOOM_MIN, min(ZOOM_MAX, self._film_w * factor))
        self._set_film()

    def zoom_to_fit(self, left: float, right: float, bottom: float, top: float) -> None:
        """Adjust film size and position to fit a world-space bounding box."""
        cx = (left + right) / 2
        cz = (bottom + top) / 2
        padding = 2.0
        self._film_w = max(right - left + padding, (top - bottom + padding) * self._aspect())
        self._cam_x = cx
        self._cam_z = cz
        self._base.cam.setPos(cx, -100, cz)
        self._set_film()

    # ── Coordinate conversion ─────────────────────────────────────────────────

    def screen_to_world(self, mx: float, my: float) -> tuple[float, float]:
        """
        Convert normalised screen coordinates in [-1, 1] to world (X, Z).
        mx = -1 is left edge, +1 is right edge; my = -1 bottom, +1 top.
        """
        near = Point3()
        far  = Point3()
        self._lens.extrude(Point2(mx, my), near, far)
        # The camera sits at Y=-100 looking in +Y; near/far are in camera space.
        # Transform from camera space to world space (render).
        cam_np: NodePath = self._base.cam
        render_np: NodePath = self._base.render
        near_w = render_np.getRelativePoint(cam_np, near)
        far_w  = render_np.getRelativePoint(cam_np, far)
        # Intersect the ray with the level plane at Y=0 in world space.
        # The camera is at Y=-100 looking in +Y, so find t where Y=0.
        dy = far_w.y - near_w.y
        if abs(dy) < 1e-9:
            return (0.0, 0.0)
        t = -near_w.y / dy
        wx = near_w.x + t * (far_w.x - near_w.x)
        wz = near_w.z + t * (far_w.z - near_w.z)
        return (wx, wz)

    def world_to_screen(self, wx: float, wz: float) -> tuple[float, float]:
        """Convert world (X, Z) to normalised screen [-1, 1]."""
        p3 = Point3(wx, 0, wz)
        p2 = Point2()
        # Transform point from world space (render) to camera space.
        cam_np: NodePath = self._base.cam
        render_np: NodePath = self._base.render
        cam_p3 = cam_np.getRelativePoint(render_np, p3)
        self._lens.project(cam_p3, p2)
        return (float(p2.x), float(p2.y))

    # ── Window resize ─────────────────────────────────────────────────────────

    def on_resize(self, win_w: int, win_h: int) -> None:
        self._win_w = win_w
        self._win_h = win_h
        self._set_film()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _aspect(self) -> float:
        return self._win_w / max(1, self._win_h)

    def _set_film(self) -> None:
        film_h = self._film_w / self._aspect()
        self._lens.setFilmSize(self._film_w, film_h)
