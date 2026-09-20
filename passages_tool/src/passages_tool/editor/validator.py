"""
editor/validator.py
───────────────────
Pure-Python level validation checks (no Panda3D dependencies).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from passages_tool.editor.arch_utils import arch_view_angle
from passages_tool.editor.level import (
    Level,
    PolylineType,
    _texture_intervals_overlap,
    interval_edge_indices,
    wall_edge_index_pairs,
)


@dataclass
class ValidationWarning:
    kind: str
    target_id: str
    message: str
    v_from: int = -1
    v_to: int = -1
    angle_deg: float = 0.0

    @property
    def arch_id(self) -> str:
        """Polyline id to highlight, or empty for level-meta issues."""
        return self.target_id


def validate_textures(level: Level) -> list[ValidationWarning]:
    """
    Warn about assignable surfaces with no texture assigned — these render
    transparent. Checks every Wall edge (via its texture_intervals) plus the
    level floor and ceiling.

    Floor/ceiling warnings have empty ``target_id`` (level meta, not a polyline).
    """
    warnings: list[ValidationWarning] = []

    # ── Walls: every edge must be covered by an interval with a real texture ──
    for pl in level.walls():
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
                        kind="interval_overlap",
                        target_id=pl.id,
                        v_from=a.from_vertex,
                        v_to=a.to_vertex,
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
                    kind="untextured_wall",
                    target_id=pl.id,
                    v_from=uncovered[0],
                    v_to=min(uncovered[0] + 1, n - 1),
                    message=msg,
                )
            )

    # ── Floor / ceiling (level meta) ─────────────────────────────────────────
    if not level.meta.floor_texture:
        warnings.append(ValidationWarning(
            kind="missing_floor",
            target_id="",
            message="Floor has no texture assigned (Level Properties > floor) — it will render transparent.",
        ))
    if not level.meta.ceiling_texture:
        warnings.append(ValidationWarning(
            kind="missing_ceiling",
            target_id="",
            message="Ceiling has no texture assigned (Level Properties > ceiling) — it will render transparent.",
        ))

    return warnings


def validate_structure(level: Level) -> list[ValidationWarning]:
    """Warn about document-level issues.

    Multiple EyePaths are valid. Bake, preview, and the minigame merge them
    with a global vertex offset so the first path's keys stay ``v0000_to_v0001``.
    """
    del level
    return []


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

    fog_end = level.meta.fog_end

    for v_from, v_to, p_from, p_to in level.iter_eyepath_directed_edges():

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

            ang = arch_view_angle(arch.orientation, (vx, vy))
            if ang is None:
                continue

            # to_plane_deg: 90 = face-on, 0 = edge-on
            angle_deg = ang.to_plane_deg
            if angle_deg < threshold_deg:
                msg = (
                    f"Arch {arch.id[:8]}... is edge-on (view angle {angle_deg:.1f}° < {threshold_deg}°) "
                    f"when looking from vertex {v_from} to {v_to}."
                )
                warnings.append(
                    ValidationWarning(
                        kind="arch_edge_on",
                        target_id=arch.id,
                        v_from=v_from,
                        v_to=v_to,
                        angle_deg=angle_deg,
                        message=msg,
                    )
                )

    return warnings
