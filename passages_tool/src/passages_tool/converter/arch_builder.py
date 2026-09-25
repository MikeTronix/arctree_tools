"""
converter/arch_builder.py
─────────────────────────
Generates 3D arch quads geometry (.egg) from level Arch nodes.
Supports dynamic wall snapping (v3) and N-slice trim-sheet texturing.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from panda3d.egg import EggGroup, EggTexture

from passages_tool.converter.egg_writer import EggContext
from passages_tool.converter.opening import (
    is_3d_opening,
    is_niche,
    is_recess,
    is_volume,
    opening_depth_m,
    opening_profile_name,
    profile_polyline,
)
from passages_tool.converter.wall_builder import get_texture_size
from passages_tool.editor.level import Level, Polyline, PolylineType
from passages_tool.textures.style import StyleError, load_level_style

# N-slice cards sit on the wall plane; push them into the room so a PNG
# dressing does not z-fight (half the card inside the wall).
_CARD_PUSH_M = 0.025


def load_arch_config(texture_name: Optional[str], texture_dir: Optional[Path]) -> Optional[dict]:
    """Load the sidecar .arch.json configuration if it exists."""
    if not texture_name or not texture_dir:
        return None
    tex_path = Path(texture_name)
    json_name = tex_path.with_suffix(".arch.json").name
    json_path = texture_dir / json_name
    if json_path.exists():
        try:
            import json
            with open(json_path, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def find_snap_points(
    level: Level, pos: tuple[float, float], theta_deg: float
) -> tuple[tuple[float, float], tuple[float, float], float, tuple[float, float], tuple[float, float]]:
    """
    Raycast along the transverse axis of the arch to find nearest wall intersections on both sides.
    Returns:
      P_left (tuple): coordinate of left snap point
      P_right (tuple): coordinate of right snap point
      width (float): distance between left and right snap points
      normal (tuple): normalized facing normal vector
      midpoint (tuple): coordinates of new centered midpoint
    """
    theta_rad = math.radians(theta_deg)
    sin_t = math.sin(theta_rad)
    cos_t = math.cos(theta_rad)
    
    # Transverse axes (left and right perpendiculars)
    d_right = (-sin_t, cos_t)
    d_left = (sin_t, -cos_t)
    
    p_x, p_y = pos
    
    # Defaults in case no walls intersect
    best_t_left = float("inf")
    best_p_left = (p_x + d_left[0] * 2.0, p_y + d_left[1] * 2.0)
    
    best_t_right = float("inf")
    best_p_right = (p_x + d_right[0] * 2.0, p_y + d_right[1] * 2.0)
    
    for pl in level.polylines.values():
        if pl.type != PolylineType.WALL or not pl.vertices:
            continue
        
        segments = []
        for i in range(len(pl.vertices) - 1):
            segments.append((pl.vertices[i], pl.vertices[i+1]))
        if pl.closed and len(pl.vertices) >= 3:
            segments.append((pl.vertices[-1], pl.vertices[0]))
            
        for a, b in segments:
            ax, ay = a
            bx, by = b
            dx = bx - ax
            dy = by - ay
            
            # Solve intersection for right ray: P + t*D = A + u*(B - A)
            rx, ry = d_right
            det_r = dx * ry - dy * rx
            if abs(det_r) > 1e-6:
                t = (dy * (p_x - ax) - dx * (p_y - ay)) / det_r
                u = (rx * (ay - p_y) - ry * (ax - p_x)) / det_r
                if t > 0.0 and 0.0 <= u <= 1.0:
                    if t < best_t_right:
                        best_t_right = t
                        best_p_right = (p_x + t * rx, p_y + t * ry)
                        
            # Solve intersection for left ray: P + t*D = A + u*(B - A)
            lx, ly = d_left
            det_l = dx * ly - dy * lx
            if abs(det_l) > 1e-6:
                t = (dy * (p_x - ax) - dx * (p_y - ay)) / det_l
                u = (lx * (ay - p_y) - ly * (ax - p_x)) / det_l
                if t > 0.0 and 0.0 <= u <= 1.0:
                    if t < best_t_left:
                        best_t_left = t
                        best_p_left = (p_x + t * lx, p_y + t * ly)

    width = math.sqrt((best_p_right[0] - best_p_left[0])**2 + (best_p_right[1] - best_p_left[1])**2)
    midpoint = (0.5 * (best_p_left[0] + best_p_right[0]), 0.5 * (best_p_left[1] + best_p_right[1]))
    
    # Alignment-corrected facing normal perpendicular to span vector
    span_x = best_p_right[0] - best_p_left[0]
    span_y = best_p_right[1] - best_p_left[1]
    span_len = math.sqrt(span_x**2 + span_y**2)
    if span_len > 1e-6:
        nx = -span_y / span_len
        ny = span_x / span_len
        orig_nx = cos_t
        orig_ny = sin_t
        if nx * orig_nx + ny * orig_ny < 0:
            nx = -nx
            ny = -ny
    else:
        nx = cos_t
        ny = sin_t
        
    return best_p_left, best_p_right, width, (nx, ny), midpoint


def _world_on_span(p_left, p_right, width, nx, ny, s, z, along):
    t = s / width if width > 1e-9 else 0.0
    x = p_left[0] + t * (p_right[0] - p_left[0]) + along * nx
    y = p_left[1] + t * (p_right[1] - p_left[1]) + along * ny
    return x, y, z


def _add_quad(ctx, group, pts, tex, normal):
    verts = []
    uvs = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    for (x, y, z), (u, v) in zip(pts, uvs):
        verts.append(ctx.add_vertex(x, y, z, u, v, normal))
    poly = ctx.add_polygon(verts, tex)
    group.add_child(poly)
    return poly


def _build_volume_box(
    group: EggGroup,
    ctx: EggContext,
    p_left,
    p_right,
    width: float,
    nx: float,
    ny: float,
    z_bottom: float,
    z_top: float,
    depth: float,
    tex,
    *,
    into_room: bool = True,
) -> None:
    """Box on the wall. ``into_room``: +normal (pilaster). Else −normal (recess).

    Wall-plane face is omitted (flush / hole). Far cap is always emitted.
    """
    depth = max(0.05, float(depth))
    w = max(1e-4, float(width))
    sign = 1.0 if into_room else -1.0
    a0, a1 = 0.0, sign * depth
    n_out = (nx, ny, 0.0)
    sx = (p_right[0] - p_left[0]) / w
    sy = (p_right[1] - p_left[1]) / w
    n_right = (sx, sy, 0.0)
    n_left = (-sx, -sy, 0.0)

    def W(s, z, along):
        return _world_on_span(p_left, p_right, w, nx, ny, s, z, along)

    # Far cap (pilaster front or recess back), facing the room
    _add_quad(
        ctx, group,
        (W(0.0, z_bottom, a1), W(w, z_bottom, a1), W(w, z_top, a1), W(0.0, z_top, a1)),
        tex, n_out,
    )
    _add_quad(
        ctx, group,
        (W(0.0, z_bottom, a0), W(0.0, z_bottom, a1), W(0.0, z_top, a1), W(0.0, z_top, a0)),
        tex, n_left,
    )
    _add_quad(
        ctx, group,
        (W(w, z_bottom, a1), W(w, z_bottom, a0), W(w, z_top, a0), W(w, z_top, a1)),
        tex, n_right,
    )
    _add_quad(
        ctx, group,
        (W(0.0, z_top, a0), W(0.0, z_top, a1), W(w, z_top, a1), W(w, z_top, a0)),
        tex, (0.0, 0.0, 1.0),
    )
    _add_quad(
        ctx, group,
        (W(0.0, z_bottom, a1), W(0.0, z_bottom, a0), W(w, z_bottom, a0), W(w, z_bottom, a1)),
        tex, (0.0, 0.0, -1.0),
    )


def _build_opening_slab(
    group: EggGroup,
    ctx: EggContext,
    p_left,
    p_right,
    width: float,
    nx: float,
    ny: float,
    z_bottom: float,
    z_top: float,
    depth: float,
    profile: str,
    front_tex,
    side_tex,
) -> None:
    """Flush-front slab: tunnel along the profile, front/back cards, spandrels."""
    height = z_top - z_bottom
    depth = max(0.05, float(depth))
    pts = profile_polyline(profile, width, z_bottom, height)
    n_in = (-nx, -ny, 0.0)
    n_out = (nx, ny, 0.0)
    # Inner tunnel (into the wall = -normal)
    nseg = len(pts)
    for i in range(nseg):
        s0, z0 = pts[i]
        s1, z1 = pts[(i + 1) % nseg]
        f0 = _world_on_span(p_left, p_right, width, nx, ny, s0, z0, 0.0)
        f1 = _world_on_span(p_left, p_right, width, nx, ny, s1, z1, 0.0)
        b0 = _world_on_span(p_left, p_right, width, nx, ny, s0, z0, -depth)
        b1 = _world_on_span(p_left, p_right, width, nx, ny, s1, z1, -depth)
        _add_quad(ctx, group, (f0, f1, b1, b0), side_tex, n_in)
    # Front / back decorative cards (bounding rect). Skip when there is no
    # door texture — untextured egg polys are opaque white and seal the hole.
    if front_tex is not None:
        fl = _world_on_span(p_left, p_right, width, nx, ny, 0.0, z_bottom, 0.0)
        fr = _world_on_span(p_left, p_right, width, nx, ny, width, z_bottom, 0.0)
        ftr = _world_on_span(p_left, p_right, width, nx, ny, width, z_top, 0.0)
        ftl = _world_on_span(p_left, p_right, width, nx, ny, 0.0, z_top, 0.0)
        poly_f = _add_quad(ctx, group, (fl, fr, ftr, ftl), front_tex, n_out)
        poly_f.set_bface_flag(True)
        bl = _world_on_span(p_left, p_right, width, nx, ny, 0.0, z_bottom, -depth)
        br = _world_on_span(p_left, p_right, width, nx, ny, width, z_bottom, -depth)
        btr = _world_on_span(p_left, p_right, width, nx, ny, width, z_top, -depth)
        btl = _world_on_span(p_left, p_right, width, nx, ny, 0.0, z_top, -depth)
        poly_b = _add_quad(ctx, group, (br, bl, btl, btr), front_tex, n_in)
        poly_b.set_bface_flag(True)
    if profile in ("round", "gothic"):
        # Spandrels: corner (0, z_top) / (width, z_top) to the upper profile.
        upper_z = [p[1] for p in pts if p[1] > z_bottom + 1e-4]
        spring = min(upper_z) if upper_z else z_bottom
        left_arc = [p for p in pts if p[0] <= width * 0.5 + 1e-6 and p[1] >= spring - 1e-6]
        right_arc = [p for p in pts if p[0] >= width * 0.5 - 1e-6 and p[1] >= spring - 1e-6]
        left_arc = sorted(left_arc, key=lambda p: p[1])
        right_arc = sorted(right_arc, key=lambda p: p[1])
        corner_l = (0.0, z_top)
        corner_r = (width, z_top)
        for along, nrm in ((0.0, n_out), (-depth, n_in)):
            if len(left_arc) >= 2:
                c = _world_on_span(p_left, p_right, width, nx, ny, corner_l[0], corner_l[1], along)
                for j in range(len(left_arc) - 1):
                    a = _world_on_span(p_left, p_right, width, nx, ny, left_arc[j][0], left_arc[j][1], along)
                    b = _world_on_span(p_left, p_right, width, nx, ny, left_arc[j + 1][0], left_arc[j + 1][1], along)
                    tri = [c, a, b] if along == 0.0 else [c, b, a]
                    v0 = ctx.add_vertex(*tri[0], 0.0, 1.0, nrm)
                    v1 = ctx.add_vertex(*tri[1], 0.0, 0.0, nrm)
                    v2 = ctx.add_vertex(*tri[2], 1.0, 0.0, nrm)
                    group.add_child(ctx.add_polygon([v0, v1, v2], side_tex))
            if len(right_arc) >= 2:
                c = _world_on_span(p_left, p_right, width, nx, ny, corner_r[0], corner_r[1], along)
                for j in range(len(right_arc) - 1):
                    a = _world_on_span(p_left, p_right, width, nx, ny, right_arc[j][0], right_arc[j][1], along)
                    b = _world_on_span(p_left, p_right, width, nx, ny, right_arc[j + 1][0], right_arc[j + 1][1], along)
                    tri = [c, b, a] if along == 0.0 else [c, a, b]
                    v0 = ctx.add_vertex(*tri[0], 1.0, 1.0, nrm)
                    v1 = ctx.add_vertex(*tri[1], 1.0, 0.0, nrm)
                    v2 = ctx.add_vertex(*tri[2], 0.0, 0.0, nrm)
                    group.add_child(ctx.add_polygon([v0, v1, v2], side_tex))


def build_arches(
    level: Level, texture_dir: Optional[Path] = None
) -> list[EggGroup]:
    """
    Build 3D arch quads for all Arch nodes in the level.
    Supports N-slice texturing and dynamic wall snapping.
    """
    groups: list[EggGroup] = []
    wall_height = level.meta.wall_height
    ppm = level.meta.pixels_per_meter
    pack = None
    if level.meta.style and texture_dir is not None:
        try:
            pack = load_level_style(Path(texture_dir), level.meta.style)
        except StyleError:
            pack = None

    for pl in level.polylines.values():
        if pl.type != PolylineType.ARCH or not pl.vertices:
            continue

        # Each arch must be a separate EggGroup for transparency depth sorting
        group = EggGroup(f"arch_{pl.id}")
        ctx = EggContext(f"arch_{pl.id}")
        group.add_child(ctx.vpool)

        pos = pl.vertices[0]
        
        # Load texture size for V scaling
        tex_w, tex_h = get_texture_size(pl.texture, texture_dir)
        egg_tex = ctx.get_or_create_texture(pl.texture) if pl.texture else None

        # Bind transparency modes
        if egg_tex is not None:
            if pl.transparency == "alpha_test":
                egg_tex.set_alpha_mode(EggTexture.AM_binary)
            elif pl.transparency == "alpha_blend":
                egg_tex.set_alpha_mode(EggTexture.AM_blend)
            else:
                egg_tex.set_alpha_mode(EggTexture.AM_off)

        is_billboard = (pl.orientation == "billboard")
        auto_snap = (
            getattr(pl, "auto_snap", False)
            and not is_billboard
            and not is_volume(pl)
        )
        
        # Solve endpoints and orientation
        if auto_snap:
            try:
                theta_deg = float(pl.orientation)
            except ValueError:
                theta_deg = 0.0
            p_left, p_right, width, normal, midpoint = find_snap_points(level, pos, theta_deg)
            nx, ny = normal
            x_world, y_world = midpoint
        else:
            width = pl.width
            x_world, y_world = pos
            if is_billboard:
                nx, ny = 0.0, -1.0
            else:
                try:
                    theta_deg = float(pl.orientation)
                except ValueError:
                    theta_deg = 0.0
                theta_rad = math.radians(theta_deg)
                nx = math.cos(theta_rad)
                ny = math.sin(theta_rad)
                
            if not is_billboard:
                theta_rad = math.radians(theta_deg)
                dx_w = (width / 2.0) * (-math.sin(theta_rad))
                dy_w = (width / 2.0) * math.cos(theta_rad)
                p_left = (x_world - dx_w, y_world - dy_w)
                p_right = (x_world + dx_w, y_world + dy_w)

        height = (
            pl.height_override
            if pl.height_override is not None
            else wall_height
        )

        z_bottom = pl.z_offset
        z_top = pl.z_offset + height

        # Compute V scaling coordinates
        if pl.v_at_floor:
            v_bottom = (pl.z_offset * ppm) / tex_h
            v_top = ((pl.z_offset + height) * ppm) / tex_h
        else:
            # PNG fills this card from its bottom (z_offset) to z_offset+height.
            v_bottom = 0.0
            v_top = (height * ppm) / tex_h

        if is_recess(pl) and not is_billboard and width > 1e-6:
            depth = opening_depth_m(pl, pack)
            side_name = getattr(pl, "side_texture", None) or None
            if not side_name and pack and pack.default_opening.side_preset:
                side_name = f"presets/{pack.default_opening.side_preset}/diffuse.png"
            if not side_name:
                side_name = pl.texture
            side_tex = ctx.get_or_create_texture(side_name) if side_name else egg_tex
            _build_volume_box(
                group, ctx, p_left, p_right, width, nx, ny,
                z_bottom, z_top, depth, side_tex or egg_tex,
                into_room=False,
            )
            if group.get_first_child() is not None:
                groups.append(group)
            continue

        if is_volume(pl) and not is_billboard and width > 1e-6:
            depth = opening_depth_m(pl, pack)
            side_name = getattr(pl, "side_texture", None) or None
            if not side_name and pack and pack.default_opening.side_preset:
                side_name = f"presets/{pack.default_opening.side_preset}/diffuse.png"
            if not side_name:
                side_name = pl.texture
            side_tex = ctx.get_or_create_texture(side_name) if side_name else egg_tex
            _build_volume_box(
                group, ctx, p_left, p_right, width, nx, ny,
                z_bottom, z_top, depth, side_tex or egg_tex,
                into_room=True,
            )
            if group.get_first_child() is not None:
                groups.append(group)
            continue

        if is_3d_opening(pl) and not is_billboard and width > 1e-6:
            depth = opening_depth_m(pl, pack)
            prof = opening_profile_name(pl, pack)
            side_name = getattr(pl, "side_texture", None) or None
            if not side_name and pack and pack.default_opening.side_preset:
                side_name = f"presets/{pack.default_opening.side_preset}/diffuse.png"
            if not side_name:
                side_name = pl.texture
            side_tex = ctx.get_or_create_texture(side_name) if side_name else egg_tex
            _build_opening_slab(
                group, ctx, p_left, p_right, width, nx, ny,
                z_bottom, z_top, depth, prof, egg_tex, side_tex,
            )
            if group.get_first_child() is not None:
                groups.append(group)
            continue

        # POM niche: unique wall maps carry the dip. No coplanar card unless
        # the author assigned a PNG (then it is a dressing card, pushed out).
        if is_niche(pl) and not pl.texture:
            continue

        # N-slice UV partitioning (XOR with 3D opening)
        arch_cfg = load_arch_config(pl.texture, texture_dir)
        u_start, u_end = 0.0, 1.0
        
        if arch_cfg and width > 0.0:
            tex_w_cfg = float(arch_cfg.get("texture_width", tex_w))
            w_pil_l = float(arch_cfg.get("nominal_pillar_l_width_m", 0.5))
            w_pil_r = float(arch_cfg.get("nominal_pillar_r_width_m", 0.5))
            w_key = float(arch_cfg.get("nominal_keystone_width_m", 0.25))
            w_tile = float(arch_cfg.get("nominal_tile_width_m", 0.375))
            
            px_pil_l = float(arch_cfg.get("pillar_l_width_px", 128))
            px_pil_r = float(arch_cfg.get("pillar_r_width_px", 128))
            px_key = float(arch_cfg.get("keystone_width_px", 64))
            px_tile = float(arch_cfg.get("tile_width_px", 96))
            
            # UV anchor coordinates
            u0 = 0.0
            u1 = px_pil_l / tex_w_cfg
            u2 = (px_pil_l + px_tile) / tex_w_cfg
            u3 = (px_pil_l + px_tile + px_key) / tex_w_cfg
            u4 = (px_pil_l + px_tile + px_key + px_tile) / tex_w_cfg
            u5 = 1.0
            
            min_width = w_pil_l + w_pil_r + w_key
            if width < min_width:
                scale_factor = width / min_width
                w_pil_l *= scale_factor
                w_pil_r *= scale_factor
                w_key *= scale_factor
                boundaries = [
                    (0.0, w_pil_l, u0, u1),
                    (w_pil_l, w_pil_l + w_key, u2, u3),
                    (w_pil_l + w_key, width, u4, u5)
                ]
            else:
                w_bands = width - min_width
                w_band = w_bands / 2.0
                N = max(1, round(w_band / w_tile))
                w_tile_act = w_band / N
                
                boundaries = []
                # Left Pillar
                boundaries.append((0.0, w_pil_l, u0, u1))
                # Left Voussoir Band (N repeated segments)
                for i in range(N):
                    x_s = w_pil_l + i * w_tile_act
                    x_e = x_s + w_tile_act
                    boundaries.append((x_s, x_e, u1, u2))
                # Keystone
                x_key_s = w_pil_l + w_band
                x_key_e = x_key_s + w_key
                boundaries.append((x_key_s, x_key_e, u2, u3))
                # Right Voussoir Band (N repeated segments)
                for i in range(N):
                    x_s = x_key_e + i * w_tile_act
                    x_e = x_s + w_tile_act
                    boundaries.append((x_s, x_e, u3, u4))
                # Right Pillar
                boundaries.append((width - w_pil_r, width, u4, u5))
        else:
            boundaries = [(0.0, width, u_start, u_end)]

        # Generate geometry quads
        if is_billboard:
            group.set_billboard_type(EggGroup.BT_axis)
            for x_start, x_end, u_s, u_e in boundaries:
                x_l = -width / 2.0 + x_start
                x_r = -width / 2.0 + x_end
                
                y_push = -_CARD_PUSH_M
                bl = ctx.add_vertex(x_l, y_push, z_bottom, u_s, v_bottom, (0.0, -1.0, 0.0))
                br = ctx.add_vertex(x_r, y_push, z_bottom, u_e, v_bottom, (0.0, -1.0, 0.0))
                tr = ctx.add_vertex(x_r, y_push, z_top, u_e, v_top, (0.0, -1.0, 0.0))
                tl = ctx.add_vertex(x_l, y_push, z_top, u_s, v_top, (0.0, -1.0, 0.0))
                
                poly = ctx.add_polygon([bl, br, tr, tl], egg_tex)
                poly.set_bface_flag(True)
                group.add_child(poly)
            group.add_translate3d((x_world, y_world, 0.0))
        else:
            dx_span = p_right[0] - p_left[0]
            dy_span = p_right[1] - p_left[1]
            
            for x_start, x_end, u_s, u_e in boundaries:
                t_s = x_start / width if width > 0.0 else 0.0
                t_e = x_end / width if width > 0.0 else 1.0
                
                x_l = p_left[0] + t_s * dx_span + nx * _CARD_PUSH_M
                y_l = p_left[1] + t_s * dy_span + ny * _CARD_PUSH_M
                x_r = p_left[0] + t_e * dx_span + nx * _CARD_PUSH_M
                y_r = p_left[1] + t_e * dy_span + ny * _CARD_PUSH_M
                
                bl = ctx.add_vertex(x_l, y_l, z_bottom, u_s, v_bottom, (nx, ny, 0.0))
                br = ctx.add_vertex(x_r, y_r, z_bottom, u_e, v_bottom, (nx, ny, 0.0))
                tr = ctx.add_vertex(x_r, y_r, z_top, u_e, v_top, (nx, ny, 0.0))
                tl = ctx.add_vertex(x_l, y_l, z_top, u_s, v_top, (nx, ny, 0.0))
                
                poly = ctx.add_polygon([bl, br, tr, tl], egg_tex)
                poly.set_bface_flag(True)
                group.add_child(poly)

        if group.get_first_child() is not None:
            groups.append(group)

    return groups
