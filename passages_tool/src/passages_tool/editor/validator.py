"""
editor/validator.py
───────────────────
Pure-Python level validation checks (no Panda3D dependencies).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from passages_tool.editor.level import Level, PolylineType


@dataclass
class ValidationWarning:
    arch_id: str
    v_from: int
    v_to: int
    angle_deg: float
    message: str


def validate_arch_visibility(
    level: Level,
    threshold_deg: float = 60.0,
) -> list[ValidationWarning]:
    """
    Validates that no fixed-rotation arches within fog_end range are edge-on
    from any EyePath directed viewpoint.
    """
    warnings = []

    # 1. Find EyePath polyline
    eyepath_pl = None
    for pl in level.polylines.values():
        if pl.type == PolylineType.EYEPATH:
            eyepath_pl = pl
            break

    if not eyepath_pl or not eyepath_pl.edges:
        return warnings

    fog_end = level.meta.fog_end

    # 2. Iterate all directed EyePath edges (each represents a viewpoint)
    for v_from, v_to in eyepath_pl.edges:
        if v_from >= len(eyepath_pl.vertices) or v_to >= len(eyepath_pl.vertices):
            continue

        p_from = eyepath_pl.vertices[v_from]
        p_to = eyepath_pl.vertices[v_to]

        # Camera view vector (directed direction of movement/gaze)
        vx = p_to[0] - p_from[0]
        vy = p_to[1] - p_from[1]
        v_len = math.hypot(vx, vy)
        if v_len == 0.0:
            continue
        vx /= v_len
        vy /= v_len

        # 3. Check all fixed arches
        for arch in level.polylines.values():
            if arch.type != PolylineType.ARCH:
                continue
            if arch.orientation == "billboard":
                continue
            if not arch.vertices:
                continue

            arch_pos = arch.vertices[0]
            # Check if within fog_end distance
            dist = math.hypot(arch_pos[0] - p_from[0], arch_pos[1] - p_from[1])
            if dist > fog_end:
                continue

            try:
                theta_deg = float(arch.orientation)
            except (ValueError, TypeError):
                continue

            # Arch normal vector points along orientation (facing angle)
            theta_rad = math.radians(theta_deg)
            nx = math.cos(theta_rad)
            ny = math.sin(theta_rad)

            # Angle between normal and view vector
            dot_val = vx * nx + vy * ny
            abs_dot = min(1.0, max(-1.0, abs(dot_val)))
            angle_rad = math.acos(abs_dot)
            angle_deg = math.degrees(angle_rad)

            if angle_deg > threshold_deg:
                msg = (
                    f"Arch {arch.id[:8]}... is edge-on (view angle {angle_deg:.1f}° > {threshold_deg}°) "
                    f"when looking from vertex {v_from} to {v_to}."
                )
                warnings.append(
                    ValidationWarning(
                        arch_id=arch.id,
                        v_from=v_from,
                        v_to=v_to,
                        angle_deg=angle_deg,
                        message=msg,
                    )
                )

    return warnings
