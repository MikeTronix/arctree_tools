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
from passages_tool.editor.level import (
    Level,
    Polyline,
    PolylineType,
    TextureInterval,
    interval_edge_indices,
    wall_edge_index_pairs,
)
from passages_tool.converter.opening import (
    WallHole,
    collect_niche_spans,
    collect_opening_punches,
    leftover_patches,
)
from passages_tool.textures.style import StyleError, StylePack, load_level_style


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


def _try_style_pack(level: Level, texture_dir: Optional[Path]) -> Optional[StylePack]:
    if not level.meta.style or texture_dir is None:
        return None
    try:
        return load_level_style(Path(texture_dir), level.meta.style)
    except StyleError:
        return None


def _emit_quad(
    ctx: EggContext,
    group: EggGroup,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    z0: float,
    z1: float,
    nx: float,
    ny: float,
    u_start: float,
    u_end: float,
    v0: float,
    v1: float,
    egg_tex,
) -> None:
    nz = 0.0
    bl = ctx.add_vertex(x1, y1, z0, u_start, v0, (nx, ny, nz))
    br = ctx.add_vertex(x2, y2, z0, u_end, v0, (nx, ny, nz))
    tr = ctx.add_vertex(x2, y2, z1, u_end, v1, (nx, ny, nz))
    tl = ctx.add_vertex(x1, y1, z1, u_start, v1, (nx, ny, nz))
    group.add_child(ctx.add_polygon([bl, br, tr, tl], egg_tex))


def _emit_edge_patches(
    ctx: EggContext,
    group: EggGroup,
    ax: float,
    ay: float,
    bx: float,
    by: float,
    length_m: float,
    wall_height: float,
    nx: float,
    ny: float,
    holes: list[WallHole],
    egg_tex,
    *,
    unique_uv: bool,
    accum_m: float = 0.0,
    x_offset: float = 0.0,
    ppm: float = 256.0,
    tex_w: float = 512.0,
    tex_h: float = 512.0,
) -> bool:
    if length_m < 1e-6:
        return False
    patches = leftover_patches(length_m, wall_height, holes)
    if not patches:
        return False
    dx, dy = bx - ax, by - ay
    emitted = False
    for p in patches:
        t0, t1 = p.s0 / length_m, p.s1 / length_m
        x1 = ax + t0 * dx
        y1 = ay + t0 * dy
        x2 = ax + t1 * dx
        y2 = ay + t1 * dy
        if unique_uv:
            u0, u1 = t0, t1
            v0 = p.z0 / wall_height if wall_height > 1e-6 else 0.0
            v1 = p.z1 / wall_height if wall_height > 1e-6 else 1.0
        else:
            u0 = ((accum_m + p.s0) * ppm + x_offset) / tex_w
            u1 = ((accum_m + p.s1) * ppm + x_offset) / tex_w
            v0 = (p.z0 * ppm) / tex_h
            v1 = (p.z1 * ppm) / tex_h
        _emit_quad(
            ctx, group, x1, y1, x2, y2, p.z0, p.z1, nx, ny,
            u0, u1, v0, v1, egg_tex,
        )
        emitted = True
    return emitted


def build_wall_strips(
    level: Level, texture_dir: Optional[Path] = None
) -> list[EggGroup]:
    """
    Build 3D wall geometry groups for all Wall polylines in the level.
    Each Wall polyline yields an EggGroup containing its textured quads.

    With ``LevelMeta.style`` set, uncovered (or untextured) edges get a unique
    band-composed map in meters. An interval with a PNG is an override and
    keeps today's UV formula.
    """
    groups: list[EggGroup] = []
    wall_height = level.meta.wall_height
    ppm = level.meta.pixels_per_meter
    pack = _try_style_pack(level, texture_dir)
    preset_images: dict = {}
    punches = collect_opening_punches(level)
    niches = collect_niche_spans(level)

    for pl in level.polylines.values():
        if pl.type != PolylineType.WALL or len(pl.vertices) < 2:
            continue

        n_verts = len(pl.vertices)
        group = EggGroup(f"wall_{pl.id}")
        ctx = EggContext(f"wall_{pl.id}")
        group.add_child(ctx.vpool)

        if pack is not None:
            has_polys = _build_styled_wall(
                pl, group, ctx, pack, texture_dir, wall_height, ppm, preset_images,
                overlay_seed=level.meta.overlay_seed,
                punches=punches,
                niches=niches,
            )
        else:
            has_polys = _build_interval_wall(
                pl, group, ctx, n_verts, texture_dir, wall_height, ppm,
                punches=punches,
            )

        if has_polys:
            groups.append(group)

    return groups


