"""
editor/validator.py
───────────────────
Pure-Python level validation checks (no Panda3D dependencies).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from passages_tool.editor.level import (
    Level,
    PolylineType,
    _texture_intervals_overlap,
    interval_edge_indices,
    wall_edge_index_pairs,
)


@dataclass
class ValidationWarning:
    arch_id: str
    v_from: int
    v_to: int
    angle_deg: float
    message: str


def validate_textures(level: Level) -> list[ValidationWarning]:
    """
    Warn about assignable surfaces with no texture assigned — these render
    transparent. Checks every Wall edge (via its texture_intervals) plus the
    level floor and ceiling.

    Reuses ValidationWarning: `arch_id` carries the polyline id to highlight
    (empty for floor/ceiling, which are level-meta, not polylines).
    """
    warnings: list[ValidationWarning] = []

    # ── Walls: every edge must be covered by an interval with a real texture ──
    for pl in level.polylines.values():
        if pl.type != PolylineType.WALL:
            continue
        n = len(pl.vertices)
        if n < 2:
            continue
        edge_count = len(wall_edge_index_pairs(pl))
        if edge_count == 0:
            continue

        covered: set[int] = set()
        for iv in pl.texture_intervals:
            if not iv.texture:
                continue  # interval present but no texture -> not covered
            for e in interval_edge_indices(pl, iv):
                if 0 <= e < edge_count:
                    covered.add(e)

        uncovered = [e for e in range(edge_count) if e not in covered]
        ivs = pl.texture_intervals
        for i, a in enumerate(ivs):
            for b in ivs[i + 1:]:
                if _texture_intervals_overlap(a, b):
                    warnings.append(ValidationWarning(
                        arch_id=pl.id, v_from=a.from_vertex, v_to=a.to_vertex,
                        angle_deg=0.0,
                        message=(
                            f"Wall {pl.id[:8]}... has overlapping texture intervals "
                            f"V{a.from_vertex}–{a.to_vertex} and V{b.from_vertex}–{b.to_vertex} "
                            f"— they will z-fight."
                        ),
                    ))
                    break
        if uncovered:
            shown = ", ".join(str(e) for e in uncovered[:8])
            more = "" if len(uncovered) <= 8 else f" (+{len(uncovered) - 8} more)"
            msg = (
                f"Wall {pl.id[:8]}... has {len(uncovered)} untextured edge(s) "
                f"[{shown}{more}] — they will render transparent."
            )
            warnings.append(
                ValidationWarning(
                    arch_id=pl.id,
                    v_from=uncovered[0],
                    v_to=min(uncovered[0] + 1, n - 1),
                    angle_deg=0.0,
                    message=msg,
                )
            )

    # ── Floor / ceiling (level meta) ─────────────────────────────────────────
    if not level.meta.floor_texture:
        warnings.append(ValidationWarning(
            arch_id="", v_from=-1, v_to=-1, angle_deg=0.0,
            message="Floor has no texture assigned (Level Properties > floor) — it will render transparent.",
        ))
    if not level.meta.ceiling_texture:
        warnings.append(ValidationWarning(
            arch_id="", v_from=-1, v_to=-1, angle_deg=0.0,
            message="Ceiling has no texture assigned (Level Properties > ceiling) — it will render transparent.",
        ))

    return warnings


def validate_structure(level: Level) -> list[ValidationWarning]:
    """Warn about document-level issues (EyePath count, etc.)."""
    warnings: list[ValidationWarning] = []
    paths = level.eyepaths()
    if len(paths) > 1:
        extras = ", ".join(pl.id[:8] + "…" for pl in paths[1:3])
        more = f" (+{len(paths) - 3} more)" if len(paths) > 3 else ""
        warnings.append(ValidationWarning(
            arch_id=paths[1].id, v_from=-1, v_to=-1, angle_deg=0.0,
            message=(
                f"Level has {len(paths)} EyePath polylines; bake and preview use "
                f"only the first. Extra: {extras}{more}."
            ),
        ))
    return warnings


def validate_arch_visibility(
    level: Level,
    threshold_deg: float = 30.0,
) -> list[ValidationWarning]:
    """
    Validates that no fixed-rotation arches within fog_end range are edge-on
    from any EyePath directed viewpoint.
    Measured relative to the arch plane (90 = face-on, 0 = edge-on).
    """
    warnings = []

    # 1. Find EyePath polyline (bake/preview use the first; extras are warned separately)
    paths = level.eyepaths()
    eyepath_pl = paths[0] if paths else None

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

            # Angle between view vector and arch plane (90 = face-on, 0 = edge-on)
            dot_val = vx * nx + vy * ny
            abs_dot = min(1.0, max(-1.0, abs(dot_val)))
            angle_rad = math.asin(abs_dot)
            angle_deg = math.degrees(angle_rad)

            if angle_deg < threshold_deg:
                msg = (
                    f"Arch {arch.id[:8]}... is edge-on (view angle {angle_deg:.1f}° < {threshold_deg}°) "
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
