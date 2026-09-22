"""
renderer/viewpoint_renderer.py
──────────────────────────────
Panda3D offscreen renderer to bake viewpoint screenshots for level transitions.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from direct.showbase.ShowBase import ShowBase
from panda3d.core import Filename, PNMImage, PerspectiveLens, PointLight, LColor

from passages_tool.config import (
    CAMERA_FAR,
    CAMERA_NEAR,
    HEADLIGHT_ATTENUATION,
    derived_fov_h,
)
from passages_tool.converter.scene_builder import load_scene
from passages_tool.editor.level import Level


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

        # Load the assembled scene graph as its own tree — do not parent it to
        # the editor's `render`, or 3D walls flash into the 2D viewport. The
        # offscreen camera is reparented onto scene_root, so it still sees it.
        self.scene_root = load_scene(
            self.level, self.scene_dir, self.base.loader, self.texture_dir
        )

    def _eyepath_endpoints(
        self, v_from: int, v_to: int
    ) -> Optional[tuple[tuple[float, float], tuple[float, float]]]:
        p_from = self.level.eyepath_vertex(v_from)
        p_to = self.level.eyepath_vertex(v_to)
        if p_from is None or p_to is None:
            return None
        return p_from, p_to

    def _render_camera(
        self,
        pos: tuple[float, float],
        look_at: tuple[float, float],
        output_path: Path,
        width: Optional[int],
        height: Optional[int],
        buffer_name: str,
        fov_h: Optional[float] = None,
    ) -> bool:
        """Place an offscreen camera at `pos`, look at `look_at`, write a PNG.

        ``fov_h`` defaults to the still's derived HFOV. Cube faces pass 90°.
        """
        eye_height = self.level.meta.eye_height
        fov_v = self.level.meta.fov_v
        render_w = width if width is not None else self.level.meta.render_width
        render_h = height if height is not None else self.level.meta.render_height

        buffer = self.base.win.make_texture_buffer(buffer_name, render_w, render_h)
        if not buffer:
            return False
        # Default buffer clear is white. A doorway whose alpha/punch opens onto
        # empty space would otherwise fill with white instead of fog-black.
        buffer.set_clear_color((0.0, 0.0, 0.0, 1.0))
        buffer.set_clear_color_active(True)

        cam = self.base.make_camera(buffer)
        cam.reparent_to(self.scene_root)
        cam.set_pos(pos[0], pos[1], eye_height)
        cam.look_at(look_at[0], look_at[1], eye_height)

        lens = PerspectiveLens()
        aspect_ratio = render_w / max(1, render_h)
        fov_h_calc = float(fov_h) if fov_h is not None else derived_fov_h(
            fov_v, render_w, render_h
        )
        lens.set_aspect_ratio(aspect_ratio)
        lens.set_fov(fov_h_calc, fov_v)
        lens.set_near_far(CAMERA_NEAR, CAMERA_FAR)
        cam.node().set_lens(lens)

        plight = PointLight("camera_headlight")
        plight.set_color(LColor(1.0, 1.0, 1.0, 1.0))
        plight.set_attenuation(HEADLIGHT_ATTENUATION)
        pl_path = cam.attach_new_node(plight)
        pl_path.set_pos(0, 0, 0)
        self.scene_root.set_light(pl_path)

        self.base.graphicsEngine.render_frame()
        self.base.graphicsEngine.render_frame()

        pnm = PNMImage()
        ok = buffer.get_screenshot(pnm)
        if ok:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            pnm.write(Filename.from_os_specific(str(output_path)))

        self.scene_root.clear_light(pl_path)
        self.base.graphicsEngine.remove_window(buffer)
        cam.remove_node()
        return ok

    def render_edge(
        self,
        v_from: int,
        v_to: int,
        output_path: Path,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> bool:
        """Render a single viewpoint edge to a PNG file."""
        ends = self._eyepath_endpoints(v_from, v_to)
        if ends is None:
            return False
        p_from, p_to = ends
        return self._render_camera(
            p_from, p_to, output_path, width, height, "viewpoint_buf"
        )

    def render_midpoint(
        self,
        v_from: int,
        v_to: int,
        output_path: Path,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> bool:
        """Render a midpoint frame along the directed edge to a PNG file.

        Uses the geometric 50% point of the edge (not the edge-on-capped
        `compute_transition_path` helper). That helper remains for validation
        experiments; changing bake camera placement is a content-visible fork.
        """
        ends = self._eyepath_endpoints(v_from, v_to)
        if ends is None:
            return False
        p_from, p_to = ends
        p_mid = (
            p_from[0] + 0.5 * (p_to[0] - p_from[0]),
            p_from[1] + 0.5 * (p_to[1] - p_from[1]),
        )
        return self._render_camera(
            p_mid, p_to, output_path, width, height, "midpoint_buf"
        )

    def close(self) -> None:
        """Detaches and cleans up the loaded scene graph."""
        if hasattr(self, "scene_root") and self.scene_root:
            self.scene_root.remove_node()
