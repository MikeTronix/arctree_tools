"""Bind bake-time silhouette POM on unique wall maps that have a height sibling."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from passages_tool.renderer.shader_probe import SHADER_DIR
from passages_tool.textures.band_compose import STYLE_CACHE_DIR
from passages_tool.textures.style import StylePack


def height_sibling_path(texture_dir: Path, diffuse_name: str) -> Optional[Path]:
    rel = str(diffuse_name).replace("\\", "/").lstrip("/")
    if not rel.lower().endswith(".png"):
        return None
    h_rel = rel[:-4] + "_h.png"
    # Prefer next to the diffuse under texture_dir.
    for candidate in (
        Path(texture_dir) / h_rel,
        Path(texture_dir) / Path(rel).name.replace(".png", "_h.png"),
        Path(h_rel),
    ):
        if candidate.is_file():
            return candidate
    return None


def _load_pom_shader():
    from panda3d.core import Shader

    vert = SHADER_DIR / "pom.vert.glsl"
    frag = SHADER_DIR / "pom.frag.glsl"
    if not vert.is_file() or not frag.is_file():
        return None
    return Shader.make(
        Shader.SL_GLSL, vert.read_text(encoding="utf-8"), frag.read_text(encoding="utf-8")
    )


def apply_style_pom(
    scene_root: Any,
    level: Any,
    texture_dir: Path,
    loader: Any,
    pack: Optional[StylePack] = None,
) -> int:
    """Override auto-shader on nodes whose diffuse has a ``*_h.png``. Returns binds."""
    tex_dir = Path(texture_dir)
    want = True
    if pack is not None:
        want = bool(pack.niche.pom) or bool(getattr(level.meta, "pom_enabled", False))
    elif not getattr(level.meta, "pom_enabled", False):
        want = False
    if not want:
        return 0
    shader = _load_pom_shader()
    if shader is None:
        return 0
    scale = 0.35
    if pack is not None:
        scale = float(pack.niche.height_scale_m)
    if getattr(level.meta, "pom_enabled", False) and pack is not None:
        scale = max(scale, float(pack.niche.height_scale_m))
    ppm = float(level.meta.pixels_per_meter) or 256.0
    bound = 0
    from panda3d.core import Filename, SamplerState, Vec2

    for np in scene_root.find_all_matches("**"):
        tex = np.get_texture() if hasattr(np, "get_texture") else None
        if tex is None:
            continue
        fn = ""
        try:
            fn = str(tex.get_filename())
        except Exception:
            fn = ""
        if STYLE_CACHE_DIR not in fn.replace("\\", "/") and STYLE_CACHE_DIR not in str(
            getattr(tex, "name", "")
        ):
            # Still try sibling from filename
            pass
        hpath = height_sibling_path(tex_dir, fn) if fn else None
        if hpath is None:
            name = Path(fn).name if fn else ""
            if name:
                hpath = height_sibling_path(tex_dir, f"{STYLE_CACHE_DIR}/{name}")
        if hpath is None or not hpath.is_file():
            continue
        try:
            htex = loader.load_texture(Filename.from_os_specific(str(hpath)), okMissing=False)
        except Exception:
            continue
        htex.set_minfilter(SamplerState.FT_linear)
        htex.set_magfilter(SamplerState.FT_linear)
        htex.set_wrap_u(SamplerState.WM_clamp)
        htex.set_wrap_v(SamplerState.WM_clamp)
        sx = max(1, int(htex.get_x_size()))
        sy = max(1, int(htex.get_y_size()))
        np.set_shader(shader)
        np.set_shader_input("heightTex", htex)
        np.set_shader_input("uHeightScale", scale)
        np.set_shader_input("uSizeMeters", Vec2(sx / ppm, sy / ppm))
        bound += 1
    return bound
