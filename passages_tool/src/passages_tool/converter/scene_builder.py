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
from panda3d.egg import EggData, EggExternalReference

from passages_tool.converter.egg_writer import parent_textures
from passages_tool.converter.arch_builder import build_arches
from passages_tool.converter.floor_ceiling_builder import build_ceiling, build_floor
from passages_tool.converter.lighting_builder import setup_lighting
from passages_tool.converter.wall_builder import build_wall_strips
from passages_tool.editor.level import Level

# Component eggs written by one geometry pass. scene.egg <File>-includes these.
COMPONENT_EGG_STEMS: tuple[str, ...] = ("walls", "floor", "ceiling", "arches")


def _write_egg(path: Path, groups) -> None:
    egg = EggData()
    egg.set_coordinate_system(CS_zup_right)
    parent_textures(egg, groups)
    for grp in groups:
        egg.add_child(grp)
    egg.write_egg(Filename.from_os_specific(str(path)))


def _write_combined_scene(path: Path, stems: tuple[str, ...] = COMPONENT_EGG_STEMS) -> None:
    """Write scene.egg as <File> includes — no second tessellation.

    Egg nodes cannot be dual-parented after the component writes, so the
    combined file references those eggs instead of rebuilding meshes.
    pview resolves the includes when the four files sit next to scene.egg.
    """
    egg = EggData()
    egg.set_coordinate_system(CS_zup_right)
    for stem in stems:
        egg.add_child(EggExternalReference(stem, f"{stem}.egg"))
    egg.write_egg(Filename.from_os_specific(str(path)))


def build_scene(
    level: Level,
    output_dir: Path,
    tex_dir: Optional[Path] = None,
    write_combined: bool = True,
) -> Path:
    """
    Assemble and export individual wall, floor, ceiling, and arch EGG meshes.
    When `write_combined` is True, also write scene.egg as <File> includes of
    those four (for pview). The runtime loader uses the component files, so
    in-editor preview and the baker can skip the combined file.
    Returns the path to scene.egg if written, otherwise walls.egg.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    wall_groups = build_wall_strips(level, tex_dir)
    floor_grp = build_floor(level, tex_dir)
    ceil_grp = build_ceiling(level, tex_dir)
    arch_groups = build_arches(level, tex_dir)

    _write_egg(output_dir / "walls.egg", wall_groups)
    _write_egg(output_dir / "floor.egg", [floor_grp])
    _write_egg(output_dir / "ceiling.egg", [ceil_grp])
    _write_egg(output_dir / "arches.egg", arch_groups)

    scene_path = output_dir / "scene.egg"
    if write_combined:
        _write_combined_scene(scene_path)
        return scene_path
    return output_dir / "walls.egg"


def load_scene(
    level: Level,
    egg_dir: Path,
    loader: Any,
    texture_dir: Optional[Path] = None,
) -> NodePath:
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

    if texture_dir is not None:
        try:
            from passages_tool.renderer.pom import apply_style_pom
            from passages_tool.textures.style import StyleError, load_level_style

            pack = None
            if level.meta.style:
                try:
                    pack = load_level_style(Path(texture_dir), level.meta.style)
                except StyleError:
                    pack = None
            apply_style_pom(scene_root, level, Path(texture_dir), loader, pack)
        except Exception:
            pass

    return scene_root
