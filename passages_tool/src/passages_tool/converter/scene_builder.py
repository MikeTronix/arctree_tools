"""
converter/scene_builder.py
──────────────────────────
Assembles the complete 3D scene (walls, floor, ceiling, arches) into a combined
EGG file, and provides a runtime loader that configures lighting and fog.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from panda3d.core import CS_zup_right, Fog, LColor, NodePath, Filename
from panda3d.egg import EggData

from passages_tool.converter.arch_builder import build_arches
from passages_tool.converter.floor_ceiling_builder import build_ceiling, build_floor
from passages_tool.converter.lighting_builder import setup_lighting
from passages_tool.converter.wall_builder import build_wall_strips
from passages_tool.editor.level import Level


def build_scene(level: Level, output_dir: Path, tex_dir: Optional[Path] = None) -> Path:
    """
    Assemble and export individual wall, floor, ceiling, and arch EGG meshes,
    as well as a combined scene.egg file for easy pview verification.
    Returns the path to the combined scene.egg file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write individual EGG files
    # Walls
    walls_egg = EggData()
    walls_egg.set_coordinate_system(CS_zup_right)
    for grp in build_wall_strips(level, tex_dir):
        walls_egg.add_child(grp)
    walls_egg.write_egg(str(output_dir / "walls.egg"))

    # Floor
    floor_egg = EggData()
    floor_egg.set_coordinate_system(CS_zup_right)
    floor_egg.add_child(build_floor(level, tex_dir))
    floor_egg.write_egg(str(output_dir / "floor.egg"))

    # Ceiling
    ceil_egg = EggData()
    ceil_egg.set_coordinate_system(CS_zup_right)
    ceil_egg.add_child(build_ceiling(level, tex_dir))
    ceil_egg.write_egg(str(output_dir / "ceiling.egg"))

    # Arches
    arches_egg = EggData()
    arches_egg.set_coordinate_system(CS_zup_right)
    for grp in build_arches(level, tex_dir):
        arches_egg.add_child(grp)
    arches_egg.write_egg(str(output_dir / "arches.egg"))

    # 2. Write combined scene EGG file
    scene_egg = EggData()
    scene_egg.set_coordinate_system(CS_zup_right)

    for grp in build_wall_strips(level, tex_dir):
        scene_egg.add_child(grp)
    scene_egg.add_child(build_floor(level, tex_dir))
    scene_egg.add_child(build_ceiling(level, tex_dir))
    for grp in build_arches(level, tex_dir):
        scene_egg.add_child(grp)

    scene_path = output_dir / "scene.egg"
    scene_egg.write_egg(str(scene_path))
    return scene_path


def load_scene(level: Level, egg_dir: Path, loader: Any) -> NodePath:
    """
    Load the exported level EGG files into a Panda3D scene graph NodePath,
    attaching the corresponding lighting and fog.
    """
    scene_root = NodePath("scene_root")

    # Load component models if they exist
    for name in ["walls", "floor", "ceiling", "arches"]:
        egg_path = egg_dir / f"{name}.egg"
        if egg_path.is_file():
            # Use absolute path to ensure loader finds the model file directly
            abs_path = egg_path.resolve().absolute()
            model = loader.load_model(Filename.from_os_specific(str(abs_path)), noCache=True)
            model.reparent_to(scene_root)

    # Apply lighting configuration
    setup_lighting(scene_root, level)

    # Configure global black linear fog (simulating fading corridors)
    fog = Fog("scene_fog")
    fog.set_color(LColor(0.0, 0.0, 0.0, 1.0))
    fog.set_linear_range(level.meta.fog_start, level.meta.fog_end)
    scene_root.set_fog(fog)

    # Enable the auto-shader so lighting, textures, normals, and fog are computed correctly
    scene_root.set_shader_auto()

    return scene_root
