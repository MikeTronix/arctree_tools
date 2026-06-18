"""
ui/palette.py
─────────────
Texture palette panel — Dear ImGui sidebar showing texture thumbnails.

Uses imgui-bundle (from panda3d-imgui / p3dimgui).

Texture display via p3dimgui:
  - Panda3D Texture objects are registered with base.imgui.loadTexture()
    which returns an imgui.ImTextureRef.
  - ImTextureRef is used directly with imgui.image() and imgui.image_button().

Layout
──────
  ┌──────────────────────────┐
  │  Textures   [Browse…]    │
  ├──────────────────────────┤
  │  [thumb][thumb][thumb]   │   ← 2-column thumbnail grid (scrollable)
  ├──────────────────────────┤
  │  full-size detail view   │   ← selected texture detail
  └──────────────────────────┘
"""
from __future__ import annotations

from typing import Callable, Optional

from passages_tool.config import PALETTE_PANEL_W, THUMBNAIL_DISPLAY_SIZE, THUMBNAIL_H, THUMBNAIL_W
from passages_tool.textures.manager import TextureManager


class TexturePalette:
    def __init__(
        self,
        texture_manager: TextureManager,
        callbacks: Optional[dict[str, Callable]] = None,
    ) -> None:
        self._mgr    = texture_manager
        self._cb     = callbacks or {}
        self._selected: Optional[str] = None
        # Cache: texture name → imgui.ImTextureRef (thumb and full)
        self._thumb_refs: dict[str, object] = {}
        self._full_refs:  dict[str, object] = {}

    @property
    def selected_name(self) -> Optional[str]:
        return self._selected

    def select(self, name: Optional[str]) -> None:
        self._selected = name

    def draw(self) -> None:
        """Render the palette panel. Must be called inside an imgui frame."""
        try:
            from imgui_bundle import imgui
        except ImportError:
            return

        # ── Panel position and size ────────────────────────────────────────────
        display_h = imgui.get_io().display_size.y
        panel_h   = display_h - 20   # from below menu bar to window bottom

        # Cond_.always so position sticks even if imgui.ini saved something bad.
        always     = imgui.Cond_.always.value
        no_move    = imgui.WindowFlags_.no_move.value
        no_resize  = imgui.WindowFlags_.no_resize.value
        no_collapse= imgui.WindowFlags_.no_collapse.value
        flags = no_move | no_resize | no_collapse

        imgui.set_next_window_size((PALETTE_PANEL_W, panel_h), always)
        imgui.set_next_window_pos((0, 20), always)

        opened, _ = imgui.begin("Textures", flags=flags)
        # Always call end() even if not opened.
        if not opened:
            imgui.end()
            return

        # ── Browse button ─────────────────────────────────────────────────────
        if imgui.button("Browse folder…"):
            browse_fn = self._cb.get("browse")
            if browse_fn:
                browse_fn()

        if self._mgr.base_dir:
            imgui.text_colored((0.6, 0.8, 0.6, 1.0), str(self._mgr.base_dir.name))
        else:
            imgui.text_colored((0.6, 0.6, 0.6, 1.0), "No folder loaded")

        imgui.separator()

        # ── Thumbnail grid ────────────────────────────────────────────────────
        names = self._mgr.texture_names
        if not names:
            imgui.text_wrapped("No textures found.\nClick 'Browse folder…'.")
        else:
            tw = THUMBNAIL_DISPLAY_SIZE
            th = THUMBNAIL_DISPLAY_SIZE
            avail_w = imgui.get_content_region_avail().x
            cols = max(1, int(avail_w // (tw + 8)))
            col  = 0

            for name in names:
                thumb_ref = self._get_thumb_ref(name)
                is_sel    = name == self._selected

                if is_sel:
                    imgui.push_style_color(imgui.Col_.button.value, (0.2, 0.7, 0.2, 0.7))

                if thumb_ref is not None:
                    clicked = imgui.image_button(f"tb_{name}", thumb_ref, (tw, th))
                else:
                    clicked = imgui.button(name[:12], (tw, th))

                if is_sel:
                    imgui.pop_style_color()

                if imgui.is_item_hovered():
                    imgui.set_tooltip(name)

                if clicked:
                    self._selected = name

                col += 1
                if col < cols:
                    imgui.same_line()
                else:
                    col = 0

        imgui.separator()

        # ── Detail view ───────────────────────────────────────────────────────
        if self._selected:
            imgui.text(self._selected)
            full_ref = self._get_full_ref(self._selected)
            if full_ref is not None:
                orig_tex = self._mgr.get_panda_texture(self._selected)
                if orig_tex:
                    avail_w = imgui.get_content_region_avail().x
                    orig_w  = orig_tex.getXSize() or 1
                    orig_h  = orig_tex.getYSize() or 1
                    disp_w  = float(min(avail_w, PALETTE_PANEL_W - 16))
                    disp_h  = disp_w * (orig_h / orig_w)
                    imgui.image(full_ref, (disp_w, disp_h))

        imgui.end()

    # ── Internal: get ImTextureRef objects ────────────────────────────────────

    def _get_thumb_ref(self, name: str) -> Optional[object]:
        if name not in self._thumb_refs:
            panda_tex = self._mgr.get_thumbnail_texture(name)
            if panda_tex is None:
                self._thumb_refs[name] = None   # sentinel: don't retry
                return None
            ref = self._register_texture(panda_tex)
            self._thumb_refs[name] = ref        # may be None if register fails
        return self._thumb_refs.get(name)

    def _get_full_ref(self, name: str) -> Optional[object]:
        if name not in self._full_refs:
            panda_tex = self._mgr.get_panda_texture(name)
            if panda_tex is None:
                self._full_refs[name] = None    # sentinel: don't retry
                return None
            ref = self._register_texture(panda_tex)
            self._full_refs[name] = ref         # may be None if register fails
        return self._full_refs.get(name)

    @staticmethod
    def _register_texture(panda_tex) -> Optional[object]:
        """Register a Panda3D Texture with p3dimgui and return an ImTextureRef."""
        try:
            # `base` is a Panda3D builtin set by ShowBase on startup.
            return base.imgui.loadTexture(panda_tex)  # noqa: F821
        except AttributeError:
            # base.imgui not yet initialised.
            return None
        except Exception:
            return None
