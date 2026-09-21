"""S5: POM-niche height dip on unique wall maps (CPU). Wall is not punched."""
from __future__ import annotations

from typing import Iterable

from PIL import Image

from passages_tool.converter.opening import WallHole


def apply_niche_dip(
    albedo: Image.Image,
    height: Image.Image,
    holes: Iterable[WallHole],
    length_m: float,
    height_m: float,
    ppm: float,
    *,
    darken: float = 0.82,
    floor: float = 0.08,
) -> None:
    """In-place: recess the height field and slightly darken albedo.

    Height 255 = wall surface, 0 = deepest. ``floor`` is the niche back
    (not fully empty, so POM still hits a surface).
    """
    w, h = albedo.size
    if w < 1 or h < 1 or ppm <= 1e-6 or height_m <= 1e-6:
        return
    ap = albedo.load()
    hp = height.load()
    darken = max(0.4, min(1.0, float(darken)))
    floor = max(0.0, min(1.0, float(floor)))
    for hole in holes:
        s0 = hole.t0 * length_m
        s1 = hole.t1 * length_m
        z0, z1 = hole.z0, hole.z1
        if s1 - s0 < 1e-4 or z1 - z0 < 1e-4:
            continue
        pad_s = max(0.04, 0.14 * (s1 - s0))
        pad_z = max(0.04, 0.14 * (z1 - z0))
        x0 = max(0, int(s0 * ppm))
        x1 = min(w - 1, int(s1 * ppm))
        y_top = h - 1 - int(z1 * ppm)
        y_bot = h - 1 - int(z0 * ppm)
        y0, y1 = max(0, min(y_top, y_bot)), min(h - 1, max(y_top, y_bot))
        for y in range(y0, y1 + 1):
            z_m = ((h - 1 - y) + 0.5) / ppm
            for x in range(x0, x1 + 1):
                s_m = (x + 0.5) / ppm
                ds = min(s_m - s0, s1 - s_m) / pad_s
                dz = min(z_m - z0, z1 - z_m) / pad_z
                edge = min(ds, dz)
                if edge <= 0.0:
                    continue
                t = min(1.0, edge)
                t = t * t * (3.0 - 2.0 * t)
                hval = int(255.0 * (1.0 - (1.0 - floor) * t) + 0.5)
                cur = hp[x, y]
                if isinstance(cur, tuple):
                    cur = cur[0]
                if hval < cur:
                    hp[x, y] = hval
                r, g, b = ap[x, y][:3]
                k = 1.0 - (1.0 - darken) * t
                ap[x, y] = (int(r * k + 0.5), int(g * k + 0.5), int(b * k + 0.5))
