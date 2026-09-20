"""
renderer/manifest.py
────────────────────
Builds, saves, and inspects the render manifest JSON for a level.

Manifest shape (version 2 — see design_docs/passages_anchor_visibility_bake_06JUL26.md):

    {
      "version": 2,
      "edges": {                       # one entry per directed EyePath edge
        "v0000_to_v0001": {
          "image_path", "midpoint_image_path", "eyepoint_xyz", "facing_xyz",
          "rendered", "flicker", "exit"
        }, ...
      },
      "eyepoints": {                   # one entry per EyePath vertex
        "v0000": {
          "xyz": [x, y, eye_height],
          "yaw_strip": "yaw_v0000.png",  # optional; omit → client still-crossfade
          "visible_anchors": {         # occlusion candidates (view-independent)
            "<anchor_id>": {
              "world_xyz": [ax, ay, z_offset],
              "radius", "height", "max_distance",
              "occ_coverage",          # baked fraction of extent unoccluded
              "distance"               # eye→anchor planar distance
            }, ...
          }
        }, ...
      }
    }

Occlusion is baked here (view-independent, per eyepoint) via CPU ray-vs-geometry
with arch texture-alpha sampling (renderer/occluder.py) + extent coverage
sampling (renderer/occlusion.py). The FOV/frustum cull and screen projection are
deferred to the runtime, which combines occ_coverage with its own frustum
coverage against the live look-at.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from passages_tool.editor.level import Level
from passages_tool.renderer.occluder import build_occluders
from passages_tool.renderer.occlusion import sample_grid_points, occlusion_coverage
from passages_tool.renderer.yaw_strip import yaw_strip_filename

MANIFEST_VERSION = 2

# Extent sample-grid + coverage parameters (§4.1).
_GRID_WIDE = 3
_GRID_TALL = 4
_SAMPLE_BIAS = 0.05
_COVERAGE_FLOOR = 0.1     # drop anchors below this baked coverage (runtime T is higher)


def build_manifest(
    level: Level,
    output_dir: Optional[Path] = None,
    texture_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Build the render manifest (version 2) for the level.

    `edges` lists both directions of each EyePath edge with camera/target
    coordinates (and whether the image exists in `output_dir`). `eyepoints`
    lists, per vertex, the anchors that are unoccluded enough to be candidates
    for display, with their baked occlusion coverage.
    """
    manifest: dict[str, Any] = {
        "version": MANIFEST_VERSION,
        "edges": {},
        "eyepoints": {},
    }
    eye_height = level.meta.eye_height

    directed = list(level.iter_eyepath_directed_edges())
    if not directed and not any(pl.vertices for pl in level.eyepaths()):
        return manifest

    for v_from, v_to, p_from, p_to in directed:
        key = f"v{v_from:04d}_to_v{v_to:04d}"

        image_name = f"render_{key}.png"
        rendered = False
        midpoint_image_path = None
        if output_dir is not None:
            rendered = (Path(output_dir) / image_name).is_file()
            lo, hi = (v_from, v_to) if v_from <= v_to else (v_to, v_from)
            mid_image_name = f"mid_v{lo:04d}_to_v{hi:04d}.png"
            if (Path(output_dir) / mid_image_name).is_file():
                midpoint_image_path = mid_image_name

        manifest["edges"][key] = {
            "image_path": image_name,
            "midpoint_image_path": midpoint_image_path,
            "eyepoint_xyz": [p_from[0], p_from[1], eye_height],
            "facing_xyz": [p_to[0], p_to[1], eye_height],
            "rendered": rendered,
            "flicker": None,
            "exit": None,
        }

    # ── eyepoints: baked occlusion coverage per anchor (view-independent) ──────
    occluders = build_occluders(level, texture_dir)
    anchors = [pl for pl in level.anchors() if pl.vertices]
    fog_end = level.meta.fog_end

    global_i = 0
    for path in level.eyepaths():
        for vpos in path.vertices:
            i = global_i
            global_i += 1
            vid = f"v{i:04d}"
            eye = (vpos[0], vpos[1], eye_height)
            nearest = lambda p, _eye=eye: occluders.nearest_occluder_dist(_eye, p)
            visible: dict[str, Any] = {}

            for anchor in anchors:
                ax, ay = anchor.vertices[0]
                dist = ((ax - vpos[0]) ** 2 + (ay - vpos[1]) ** 2) ** 0.5
                max_dist = min(anchor.max_distance, fog_end)
                if dist > max_dist or dist < 0.1:
                    continue

                grid = sample_grid_points(
                    eye, (ax, ay), anchor.z_offset, anchor.radius, anchor.height,
                    n_wide=_GRID_WIDE, n_tall=_GRID_TALL,
                )
                cov = occlusion_coverage(eye, grid, nearest, bias=_SAMPLE_BIAS)
                if cov < _COVERAGE_FLOOR:
                    continue

                visible[anchor.id] = {
                    "world_xyz": [round(ax, 4), round(ay, 4), round(anchor.z_offset, 4)],
                    "radius": round(anchor.radius, 4),
                    "height": round(anchor.height, 4),
                    "max_distance": round(anchor.max_distance, 4),
                    "occ_coverage": round(cov, 3),
                    "distance": round(dist, 3),
                }

            rec: dict[str, Any] = {
                "xyz": [vpos[0], vpos[1], eye_height],
                "visible_anchors": visible,
            }
            # Optional: present only when the baker wrote a strip. Old manifests
            # and clients omit this key and keep the still-to-still crossfade.
            if output_dir is not None:
                yaw_name = yaw_strip_filename(i)
                if (Path(output_dir) / yaw_name).is_file():
                    rec["yaw_strip"] = yaw_name
            manifest["eyepoints"][vid] = rec

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
_YAW_PATTERN = re.compile(r"^yaw_v(\d{4})\.(png|jpg|jpeg|ktx2)$")


def find_stale_images(manifest: dict[str, Any], output_dir: Path) -> list[Path]:
    """Find any image files in output_dir that are not defined in the manifest."""
    p = Path(output_dir)
    if not p.is_dir():
        return []

    edges = manifest.get("edges", {})
    yaw_needed: set[str] = set()
    for rec in (manifest.get("eyepoints") or {}).values():
        if isinstance(rec, dict) and rec.get("yaw_strip"):
            yaw_needed.add(Path(str(rec["yaw_strip"])).name)
    stale: list[Path] = []
    for file_path in p.iterdir():
        if not file_path.is_file():
            continue
        match = _IMAGE_PATTERN.match(file_path.name)
        if match:
            v_from = int(match.group(1))
            v_to = int(match.group(2))
            key = f"v{v_from:04d}_to_v{v_to:04d}"
            if key not in edges:
                stale.append(file_path)
            continue
        # Only garbage-collect yaw strips when the manifest opted into them.
        # Old bakes without the key must not delete leftover yaw_*.png.
        yaw_m = _YAW_PATTERN.match(file_path.name)
        if yaw_m and yaw_needed and file_path.name not in yaw_needed:
            stale.append(file_path)
    return stale


def find_missing_images(manifest: dict[str, Any], output_dir: Path) -> list[str]:
    """Find any edge keys in the manifest that do not have matching image files on disk."""
    p = Path(output_dir)
    missing: list[str] = []

    for key in manifest.get("edges", {}):
        png_path = p / f"render_{key}.png"
        jpg_path = p / f"render_{key}.jpg"
        if not png_path.is_file() and not jpg_path.is_file():
            missing.append(key)

    return missing
