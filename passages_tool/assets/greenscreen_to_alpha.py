"""
assets/greenscreen_to_alpha.py
────────────────────────────────
Convert green-screen PNGs (areas filled with #00FF00) to true RGBA PNGs
with those areas made fully transparent.

Usage (from the passages_tool root):
    .venv\\Scripts\\python assets\\greenscreen_to_alpha.py [file_or_dir ...]

If no arguments are given, processes all *_gs.png files in the current
directory and its subdirectories.

A small colour tolerance is used (default: 40 per channel) to catch
near-green fringing that AI generators produce at edges.  If you need
sharper keying (less fringe bleed), lower the tolerance; if too much
green remains, raise it.  The tolerance applies to:
    G > 200  AND  R < (G - tolerance)  AND  B < (G - tolerance)
which is the standard luma-key heuristic for #00FF00 green screen.

Output files are written alongside the input with '_alpha' appended before
the extension, e.g.  arch_gothic_gs.png → arch_gothic_alpha.png
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image


def key_green_screen(
    src: Path,
    dst: Path,
    tolerance: int = 40,
) -> tuple[int, int]:
    """
    Convert green-screen pixels to transparent.

    Returns (total_pixels, keyed_pixels).
    """
    img = Image.open(src).convert("RGBA")
    arr = np.array(img, dtype=np.uint8)

    r, g, b, a = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]

    # Green-screen mask: G is bright, R and B are significantly lower
    mask = (g > 200) & (r.astype(int) < g.astype(int) - tolerance) & \
                       (b.astype(int) < g.astype(int) - tolerance)

    arr[mask, 3] = 0   # set alpha to 0 (transparent)

    Image.fromarray(arr, "RGBA").save(dst, format="PNG")
    return int(arr.shape[0] * arr.shape[1]), int(mask.sum())


def process(paths: list[Path], tolerance: int = 40) -> None:
    for src in paths:
        if not src.suffix.lower() == ".png":
            continue
        stem = src.stem
        dst  = src.with_name(stem.replace("_gs", "") + "_alpha.png")
        total, keyed = key_green_screen(src, dst, tolerance)
        pct = 100 * keyed / total if total else 0
        print(f"  {src.name} -> {dst.name}  ({pct:.1f}% keyed)")


def main() -> None:
    if len(sys.argv) > 1:
        paths: list[Path] = []
        for arg in sys.argv[1:]:
            p = Path(arg)
            if p.is_dir():
                paths.extend(p.rglob("*_gs.png"))
            else:
                paths.append(p)
    else:
        paths = list(Path(".").rglob("*_gs.png"))

    if not paths:
        print("No *_gs.png files found.")
        return

    print(f"Keying {len(paths)} file(s) with green-screen removal...")
    process(paths)
    print("Done.")


if __name__ == "__main__":
    main()
