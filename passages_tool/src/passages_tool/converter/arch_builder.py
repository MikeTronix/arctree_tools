"""
converter/arch_builder.py
─────────────────────────
Generates 3D arch quads geometry (.egg) from level Arch nodes.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from panda3d.egg import EggGroup, EggTexture

from passages_tool.converter.egg_writer import EggContext
from passages_tool.converter.wall_builder import get_texture_size
from passages_tool.editor.level import Level, Polyline, PolylineType


def build_arches(
    level: Level, texture_dir: Optional[Path] = None
) -> list[EggGroup]:
    """
    Build 3D arch quads for all Arch nodes in the level.
    Each Arch node yields a separate EggGroup for proper depth sorting.
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
        x_world = pos[0]
        y_world = pos[1]  # Horizontal Y-axis in Z-up coords

        width = pl.width
        height = (
            pl.height_override
            if pl.height_override is not None
            else wall_height
        )

        z_bottom = pl.z_offset
        z_top = pl.z_offset + height

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

        # UV scaling
        u_start = 0.0
        u_end = 1.0

        if pl.v_at_floor:
            v_bottom = (pl.z_offset * ppm) / tex_h
            v_top = ((pl.z_offset + height) * ppm) / tex_h
        else:
            v_bottom = 0.0
            v_top = (height * ppm) / tex_h

        if pl.orientation == "billboard":
            # Set billboard axial rotation around local Z axis
            group.set_billboard_type(EggGroup.BT_axis)

            # Positions in local coordinate system
            x_left = -width / 2.0
            x_right = width / 2.0

            # Quad faces towards -Y in local space, so width is along X
            bl = ctx.add_vertex(
                x_left, 0.0, z_bottom, u_start, v_bottom, (0.0, -1.0, 0.0)
            )
            br = ctx.add_vertex(
                x_right, 0.0, z_bottom, u_end, v_bottom, (0.0, -1.0, 0.0)
            )
            tr = ctx.add_vertex(
                x_right, 0.0, z_top, u_end, v_top, (0.0, -1.0, 0.0)
            )
            tl = ctx.add_vertex(
                x_left, 0.0, z_top, u_start, v_top, (0.0, -1.0, 0.0)
            )

            poly = ctx.add_polygon([bl, br, tr, tl], egg_tex)
            group.add_child(poly)

            # Position group origin in world coordinates
            group.add_translate3d((x_world, y_world, 0.0))
        else:
            # Fixed rotation (in degrees) - pl.orientation is the facing angle (normal direction)
            theta_deg = float(pl.orientation)
            theta_rad = math.radians(theta_deg)
            cos_t = math.cos(theta_rad)
            sin_t = math.sin(theta_rad)

            # Normal vector points along the facing direction
            nx = cos_t
            ny = sin_t
            nz = 0.0

            # Width offset vector is perpendicular to the normal (orientation + 90)
            dx_w = (width / 2.0) * (-sin_t)
            dy_w = (width / 2.0) * cos_t

            x_left = x_world - dx_w
            y_left = y_world - dy_w
            x_right = x_world + dx_w
            y_right = y_world + dy_w

            bl = ctx.add_vertex(
                x_left, y_left, z_bottom, u_start, v_bottom, (nx, ny, nz)
            )
            br = ctx.add_vertex(
                x_right, y_right, z_bottom, u_end, v_bottom, (nx, ny, nz)
            )
            tr = ctx.add_vertex(
                x_right, y_right, z_top, u_end, v_top, (nx, ny, nz)
            )
            tl = ctx.add_vertex(
                x_left, y_left, z_top, u_start, v_top, (nx, ny, nz)
            )

            poly = ctx.add_polygon([bl, br, tr, tl], egg_tex)
            group.add_child(poly)

        if group.get_first_child() is not None:
            groups.append(group)

    return groups
