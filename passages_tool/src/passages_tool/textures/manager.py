"""
textures/manager.py
───────────────────
Texture loading and thumbnail cache.

TextureManager handles:
  - Scanning a directory for PNG/JPG images.
  - Loading them as Panda3D Texture objects (for rendering on tiles/polylines).
  - Generating Pillow-based thumbnail images and converting them to
    Panda3D Textures for display in the ImGui palette panel.

Usage
─────
    mgr = TextureManager()
    mgr.scan_directory("/path/to/textures")

    names = mgr.texture_names          # sorted list of relative names
    tex   = mgr.get_panda_texture(name)
    thumb = mgr.get_thumbnail_texture(name)   # THUMBNAIL_W × THUMBNAIL_H
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PIL import Image
from panda3d.core import (
    Filename,
    SamplerState,
    Texture,
    PNMImage,
)

from passages_tool.config import THUMBNAIL_H, THUMBNAIL_W

_SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tga"}


class TextureManager:
    def __init__(self) -> None:
        self._base_dir: Optional[Path]       = None
        self._names:    list[str]            = []
        self._panda_cache:     dict[str, Texture] = {}
        self._thumbnail_cache: dict[str, Texture] = {}

    # ── Directory scanning ────────────────────────────────────────────────────

    def scan_directory(self, directory: str | os.PathLike) -> None:
        """
        Scan `directory` for supported image files.
        Clears the existing cache when called.
        """
        self._base_dir = Path(directory)
        self._names.clear()
        self._panda_cache.clear()
        self._thumbnail_cache.clear()

        if not self._base_dir.is_dir():
            return

        for path in sorted(self._base_dir.iterdir()):
            if path.suffix.lower() in _SUPPORTED_EXTS:
                self._names.append(path.name)

    @property
    def texture_names(self) -> list[str]:
        return list(self._names)

    @property
    def base_dir(self) -> Optional[Path]:
        return self._base_dir

    # ── Panda3D textures ──────────────────────────────────────────────────────

    def get_panda_texture(self, name: str) -> Optional[Texture]:
        """
        Return a Panda3D Texture for `name`, loading from disk if needed.
        Returns None if the file cannot be found or loaded.
        """
        if name in self._panda_cache:
            return self._panda_cache[name]

        if self._base_dir is None:
            return None

        path = self._base_dir / name
        if not path.is_file():
            return None

        # Try standard loading first
        tex = Texture(name)
        ok = tex.read(Filename.fromOsSpecific(str(path)))
        if not ok:
            # FALLBACK: Try loading via Pillow (handles WebP mislabeled as PNG)
            try:
                img = Image.open(path)
                tex = self._pil_to_panda_texture(img, name)
            except Exception:
                return None

        if tex is not None:
            tex.setMinfilter(SamplerState.FT_linear_mipmap_linear)
            tex.setMagfilter(SamplerState.FT_linear)
            tex.setWrapU(SamplerState.WM_repeat)
            tex.setWrapV(SamplerState.WM_repeat)

            # Generate mipmaps if the filter needs them and we have a RAM image
            if tex.has_ram_image():
                tex.generate_ram_mipmap_images()

            # Register in TexturePool
            from panda3d.core import TexturePool
            
            # 1. Register under relative name (matching EGG file references)
            tex.set_fullpath(Filename(name))
            TexturePool.add_texture(tex)
            
            # 2. Register under absolute path
            tex_abs = tex.make_copy()
            tex_abs.set_fullpath(Filename.fromOsSpecific(str(path)))
            TexturePool.add_texture(tex_abs)

            self._panda_cache[name] = tex
            return tex

        return None


    # ── Thumbnail textures ────────────────────────────────────────────────────

    def get_thumbnail_texture(self, name: str) -> Optional[Texture]:
        """
        Return a thumbnail-sized Panda3D Texture for ImGui palette display.
        Thumbnails are generated via Pillow and cached in memory.
        Returns None if the source file cannot be loaded.
        """
        if name in self._thumbnail_cache:
            return self._thumbnail_cache[name]

        if self._base_dir is None:
            return None

        path = self._base_dir / name
        if not path.is_file():
            return None

        try:
            img = Image.open(path).convert("RGBA")
        except Exception:
            return None

        try:
            # Lanczos thumbnail preserving aspect ratio.
            img.thumbnail((THUMBNAIL_W, THUMBNAIL_H), Image.Resampling.LANCZOS)

            # Pad to exact THUMBNAIL_W x THUMBNAIL_H with transparent background.
            padded = Image.new("RGBA", (THUMBNAIL_W, THUMBNAIL_H), (0, 0, 0, 0))
            paste_x = (THUMBNAIL_W - img.width)  // 2
            paste_y = (THUMBNAIL_H - img.height) // 2
            padded.paste(img, (paste_x, paste_y))

            # Convert to Panda3D Texture.
            tex = self._pil_to_panda_texture(padded, f"thumb_{name}")
            if tex is None:
                return None
        except Exception:
            return None

        self._thumbnail_cache[name] = tex
        return tex

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _pil_to_panda_texture(img: Image.Image, name: str) -> Optional[Texture]:
        """
        Convert a Pillow RGBA image to a Panda3D Texture held entirely in RAM.

        Uses Texture.setup2dTexture() + setRamImage() which accepts raw bytes
        directly — avoids the broken StringStream/tex.read() path that was
        crashing by passing a stream where Texture.read() expects a Filename.

        PIL images are top-down (row 0 = top); Panda3D/OpenGL RAM images are
        bottom-up (row 0 = bottom), so we flip vertically before copying.
        """
        try:
            img = img.convert("RGBA")
            # Flip top-to-bottom to match Panda3D's bottom-up memory layout.
            flipped = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            raw = flipped.tobytes()   # RGBA, 1 byte per channel, bottom-up

            tex = Texture(name)
            tex.setup2dTexture(
                img.width, img.height,
                Texture.T_unsigned_byte,
                Texture.F_rgba,
            )
            tex.setRamImage(raw)
            tex.setMinfilter(SamplerState.FT_linear)
            tex.setMagfilter(SamplerState.FT_linear)
            return tex
        except Exception:
            return None


def preload_level_textures(level: Level, texture_dir: Path) -> None:
    """
    Preload all textures referenced by the level using TextureManager
    and register them in TexturePool under both relative name and absolute path
    to prevent Panda3D C++ loaders from attempting to read invalid/mislabeled files from disk.
    """
    from panda3d.core import getModelPath, Filename
    from passages_tool.editor.level import PolylineType

    # Resolve texture directory to an absolute path
    abs_texture_dir = Path(texture_dir).resolve().absolute()

    # Append to model path so Panda3D's internal loaders can resolve relative paths
    getModelPath().append_directory(Filename.from_os_specific(str(abs_texture_dir)))

    # Scan the level for all referenced textures
    textures_to_load = set()
    if level.meta.floor_texture:
        textures_to_load.add(level.meta.floor_texture)
    if level.meta.ceiling_texture:
        textures_to_load.add(level.meta.ceiling_texture)

    for pl in level.polylines.values():
        if pl.type == PolylineType.ARCH and pl.texture:
            textures_to_load.add(pl.texture)
        elif pl.type == PolylineType.WALL:
            for iv in pl.texture_intervals:
                if iv.texture:
                    textures_to_load.add(iv.texture)

    # Initialize a temporary TextureManager to load these textures robustly
    mgr = TextureManager()
    mgr.scan_directory(abs_texture_dir)
    for name in textures_to_load:
        mgr.get_panda_texture(name)

