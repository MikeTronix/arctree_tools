"""
converter/wall_builder.py
─────────────────────────
Generates 3D wall mesh geometry (.egg) from level Wall polylines.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from PIL import Image
from panda3d.egg import EggGroup

from passages_tool.converter.egg_writer import EggContext
from passages_tool.editor.level import Level, Polyline, PolylineType, TextureInterval


def get_texture_size(
    texture_name: Optional[str], texture_dir: Optional[Path]
) -> tuple[int, int]:
    """Load texture dimensions from disk, defaulting to 512x512 if unavailable."""
    if not texture_name or not texture_dir:
        return 512, 512
    p = Path(texture_dir) / texture_name
    if p.is_file():
        try:
            with Image.open(p) as img:
                return img.size
        except Exception:
            pass
    return 512, 512


def build_wall_strips(
    level: Level, texture_dir: Optional[Path] = None
) -> list[EggGroup]:
    """
    Build 3D wall geometry groups for all Wall polylines in the level.
    Each Wall polyline yields an EggGroup containing its textured quads.
    """
    groups: list[EggGroup] = []
    wall_height = level.meta.wall_height
    ppm = level.meta.pixels_per_meter

    for pl in level.polylines.values():
        if pl.type != PolylineType.WALL or len(pl.vertices) < 2:
            continue

        n_verts = len(pl.vertices)
        # Egg group for this wall polyline
        group = EggGroup(f"wall_{pl.id}")
        ctx = EggContext(f"wall_{pl.id}")

        # Add vertex pool to the group
        group.add_child(ctx.vpool)

        # Fallback: if no texture intervals exist, create a default one covering the entire wall
        intervals = pl.texture_intervals
        if not intervals:
            intervals = [
                TextureInterval(
                    from_vertex=0, to_vertex=n_verts - 1, texture=None
                )
            ]

        has_polys = False

        # For each texture interval, compile the list of edges it covers
        # An interval covers edges from from_vertex to to_vertex.
        # If the polyline is closed, we also assign the closing edge (N-1 -> 0)
        # to the last interval that reaches vertex N-1.
        for iv_idx, iv in enumerate(intervals):
            tex_w, tex_h = get_texture_size(iv.texture, texture_dir)
            egg_tex = ctx.get_or_create_texture(iv.texture) if iv.texture else None

            # Collect edges for this interval
            edges: list[tuple[int, int]] = []
            for i in range(iv.from_vertex, iv.to_vertex):
                if i < n_verts - 1:
                    edges.append((i, i + 1))

            # If this is the last interval and the wall is closed, it covers the closing edge
            if pl.closed and iv.to_vertex == n_verts - 1:
                edges.append((n_verts - 1, 0))

            accumulated_len = 0.0
            for v_from, v_to in edges:
                p1 = pl.vertices[v_from]
                p2 = pl.vertices[v_to]

                # Internal coordinates are (x, z) representing horizontal (X, Y) layout.
                # Under Z-up coordinate system: X=x, Y=z, Z=height.
                x1, y1 = p1[0], p1[1]
                x2, y2 = p2[0], p2[1]

                dx = x2 - x1
                dy = y2 - y1
                segment_len = math.sqrt(dx * dx + dy * dy)
                if segment_len < 1e-6:
                    continue

                # Normalized tangent
                tx = dx / segment_len
                ty = dy / segment_len

                # Inward normal (right-hand side of tangent: (ty, -tx))
                nx = ty
                ny = -tx
                nz = 0.0

                # Horizontal UV span
                u_start = (accumulated_len * ppm + iv.x_offset) / tex_w
                u_end = ((accumulated_len + segment_len) * ppm + iv.x_offset) / tex_w

                # Vertical UV span (V=0 at floor, V_top at ceiling)
                v_top = (wall_height * ppm) / tex_h

                # Build 3D quad vertices
                # BL: bottom-left (at p1, z=0)
                bl = ctx.add_vertex(x1, y1, 0.0, u_start, 0.0, (nx, ny, nz))
                # BR: bottom-right (at p2, z=0)
                br = ctx.add_vertex(x2, y2, 0.0, u_end, 0.0, (nx, ny, nz))
                # TR: top-right (at p2, z=wall_height)
                tr = ctx.add_vertex(x2, y2, wall_height, u_end, v_top, (nx, ny, nz))
                # TL: top-left (at p1, z=wall_height)
                tl = ctx.add_vertex(x1, y1, wall_height, u_start, v_top, (nx, ny, nz))

                # Create polygon and add to group
                poly = ctx.add_polygon([bl, br, tr, tl], egg_tex)
                group.add_child(poly)
                has_polys = True

                accumulated_len += segment_len

        # If any polygons were created, keep the group
        if has_polys:
            groups.append(group)

    return groups
