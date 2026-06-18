"""
renderer/manifest.py
────────────────────
Builds, saves, and inspects the render manifest JSON for a level.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from passages_tool.editor.level import Level, PolylineType


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
        if output_dir is not None:
            rendered = (Path(output_dir) / image_name).is_file()

        manifest[key] = {
            "image_path": image_name,
            "eyepoint_xyz": [p_from[0], p_from[1], eye_height],
            "facing_xyz": [p_to[0], p_to[1], eye_height],
            "rendered": rendered,
            "flicker": None,  # Can be populated by game editor/logic later
            "exit": None,     # Can be populated by game editor/logic later
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


# Regex to match output files like render_v0000_to_v0001.png or .jpg
_IMAGE_PATTERN = re.compile(r"^render_v(\d{4})_to_v(\d{4})\.(png|jpg|jpeg)$")


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
