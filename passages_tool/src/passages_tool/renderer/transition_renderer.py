"""
renderer/transition_renderer.py
───────────────────────────────
Calculates and renders transitions between EyePath viewpoints.
"""
from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Optional, Union

from PIL import Image
from panda3d.core import Filename, PNMImage, PerspectiveLens, PointLight, LColor

from passages_tool import config
from passages_tool.editor.level import Level, PolylineType


def edge_on_check(
    arch,
    camera_pos: tuple[float, float],
    view_vector: tuple[float, float],
    threshold_deg: float = 60.0,
) -> bool:
    """
    Returns True if the angle between the arch normal and the view vector
    diverges from face-on (0 or 180 degrees) by more than threshold_deg.
    Billboard arches are always immune (returns False).
    """
    if arch.orientation == "billboard":
        return False

    try:
        theta_deg = float(arch.orientation)
    except (ValueError, TypeError):
        return False

    # Arch normal points along orientation (facing angle)
    theta_rad = math.radians(theta_deg)
    nx = math.cos(theta_rad)
    ny = math.sin(theta_rad)

    # Normalize view vector
    vx, vy = view_vector
    v_len = math.hypot(vx, vy)
    if v_len == 0.0:
        return False
    vx /= v_len
    vy /= v_len

    # Dot product
    dot_val = vx * nx + vy * ny
    abs_dot = min(1.0, max(-1.0, abs(dot_val)))
    angle_rad = math.acos(abs_dot)
    angle_deg = math.degrees(angle_rad)

    # Divergence from face-on (0 degrees) is the angle to the normal/anti-normal
    # If angle_deg > threshold_deg, the view direction is too close to parallel to the arch plane
    return angle_deg > threshold_deg


def compute_transition_path(
    v_from: int,
    v_to: int,
    n_frames: int,
    level: Level,
    threshold_deg: float = 60.0,
) -> list[tuple[float, float, float]]:
    """
    Computes a transition path from v_from toward v_to.
    Distance is capped to keep all fixed arches within range comfortably face-on.
    Returns a list of (x, y, heading_deg) tuples.
    """
    # Find EyePath polyline
    eyepath_pl = None
    for pl in level.polylines.values():
        if pl.type == PolylineType.EYEPATH:
            eyepath_pl = pl
            break

    if not eyepath_pl or v_from >= len(eyepath_pl.vertices) or v_to >= len(eyepath_pl.vertices):
        return []

    p_from = eyepath_pl.vertices[v_from]
    p_to = eyepath_pl.vertices[v_to]

    dx = p_to[0] - p_from[0]
    dy = p_to[1] - p_from[1]
    dist = math.hypot(dx, dy)

    if dist == 0.0:
        return [(p_from[0], p_from[1], 0.0)] * n_frames

    ux = dx / dist
    uy = dy / dist
    heading_rad = math.atan2(dy, dx)
    heading_deg = math.degrees(heading_rad)

    # Default limits
    max_dist = getattr(config, "DEFAULT_TRANSITION_MAX_DIST", 1.5)
    target_dist = min(dist * 0.5, max_dist)

    # Find maximum safe travel distance
    safe_dist = target_dist
    fog_end = level.meta.fog_end

    # Check 50 samples along the candidate path
    for step in range(51):
        d = (step / 50.0) * target_dist
        pos_x = p_from[0] + d * ux
        pos_y = p_from[1] + d * uy

        for arch in level.polylines.values():
            if arch.type != PolylineType.ARCH:
                continue
            if arch.orientation == "billboard":
                continue

            arch_pos = arch.vertices[0]
            dist_to_arch = math.hypot(arch_pos[0] - pos_x, arch_pos[1] - pos_y)
            if dist_to_arch > fog_end:
                continue

            if edge_on_check(arch, (pos_x, pos_y), (ux, uy), threshold_deg):
                # Unsafe! Cap at previous safe step
                safe_dist = ((step - 1) / 50.0) * target_dist if step > 0 else 0.0
                break
        else:
            continue
        break

    # Generate the frames
    frames = []
    for step in range(n_frames):
        t = (step / (n_frames - 1)) if n_frames > 1 else 0.0
        d = t * safe_dist
        x = p_from[0] + d * ux
        y = p_from[1] + d * uy
        frames.append((x, y, heading_deg))

    return frames


