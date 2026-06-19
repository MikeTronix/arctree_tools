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


# TransitionRenderer class has been retired. Viewpoint and midpoint bakes
# are now handled directly by ViewpointRenderer.
