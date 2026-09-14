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
from passages_tool.converter.wall_builder import get_texture_size
from passages_tool.editor.level import Level, Polyline, PolylineType


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
        auto_snap = getattr(pl, "auto_snap", False) and not is_billboard
        
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
            v_bottom = 0.0
            v_top = (height * ppm) / tex_h

        # N-slice UV partitioning
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
                
                bl = ctx.add_vertex(x_l, 0.0, z_bottom, u_s, v_bottom, (0.0, -1.0, 0.0))
                br = ctx.add_vertex(x_r, 0.0, z_bottom, u_e, v_bottom, (0.0, -1.0, 0.0))
                tr = ctx.add_vertex(x_r, 0.0, z_top, u_e, v_top, (0.0, -1.0, 0.0))
                tl = ctx.add_vertex(x_l, 0.0, z_top, u_s, v_top, (0.0, -1.0, 0.0))
                
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
                
                x_l = p_left[0] + t_s * dx_span
                y_l = p_left[1] + t_s * dy_span
                x_r = p_left[0] + t_e * dx_span
                y_r = p_left[1] + t_e * dy_span
                
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
