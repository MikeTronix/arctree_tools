"""S2: compose unique wall-edge maps from style bands (CPU, meters).

U = distance along the edge, V = world Z. Interval PNGs are not composed
here — the wall builder uses those as overrides. Cap 4096 px on U: skip
(no silent resize).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image

from passages_tool.config import DEFAULT_PIXELS_PER_METER
from passages_tool.textures.style import (
    StyleBand,
    StylePack,
    preset_dir,
)

STYLE_CACHE_DIR = "_style_cache"
COMPOSE_U_MAX = 4096
_UNCOVERED = (128, 128, 128)


def compose_size_px(length_m: float, height_m: float, ppm: float) -> tuple[int, int]:
    w = max(1, int(round(float(length_m) * float(ppm))))
    h = max(1, int(round(float(height_m) * float(ppm))))
    return w, h


def default_tile_meters(image: Image.Image) -> tuple[float, float]:
    """Meters per one repeat when the band omits tile_meters (512² → 2 m)."""
    ppm = float(DEFAULT_PIXELS_PER_METER)
    return image.width / ppm, image.height / ppm


def band_at_z(bands: tuple[StyleBand, ...], z_m: float) -> Optional[StyleBand]:
    if not bands:
        return None
    for b in bands:
        if b.z0 <= z_m < b.z1:
            return b
    last = bands[-1]
    if last.z0 <= z_m <= last.z1:
        return last
    return None


def sample_wrap(im: Image.Image, u: float, v: float) -> tuple[int, int, int]:
    """Nearest sample. u/v in repeats; v=0 is the image bottom (floor)."""
    w, h = im.size
    uu = u % 1.0
    vv = v % 1.0
    ix = min(w - 1, max(0, int(uu * w)))
    iy = min(h - 1, max(0, int((1.0 - vv) * h)))
    px = im.getpixel((ix, iy))
    if isinstance(px, int):
        return (px, px, px)
    return (int(px[0]), int(px[1]), int(px[2]))


def load_preset_diffuse(texture_dir: Path, preset_id: str) -> Optional[Image.Image]:
    d = preset_dir(texture_dir, preset_id)
    if d is None:
        return None
    p = d / "diffuse.png"
    if not p.is_file():
        return None
    try:
        return Image.open(p).convert("RGB")
    except OSError:
        return None


def compose_edge_diffuse(
    pack: StylePack,
    texture_dir: Path,
    length_m: float,
    height_m: float,
    ppm: float,
    *,
    preset_images: Optional[dict[str, Image.Image]] = None,
) -> Optional[Image.Image]:
    """Rasterize one wall edge. None if U would exceed COMPOSE_U_MAX."""
    if length_m <= 1e-6 or height_m <= 1e-6 or ppm <= 1e-6:
        return None
    w, h = compose_size_px(length_m, height_m, ppm)
    if w > COMPOSE_U_MAX:
        return None

    cache = preset_images if preset_images is not None else {}
    out = Image.new("RGB", (w, h), _UNCOVERED)
    pix = out.load()
    bands = pack.bands
    for y in range(h):
        # y=0 is PNG top = ceiling
        z_m = ((h - 1 - y) + 0.5) / ppm
        band = band_at_z(bands, z_m)
        src = None
        tile_u = tile_v = 1.0
        if band is not None:
            src = cache.get(band.preset)
            if src is None:
                loaded = load_preset_diffuse(texture_dir, band.preset)
                if loaded is not None:
                    cache[band.preset] = loaded
                    src = loaded
            if src is not None:
                if band.tile_meters:
                    tile_u, tile_v = band.tile_meters
                else:
                    tile_u, tile_v = default_tile_meters(src)
        for x in range(w):
            if src is None:
                continue
            s_m = (x + 0.5) / ppm
            pix[x, y] = sample_wrap(src, s_m / tile_u, z_m / tile_v)
    return out


def cache_relpath(style_id: str, wall_id: str, edge_idx: int) -> str:
    sid = "".join(c if c.isalnum() or c in "-_" else "_" for c in style_id) or "style"
    wid = "".join(c if c.isalnum() or c in "-_" else "_" for c in wall_id) or "wall"
    return f"{STYLE_CACHE_DIR}/{sid}/wall_{wid}_e{edge_idx}.png"


def write_edge_diffuse(
    pack: StylePack,
    texture_dir: Path,
    wall_id: str,
    edge_idx: int,
    length_m: float,
    height_m: float,
    ppm: float,
    *,
    preset_images: Optional[dict[str, Image.Image]] = None,
) -> Optional[str]:
    """Write the unique map under ``texture_dir/_style_cache/``. Relative posix path."""
    img = compose_edge_diffuse(
        pack, texture_dir, length_m, height_m, ppm, preset_images=preset_images
    )
    if img is None:
        return None
    rel = cache_relpath(pack.id, wall_id, edge_idx)
    dest = Path(texture_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "PNG")
    return rel.replace("\\", "/")
