"""S3: seeded overlay stamps on unique wall maps.

Density 0 is a no-op (S2 golden). Placement is hashed from style id, wall id,
edge index, and ``LevelMeta.overlay_seed`` (else the pack's ``overlays.seed``).
Optional RGBA sprites: ``<texture_dir>/overlays/<kind>.png``.
"""
from __future__ import annotations

import hashlib
import random
from pathlib import Path
from typing import Optional

from PIL import Image

from passages_tool.textures.style import StylePack

# Stamps per m² at density 1. Uncommon even at 1.0.
_KIND_RATE = {
    "wetness": 0.22,
    "moss": 0.16,
    "graffiti": 0.08,
}
# radius_m range, z_m range as fractions of wall height (0 = floor).
_KIND_SHAPE = {
    "wetness": ((0.40, 1.10), (0.00, 0.45), (25, 45, 75), 0.42),
    "moss": ((0.25, 0.70), (0.00, 0.38), (35, 80, 30), 0.40),
    "graffiti": ((0.28, 0.75), (0.22, 0.72), (50, 40, 35), 0.50),
}


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def effective_overlay_seed(pack: StylePack, overlay_seed: Optional[int]) -> int:
    if overlay_seed is not None:
        return int(overlay_seed)
    return int(pack.overlays.seed)


def overlay_rng(*parts: object) -> random.Random:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"\0")
    return random.Random(int.from_bytes(h.digest()[:8], "little"))


def stamp_count(density: float, area_m2: float, rate: float, rng: random.Random) -> int:
    d = clamp01(density)
    if d <= 0.0 or area_m2 <= 0.0 or rate <= 0.0:
        return 0
    expected = d * area_m2 * rate
    n = int(expected)
    if rng.random() < (expected - n):
        n += 1
    return n


def _blend(src: tuple[int, int, int], color: tuple[int, int, int], a: float) -> tuple[int, int, int]:
    a = clamp01(a)
    if a <= 0.0:
        return src
    ia = 1.0 - a
    return (
        int(src[0] * ia + color[0] * a + 0.5),
        int(src[1] * ia + color[1] * a + 0.5),
        int(src[2] * ia + color[2] * a + 0.5),
    )


def _stamp_ellipse(
    pix,
    w: int,
    h: int,
    cx: int,
    cy: int,
    rx: int,
    ry: int,
    color: tuple[int, int, int],
    strength: float,
) -> None:
    rx = max(1, rx)
    ry = max(1, ry)
    x0, x1 = max(0, cx - rx), min(w - 1, cx + rx)
    y0, y1 = max(0, cy - ry), min(h - 1, cy + ry)
    rx2, ry2 = float(rx * rx), float(ry * ry)
    for y in range(y0, y1 + 1):
        dy = y - cy
        for x in range(x0, x1 + 1):
            dx = x - cx
            d = (dx * dx) / rx2 + (dy * dy) / ry2
            if d >= 1.0:
                continue
            falloff = (1.0 - d) * (1.0 - d)
            pix[x, y] = _blend(pix[x, y], color, strength * falloff)


def _load_mask(texture_dir: Path, kind: str) -> Optional[Image.Image]:
    p = Path(texture_dir) / "overlays" / f"{kind}.png"
    if not p.is_file():
        return None
    try:
        return Image.open(p).convert("RGBA")
    except OSError:
        return None


def _stamp_mask(
    base: Image.Image,
    mask: Image.Image,
    cx: int,
    cy: int,
    rw: int,
    rh: int,
    strength: float,
) -> None:
    rw = max(1, rw)
    rh = max(1, rh)
    sprite = mask.resize((rw * 2, rh * 2), Image.Resampling.NEAREST)
    px = sprite.load()
    bp = base.load()
    w, h = base.size
    ox, oy = cx - rw, cy - rh
    sw, sh = sprite.size
    for y in range(sh):
        by = oy + y
        if by < 0 or by >= h:
            continue
        for x in range(sw):
            bx = ox + x
            if bx < 0 or bx >= w:
                continue
            r, g, b, a = px[x, y]
            if a <= 0:
                continue
            bp[bx, by] = _blend(bp[bx, by], (r, g, b), (a / 255.0) * strength)


def apply_overlays(
    image: Image.Image,
    pack: StylePack,
    length_m: float,
    height_m: float,
    ppm: float,
    *,
    wall_id: str,
    edge_idx: int,
    overlay_seed: Optional[int] = None,
    texture_dir: Optional[Path] = None,
) -> Image.Image:
    """Stamp in-place and return ``image``. No-op when all densities are 0."""
    ov = pack.overlays
    dens = {
        "wetness": clamp01(ov.wetness),
        "moss": clamp01(ov.moss),
        "graffiti": clamp01(ov.graffiti),
    }
    if dens["wetness"] <= 0.0 and dens["moss"] <= 0.0 and dens["graffiti"] <= 0.0:
        return image

    seed = effective_overlay_seed(pack, overlay_seed)
    area = max(0.0, float(length_m) * float(height_m))
    pix = image.load()
    w, h = image.size
    ppm = float(ppm)

    for kind, density in dens.items():
        if density <= 0.0:
            continue
        rng = overlay_rng(pack.id, wall_id, edge_idx, seed, kind)
        n = stamp_count(density, area, _KIND_RATE[kind], rng)
        if n <= 0:
            continue
        (rmin, rmax), (z0f, z1f), color, strength = _KIND_SHAPE[kind]
        mask = _load_mask(texture_dir, kind) if texture_dir is not None else None
        z0 = z0f * height_m
        z1 = max(z0 + 0.05, z1f * height_m)
        for _ in range(n):
            rad = rmin + rng.random() * (rmax - rmin)
            s_m = rad + rng.random() * max(0.01, length_m - 2.0 * rad)
            z_m = z0 + rng.random() * (z1 - z0)
            cx = int((s_m + 0.0) * ppm)
            cy = (h - 1) - int(z_m * ppm)
            rx = max(1, int(rad * ppm))
            ry = max(1, int(rad * 0.72 * ppm))
            if mask is not None:
                _stamp_mask(image, mask, cx, cy, rx, ry, strength)
            else:
                _stamp_ellipse(pix, w, h, cx, cy, rx, ry, color, strength)
    return image
