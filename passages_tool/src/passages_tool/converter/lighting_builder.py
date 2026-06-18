"""
converter/lighting_builder.py
─────────────────────────────
Applies runtime lights (AmbientLight and PointLights) to a Panda3D scene graph.
"""
from __future__ import annotations

from typing import Any
from panda3d.core import AmbientLight, PointLight, LColor, NodePath

from passages_tool.editor.level import Level, PolylineType


def setup_lighting(scene_root: NodePath, level: Level) -> list[NodePath]:
    """
    Configure ambient and point lights in the scene.
    Point lights are placed at the center of Arches marked as light sources.
    Returns a list of NodePaths for the created lights.
    """
    light_paths: list[NodePath] = []

    # 1. Global Ambient Light
    ambient = AmbientLight("global_ambient")
    # Soft ambient light so shadowed walls are still slightly visible
    ambient.set_color(LColor(0.18, 0.18, 0.18, 1.0))
    al_path = scene_root.attach_new_node(ambient)
    scene_root.set_light(al_path)
    light_paths.append(al_path)

    # 2. Point Lights from Arches
    wall_height = level.meta.wall_height
    for pl in level.polylines.values():
        if pl.type == PolylineType.ARCH and pl.is_light_source:
            pos = pl.vertices[0]
            x_world = pos[0]
            y_world = pos[1]  # Horizontal Y-axis in Z-up

            # Vertically position light at the center of the arch quad
            height = (
                pl.height_override
                if pl.height_override is not None
                else wall_height
            )
            z_world = pl.z_offset + height / 2.0

            plight = PointLight(f"point_light_{pl.id}")
            r, g, b = pl.light_color
            intensity = pl.light_intensity
            plight.set_color(
                LColor(r * intensity, g * intensity, b * intensity, 1.0)
            )

            # Attenuation constants: (constant, linear, quadratic)
            # Quadratic term of 0.03 gives a smooth falloff over 10-20 meters
            plight.set_attenuation((0.0, 0.0, 0.03))

            pl_path = scene_root.attach_new_node(plight)
            pl_path.set_pos(x_world, y_world, z_world)
            scene_root.set_light(pl_path)
            light_paths.append(pl_path)

    return light_paths
