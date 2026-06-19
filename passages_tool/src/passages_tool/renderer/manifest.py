"""
renderer/manifest.py
────────────────────
Builds, saves, and inspects the render manifest JSON for a level.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Optional

from passages_tool.editor.level import Level, PolylineType


def ccw(A: tuple[float, float], B: tuple[float, float], C: tuple[float, float]) -> bool:
    return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])


def segments_intersect(A: tuple[float, float], B: tuple[float, float], C: tuple[float, float], D: tuple[float, float]) -> bool:
    return (ccw(A, C, D) != ccw(B, C, D)) and (ccw(A, B, C) != ccw(A, B, D))


def build_manifest(level: Level, output_dir: Optional[Path] = None) -> dict[str, Any]:
    """
    Build the render manifest dictionary for the level.
    Lists all directed edges in the EyePath with camera positions and target coordinates.
    Checks if the corresponding image exists in output_dir.
    """
    manifest: dict[str, Any] = {}
    eye_height = level.meta.eye_height

    # Find the EyePath polyline
    eyepath_pl = None
    for pl in level.polylines.values():
        if pl.type == PolylineType.EYEPATH:
            eyepath_pl = pl
            break

    if not eyepath_pl or not eyepath_pl.vertices:
        return manifest

    # For each directed edge, create an entry
    for v_from, v_to in eyepath_pl.edges:
        if v_from >= len(eyepath_pl.vertices) or v_to >= len(eyepath_pl.vertices):
            continue

        p_from = eyepath_pl.vertices[v_from]
        p_to = eyepath_pl.vertices[v_to]

        # Edge key format: v0000_to_v0001
        key = f"v{v_from:04d}_to_v{v_to:04d}"
        
        # Determine if image exists
        image_name = f"render_{key}.png"
        rendered = False
        midpoint_image_path = None
        if output_dir is not None:
            rendered = (Path(output_dir) / image_name).is_file()
            mid_image_name = f"mid_{key}.png"
            if (Path(output_dir) / mid_image_name).is_file():
                midpoint_image_path = mid_image_name

        # Calculate visible anchors
        visible_anchors = {}
        for anchor in level.polylines.values():
            if anchor.type != PolylineType.ANCHOR:
                continue
            if not anchor.vertices:
                continue

            ax, ay = anchor.vertices[0]
            dx_rel = ax - p_from[0]
            dy_rel = ay - p_from[1]
            dist = math.hypot(dx_rel, dy_rel)

            max_dist = min(anchor.max_distance, level.meta.fog_end)
            if dist > max_dist or dist < 0.1:
                continue

            # View direction vector
            vx = p_to[0] - p_from[0]
            vy = p_to[1] - p_from[1]
            v_len = math.hypot(vx, vy)
            if v_len == 0.0:
                continue
            vx /= v_len
            vy /= v_len

            # Relative direction to anchor
            ux = dx_rel / dist
            uy = dy_rel / dist

            # Angle check
            cos_theta = vx * ux + vy * uy
            cos_theta = min(1.0, max(-1.0, cos_theta))
            theta_rad = math.acos(cos_theta)

            fov_limit = anchor.fov_limit if anchor.fov_limit is not None else (level.meta.fov_h * 0.5)
            if math.degrees(theta_rad) > fov_limit:
                continue

            # Line-of-sight check (segment intersection)
            p_start = (p_from[0] + 0.01 * dx_rel, p_from[1] + 0.01 * dy_rel)
            p_end = (ax - 0.01 * dx_rel, ay - 0.01 * dy_rel)

            blocked = False
            for pl in level.polylines.values():
                if pl.type == PolylineType.WALL:
                    for i in range(len(pl.vertices) - 1):
                        w1 = pl.vertices[i]
                        w2 = pl.vertices[i+1]
                        if segments_intersect(p_start, p_end, w1, w2):
                            blocked = True
                            break
                    if blocked:
                        break
                    if pl.closed and len(pl.vertices) >= 3:
                        w1 = pl.vertices[-1]
                        w2 = pl.vertices[0]
                        if segments_intersect(p_start, p_end, w1, w2):
                            blocked = True
                            break
                elif pl.type == PolylineType.ARCH and pl.transparency == "none":
                    if pl.vertices:
                        arch_pos = pl.vertices[0]
                        try:
                            if pl.orientation != "billboard":
                                half_w = pl.width * 0.5
                                ang = math.radians(float(pl.orientation) + 90.0)
                                adx = math.cos(ang) * half_w
                                adz = math.sin(ang) * half_w
                                a1 = (arch_pos[0] - adx, arch_pos[1] - adz)
                                a2 = (arch_pos[0] + adx, arch_pos[1] + adz)
                                if segments_intersect(p_start, p_end, a1, a2):
                                    blocked = True
                                    break
                        except ValueError:
                            pass

            if blocked:
                continue

            # Projection math
            fx, fy = vx, vy
            rx, ry = fy, -fx

            cam_z = level.meta.eye_height
            anchor_z = anchor.z_offset
            dz_rel = anchor_z - cam_z

            depth = dx_rel * fx + dy_rel * fy
            x_cam = dx_rel * rx + dy_rel * ry
            y_cam = dz_rel

            if depth < 0.1:
                continue

            w_half = math.tan(math.radians(level.meta.fov_h) * 0.5)
            h_half = math.tan(math.radians(level.meta.fov_v) * 0.5)

            screen_x = x_cam / (depth * w_half)
            screen_y = y_cam / (depth * h_half)
            scale = 1.0 / depth

            visible_anchors[anchor.id] = {
                "screen_x": round(screen_x, 4),
                "screen_y": round(screen_y, 4),
                "scale": round(scale, 4),
                "distance": round(dist, 3)
            }

        manifest[key] = {
            "image_path": image_name,
            "midpoint_image_path": midpoint_image_path,
            "eyepoint_xyz": [p_from[0], p_from[1], eye_height],
            "facing_xyz": [p_to[0], p_to[1], eye_height],
            "rendered": rendered,
            "flicker": None,
            "exit": None,
            "visible_anchors": visible_anchors,
        }

    return manifest


def save_manifest(manifest: dict[str, Any], path: Path) -> None:
    """Save the manifest dictionary as formatted JSON."""
    Path(path).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def load_manifest(path: Path) -> dict[str, Any]:
    """Load the manifest dictionary from JSON."""
    p = Path(path)
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


# Regex to match output files like render_v0000_to_v0001.png, .jpg, or mid_v0000_to_v0001.ktx2
_IMAGE_PATTERN = re.compile(r"^(?:render|mid)_v(\d{4})_to_v(\d{4})\.(png|jpg|jpeg|ktx2)$")


def find_stale_images(manifest: dict[str, Any], output_dir: Path) -> list[Path]:
    """Find any image files in output_dir that are not defined in the manifest."""
    p = Path(output_dir)
    if not p.is_dir():
        return []

    stale: list[Path] = []
    for file_path in p.iterdir():
        if file_path.is_file():
            match = _IMAGE_PATTERN.match(file_path.name)
            if match:
                v_from = int(match.group(1))
                v_to = int(match.group(2))
                key = f"v{v_from:04d}_to_v{v_to:04d}"
                if key not in manifest:
                    stale.append(file_path)
    return stale


def find_missing_images(manifest: dict[str, Any], output_dir: Path) -> list[str]:
    """Find any edge keys in the manifest that do not have matching image files on disk."""
    p = Path(output_dir)
    missing: list[str] = []
    
    for key, info in manifest.items():
        image_name = info.get("image_path", f"render_{key}.png")
        # Check for both .png (editor render) and .jpg (shipping render)
        png_path = p / f"render_{key}.png"
        jpg_path = p / f"render_{key}.jpg"
        
        if not png_path.is_file() and not jpg_path.is_file():
            missing.append(key)
            
    return missing
