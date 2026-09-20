"""In-editor 3D viewpoint preview. Mixed into PassagesApp."""
from __future__ import annotations

from passages_tool.config import TOOL_ROOT
from passages_tool.log import get_logger

log = get_logger("app.preview")


class PreviewMixin:
    def _cb_render_preview(self, pid: str, v_from: int, v_to: int) -> None:
        from passages_tool.converter.scene_builder import build_scene
        from passages_tool.renderer.viewpoint_renderer import ViewpointRenderer
        from panda3d.core import TexturePool

        preview_dir = TOOL_ROOT / "temp_preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        tex_dir = self._tex.base_dir

        if tex_dir:
            from passages_tool.textures.manager import preload_level_textures
            preload_level_textures(self._level, tex_dir)

        try:
            build_scene(self._level, preview_dir, tex_dir, write_combined=False)
        except Exception:
            log.exception("Error compiling scene for preview")
            return

        temp_png = preview_dir / "preview.png"
        renderer = None
        try:
            renderer = ViewpointRenderer(self._level, preview_dir, tex_dir)
            off = self._level.eyepath_offset(pid)
            renderer.render_edge(off + v_from, off + v_to, temp_png)
        except Exception:
            log.exception("Error rendering preview")
            return
        finally:
            if renderer:
                renderer.close()

        if temp_png.is_file():
            tex_path_str = str(temp_png)
            TexturePool.release_texture(TexturePool.find_texture(tex_path_str))
            panda_tex = TexturePool.load_texture(tex_path_str)
            if panda_tex:
                try:
                    ref = self.base.imgui.loadTexture(panda_tex)
                    self._props.set_preview_image(ref)
                except Exception:
                    log.exception("Error loading preview texture into ImGui")