class TransitionRenderer:
    """Manages offscreen rendering of transition animations."""

    def __init__(self, viewpoint_renderer) -> None:
        """Shares the ShowBase context from an initialized ViewpointRenderer."""
        self.v_renderer = viewpoint_renderer
        self.base = viewpoint_renderer.base
        self.level = viewpoint_renderer.level
        self.scene_root = viewpoint_renderer.scene_root

    def render_transition(
        self,
        v_from: int,
        v_to: int,
        fwd_gif_path: Path,
        rev_gif_path: Path,
        n_frames: int = 8,
        width: Optional[int] = None,
        height: Optional[int] = None,
        threshold_deg: float = 60.0,
    ) -> tuple[bool, bool]:
        """
        Renders transition animations (forward and reverse) for the undirected edge.
        Saves as two animated GIFs.
        """
        # Resolve dimensions
        render_w = width if width is not None else self.level.meta.render_width
        render_h = height if height is not None else self.level.meta.render_height
        eye_height = self.level.meta.eye_height
        fov_h = self.level.meta.fov_h
        fov_v = self.level.meta.fov_v

        # 1. Compute paths
        fwd_path = compute_transition_path(v_from, v_to, n_frames, self.level, threshold_deg)
        rev_path = compute_transition_path(v_to, v_from, n_frames, self.level, threshold_deg)

        if not fwd_path or not rev_path:
            return False, False

        # Find EyePath vertices to get the exact look-at targets
        eyepath_pl = None
        for pl in self.level.polylines.values():
            if pl.type == PolylineType.EYEPATH:
                eyepath_pl = pl
                break
        if not eyepath_pl:
            return False, False

        p_from = eyepath_pl.vertices[v_from]
        p_to = eyepath_pl.vertices[v_to]

        # 2. Setup offscreen buffer and camera
        buffer = self.base.win.make_texture_buffer("trans_buf", render_w, render_h)
        if not buffer:
            return False, False

        cam = self.base.make_camera(buffer)
        cam.reparent_to(self.scene_root)
        lens = PerspectiveLens()
        lens.set_fov(fov_h, fov_v)
        lens.set_near_far(0.1, 100.0)
        cam.node().set_lens(lens)

        # Add camera headlight (PointLight) so the scene is illuminated from the viewer's viewpoint
        plight = PointLight("camera_headlight")
        plight.set_color(LColor(1.0, 1.0, 1.0, 1.0))
        plight.set_attenuation((0.0, 0.0, 0.03))
        pl_path = cam.attach_new_node(plight)
        pl_path.set_pos(0, 0, 0)
        self.scene_root.set_light(pl_path)

        def render_sequence(path, look_target) -> list[Image.Image]:
            import tempfile
            frames_pil = []
            for x, y, _ in path:
                cam.set_pos(x, y, eye_height)
                cam.look_at(look_target[0], look_target[1], eye_height)

                # Render twice to ensure texture loading
                self.base.graphicsEngine.render_frame()
                self.base.graphicsEngine.render_frame()

                pnm = PNMImage()
                if buffer.get_screenshot(pnm):
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        tmp_path = Path(tmp.name)
                    try:
                        pnm.write(Filename.from_os_specific(str(tmp_path)))
                        # Open and load image data, making a copy so the file can be safely unlinked
                        with Image.open(tmp_path) as img:
                            frames_pil.append(img.copy())
                    finally:
                        if tmp_path.exists():
                            tmp_path.unlink()
            return frames_pil

        fwd_ok = False
        rev_ok = False

        try:
            # Render forward
            fwd_frames = render_sequence(fwd_path, p_to)
            if len(fwd_frames) == n_frames:
                fwd_gif_path.parent.mkdir(parents=True, exist_ok=True)
                fwd_frames[0].save(
                    fwd_gif_path,
                    save_all=True,
                    append_images=fwd_frames[1:],
                    duration=50,  # 50ms per frame
                    loop=0,
                )
                fwd_ok = True

            # Render reverse
            rev_frames = render_sequence(rev_path, p_from)
            if len(rev_frames) == n_frames:
                rev_gif_path.parent.mkdir(parents=True, exist_ok=True)
                rev_frames[0].save(
                    rev_gif_path,
                    save_all=True,
                    append_images=rev_frames[1:],
                    duration=50,
                    loop=0,
                )
                rev_ok = True
        finally:
            self.scene_root.clear_light(pl_path)
            self.base.graphicsEngine.remove_window(buffer)
            cam.remove_node()

        return fwd_ok, rev_ok