def _build_interval_wall(
    pl,
    group: EggGroup,
    ctx: EggContext,
    n_verts: int,
    texture_dir: Optional[Path],
    wall_height: float,
    ppm: float,
    punches: Optional[dict] = None,
) -> bool:
    intervals = pl.texture_intervals
    if not intervals:
        intervals = [
            TextureInterval(from_vertex=0, to_vertex=n_verts - 1, texture=None)
        ]
    has_polys = False
    for iv in intervals:
        has_polys = _emit_interval_edges(
            pl, group, ctx, iv, n_verts, texture_dir, wall_height, ppm,
            punches=punches,
        ) or has_polys
    return has_polys


def _build_styled_wall(
    pl,
    group: EggGroup,
    ctx: EggContext,
    pack: StylePack,
    texture_dir: Optional[Path],
    wall_height: float,
    ppm: float,
    preset_images: dict,
    overlay_seed: Optional[int] = None,
    punches: Optional[dict] = None,
    niches: Optional[dict] = None,
) -> bool:
    from passages_tool.textures.band_compose import write_edge_diffuse

    n_verts = len(pl.vertices)
    override_edges: set[int] = set()
    has_polys = False
    u_acc = 0.0
    loop_u = bool(getattr(pack, "loop_u", True))
    for iv in pl.texture_intervals:
        if not iv.texture:
            continue
        override_edges.update(interval_edge_indices(pl, iv))
        has_polys = _emit_interval_edges(
            pl, group, ctx, iv, n_verts, texture_dir, wall_height, ppm,
            punches=punches,
        ) or has_polys

    for v_from, v_to in wall_edge_index_pairs(pl):
        if v_from in override_edges:
            continue
        p1 = pl.vertices[v_from]
        p2 = pl.vertices[v_to]
        x1, y1 = p1[0], p1[1]
        x2, y2 = p2[0], p2[1]
        dx, dy = x2 - x1, y2 - y1
        segment_len = math.sqrt(dx * dx + dy * dy)
        if segment_len < 1e-6:
            continue
        nx, ny = dy / segment_len, -dx / segment_len
        rel = None
        if texture_dir is not None:
            rel = write_edge_diffuse(
                pack,
                Path(texture_dir),
                pl.id,
                v_from,
                segment_len,
                wall_height,
                ppm,
                preset_images=preset_images,
                overlay_seed=overlay_seed,
                niches=(niches.get((pl.id, v_from), []) if niches else []),
                u0_m=(u_acc if loop_u else 0.0),
            )
        egg_tex = ctx.get_or_create_texture(rel) if rel else None
        holes = []
        if punches:
            holes = punches.get((pl.id, v_from), [])
        has_polys = _emit_edge_patches(
            ctx, group, x1, y1, x2, y2, segment_len, wall_height, nx, ny,
            holes, egg_tex, unique_uv=True,
        ) or has_polys
        if loop_u:
            u_acc += segment_len
    return has_polys


def _emit_interval_edges(
    pl,
    group: EggGroup,
    ctx: EggContext,
    iv: TextureInterval,
    n_verts: int,
    texture_dir: Optional[Path],
    wall_height: float,
    ppm: float,
    punches: Optional[dict] = None,
) -> bool:
    tex_w, tex_h = get_texture_size(iv.texture, texture_dir)
    egg_tex = ctx.get_or_create_texture(iv.texture) if iv.texture else None
    edges: list[tuple[int, int]] = []
    for e in interval_edge_indices(pl, iv):
        if e == n_verts - 1 and pl.closed and n_verts >= 2:
            edges.append((n_verts - 1, 0))
        elif e < n_verts - 1:
            edges.append((e, e + 1))
    has_polys = False
    accumulated_len = 0.0
    for v_from, v_to in edges:
        p1 = pl.vertices[v_from]
        p2 = pl.vertices[v_to]
        x1, y1 = p1[0], p1[1]
        x2, y2 = p2[0], p2[1]
        dx, dy = x2 - x1, y2 - y1
        segment_len = math.sqrt(dx * dx + dy * dy)
        if segment_len < 1e-6:
            continue
        nx, ny = dy / segment_len, -dx / segment_len
        holes = []
        if punches:
            holes = punches.get((pl.id, v_from), [])
        has_polys = _emit_edge_patches(
            ctx, group, x1, y1, x2, y2, segment_len, wall_height, nx, ny,
            holes, egg_tex, unique_uv=False, accum_m=accumulated_len,
            x_offset=iv.x_offset, ppm=ppm, tex_w=float(tex_w), tex_h=float(tex_h),
        ) or has_polys
        accumulated_len += segment_len
    return has_polys
