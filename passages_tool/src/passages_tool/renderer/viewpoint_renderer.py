"""
renderer/viewpoint_renderer.py
──────────────────────────────
Panda3D offscreen renderer to bake viewpoint screenshots for level transitions.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from direct.showbase.ShowBase import ShowBase
from panda3d.core import Filename, PNMImage, PerspectiveLens, PointLight, LColor

from passages_tool.converter.scene_builder import load_scene
from passages_tool.editor.level import Level, PolylineType


class ViewpointRenderer:
    """Manages offscreen rendering for a level's EyePath viewpoints."""

    def __init__(self, level: Level, scene_dir: Path, texture_dir: Optional[Path] = None) -> None:
        self.level = level
        self.scene_dir = Path(scene_dir)
        self.texture_dir = Path(texture_dir) if texture_dir else Path(".")

        # Initialize ShowBase offscreen if not already running
        if getattr(ShowBase, "defaultShowBase", None) is None:
            self.base = ShowBase(windowType="offscreen")
        else:
            self.base = getattr(ShowBase, "defaultShowBase")

        # Preload level textures to handle any WebP-mislabeled-as-PNG formats
        from passages_tool.textures.manager import preload_level_textures
        preload_level_textures(self.level, self.texture_dir)

        # Load the assembled scene graph
        self.scene_root = load_scene(self.level, self.scene_dir, self.base.loader)
        self.scene_root.reparent_to(self.base.render)

    def render_edge(
        self,
        v_from: int,
        v_to: int,
        output_path: Path,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> bool:
        """Render a single viewpoint edge to a PNG file."""
        # Find EyePath vertices
        eyepath_pl = None
        for pl in self.level.polylines.values():
            if pl.type == PolylineType.EYEPATH:
                eyepath_pl = pl
                break

        if not eyepath_pl or v_from >= len(eyepath_pl.vertices) or v_to >= len(eyepath_pl.vertices):
            return False

        p_from = eyepath_pl.vertices[v_from]
        p_to = eyepath_pl.vertices[v_to]
        eye_height = self.level.meta.eye_height
        fov_h = self.level.meta.fov_h
        fov_v = self.level.meta.fov_v

        render_w = width if width is not None else self.level.meta.render_width
        render_h = height if height is not None else self.level.meta.render_height

        # 1. Create offscreen texture buffer
        buffer = self.base.win.make_texture_buffer("viewpoint_buf", render_w, render_h)
        if not buffer:
            return False

        # 2. Add camera to the buffer
        cam = self.base.make_camera(buffer)
        cam.reparent_to(self.scene_root)

        # Set position and heading in Mapping A (Z-up, horizontal is X, Y)
        cam.set_pos(p_from[0], p_from[1], eye_height)
        cam.look_at(p_to[0], p_to[1], eye_height)

        # Configure perspective lens
        lens = PerspectiveLens()
        lens.set_fov(fov_h, fov_v)
        lens.set_near_far(0.1, 100.0)
        cam.node().set_lens(lens)

        # Add camera headlight (PointLight) so the scene is illuminated from the viewer's viewpoint
        plight = PointLight("camera_headlight")
        plight.set_color(LColor(1.0, 1.0, 1.0, 1.0))
        plight.set_attenuation((0.0, 0.0, 0.03))
        pl_path = cam.attach_new_node(plight)
        pl_path.set_pos(0, 0, 0)
        self.scene_root.set_light(pl_path)

        # 3. Render frame (render twice to guarantee textures load on the GPU)
        self.base.graphicsEngine.render_frame()
        self.base.graphicsEngine.render_frame()

        # 4. Save screenshot
        pnm = PNMImage()
        ok = buffer.get_screenshot(pnm)
        if ok:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            pnm.write(Filename.from_os_specific(str(output_path)))

        # 5. Clean up camera and buffer
        self.scene_root.clear_light(pl_path)
        self.base.graphicsEngine.remove_window(buffer)
        cam.remove_node()

        return ok

    def render_midpoint(
        self,
        v_from: int,
        v_to: int,
        output_path: Path,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> bool:
        """Render a midpoint frame along the directed edge to a PNG file."""
        # Find EyePath vertices
        eyepath_pl = None
        for pl in self.level.polylines.values():
            if pl.type == PolylineType.EYEPATH:
                eyepath_pl = pl
                break

        if not eyepath_pl or v_from >= len(eyepath_pl.vertices) or v_to >= len(eyepath_pl.vertices):
            return False

        p_from = eyepath_pl.vertices[v_from]
        p_to = eyepath_pl.vertices[v_to]
        eye_height = self.level.meta.eye_height
        fov_h = self.level.meta.fov_h
        fov_v = self.level.meta.fov_v

        render_w = width if width is not None else self.level.meta.render_width
        render_h = height if height is not None else self.level.meta.render_height

        # Calculate midpoint position
        p_mid_x = p_from[0] + 0.5 * (p_to[0] - p_from[0])
        p_mid_y = p_from[1] + 0.5 * (p_to[1] - p_from[1])

        # 1. Create offscreen texture buffer
        buffer = self.base.win.make_texture_buffer("midpoint_buf", render_w, render_h)
        if not buffer:
            return False

        # 2. Add camera to the buffer
        cam = self.base.make_camera(buffer)
        cam.reparent_to(self.scene_root)

        # Set camera position at midpoint, looking towards the destination
        cam.set_pos(p_mid_x, p_mid_y, eye_height)
        cam.look_at(p_to[0], p_to[1], eye_height)

        # Configure perspective lens
        lens = PerspectiveLens()
        lens.set_fov(fov_h, fov_v)
        lens.set_near_far(0.1, 100.0)
        cam.node().set_lens(lens)

        # Add camera headlight (PointLight) so the scene is illuminated from the viewer's viewpoint
        plight = PointLight("camera_headlight")
        plight.set_color(LColor(1.0, 1.0, 1.0, 1.0))
        plight.set_attenuation((0.0, 0.0, 0.03))
        pl_path = cam.attach_new_node(plight)
        pl_path.set_pos(0, 0, 0)
        self.scene_root.set_light(pl_path)

        # 3. Render frame (render twice to guarantee textures load on the GPU)
        self.base.graphicsEngine.render_frame()
        self.base.graphicsEngine.render_frame()

        # 4. Save screenshot
        pnm = PNMImage()
        ok = buffer.get_screenshot(pnm)
        if ok:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            pnm.write(Filename.from_os_specific(str(output_path)))

        # 5. Clean up camera and buffer
        self.scene_root.clear_light(pl_path)
        self.base.graphicsEngine.remove_window(buffer)
        cam.remove_node()

        return ok

    def close(self) -> None:
        """Detaches and cleans up the loaded scene graph."""
        if hasattr(self, "scene_root") and self.scene_root:
            self.scene_root.remove_node()
