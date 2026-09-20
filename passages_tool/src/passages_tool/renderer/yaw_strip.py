"""Cylindrical yaw-strip helpers for turn slew (Feature 11).

Four 90° cube faces unwrapped L→R at headings 0°, 90°, 180°, 270°
(atan2 space, 0 = +X). Pixel 0 is the left edge of the first face (yaw −45°).
The hi-res `render_vXXXX_to_vYYYY` stills are unchanged; this strip is extra.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image

# Default still is 1024×576; spec sweet-spot ~2048×341 (~0.5× px/deg of the still).
_STRIP_HEIGHT_REF = 341
_STILL_HEIGHT_REF = 576
FACE_HFOV_DEG = 90.0
YAW_ORIGIN_DEG = -45.0  # yaw at strip pixel x=0
FACE_YAWS_DEG = (0.0, 90.0, 180.0, 270.0)


def yaw_strip_face_size(
    render_width: int, render_height: int, fov_v_deg: float
) -> tuple[int, int]:
    """Per-face pixel size: 90° HFOV × level VFOV, height scaled to ~341 at 576."""
    face_h = max(1, round(render_height * _STRIP_HEIGHT_REF / _STILL_HEIGHT_REF))
    aspect = math.tan(math.radians(FACE_HFOV_DEG * 0.5)) / math.tan(
        math.radians(max(fov_v_deg, 1e-3) * 0.5)
    )
    face_w = max(1, round(face_h * aspect))
    return face_w, face_h


def yaw_strip_size(
    render_width: int, render_height: int, fov_v_deg: float
) -> tuple[int, int]:
    fw, fh = yaw_strip_face_size(render_width, render_height, fov_v_deg)
    return fw * 4, fh


def look_at_from_yaw(
    pos: tuple[float, float], yaw_deg: float, dist: float = 1.0
) -> tuple[float, float]:
    rad = math.radians(yaw_deg)
    return (pos[0] + dist * math.cos(rad), pos[1] + dist * math.sin(rad))


def stitch_cube_faces(faces: list[Image.Image]) -> Image.Image:
    if len(faces) != 4:
        raise ValueError(f"expected 4 cube faces, got {len(faces)}")
    w, h = faces[0].size
    out = Image.new("RGB", (w * 4, h))
    for i, im in enumerate(faces):
        if im.size != (w, h):
            im = im.resize((w, h), Image.Resampling.BILINEAR)
        out.paste(im.convert("RGB"), (i * w, 0))
    return out


def yaw_strip_filename(vertex_index: int) -> str:
    return f"yaw_v{vertex_index:04d}.png"


def bake_yaw_strips(
    renderer,
    output_dir: Path,
    width: int,
    height: int,
    force: bool = False,
) -> tuple[int, int, int]:
    """Render + stitch one strip per EyePath vertex.

    Returns (rendered, skipped, failed). Failures are logged by the caller;
    missing strips must not fail the still bake.
    """
    from passages_tool.log import get_logger

    log = get_logger("renderer.yaw_strip")
    level = renderer.level
    fov_v = level.meta.fov_v
    face_w, face_h = yaw_strip_face_size(width, height, fov_v)
    rendered = skipped = failed = 0
    tmp = output_dir / "_yaw_faces"
    tmp.mkdir(parents=True, exist_ok=True)

    n = 0
    for path in level.eyepaths():
        for local_i, pos in enumerate(path.vertices):
            gi = n + local_i
            dest = output_dir / yaw_strip_filename(gi)
            if dest.is_file() and not force:
                skipped += 1
                continue
            faces: list[Image.Image] = []
            ok = True
            for fi, yaw in enumerate(FACE_YAWS_DEG):
                face_path = tmp / f"v{gi:04d}_f{fi}.png"
                look = look_at_from_yaw(pos, yaw)
                if not renderer._render_camera(
                    pos, look, face_path, face_w, face_h, f"yaw_face_{fi}", fov_h=FACE_HFOV_DEG
                ):
                    ok = False
                    break
                try:
                    faces.append(Image.open(face_path).copy())
                except OSError:
                    ok = False
                    break
            if not ok or len(faces) != 4:
                failed += 1
                log.error("Yaw strip failed for v%04d", gi)
                continue
            stitch_cube_faces(faces).save(dest, "PNG")
            for im in faces:
                im.close()
            rendered += 1
        n += len(path.vertices)

    # Face temps are bake-private.
    try:
        for p in tmp.glob("*.png"):
            p.unlink()
        tmp.rmdir()
    except OSError:
        pass
    return rendered, skipped, failed
