"""
renderer/shader_probe.py
────────────────────────
Phase 0: does a custom GLSL shader write color into the same
make_texture_buffer path ViewpointRenderer uses?

Hosts (design_docs/passages_pom_metatexture_14SEP26.md Phase 0):
  A — ShowBase(windowType="offscreen")  (today's bake CLI)
  B — on-screen ShowBase + offscreen buffer  (editor preview)
  C — hidden on-screen window (undecorated, off-desktop origin)

Also probes sampler2DArray and ShaderGenerator + extra TextureStage.

Read-only. Writes TOOL_ROOT/shader_probe_result.json.

CLI:  python -m passages_tool.renderer.shader_probe
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Optional

from passages_tool.config import TOOL_ROOT

SHADER_DIR = Path(__file__).resolve().parent / "shaders"
PROBE_JSON = TOOL_ROOT / "shader_probe_result.json"
PROBE_SIZE = 64
RED_TOL = 2.0 / 255.0


def mean_is_red(rgb: tuple[float, float, float], tol: float = RED_TOL) -> bool:
    return abs(rgb[0] - 1.0) <= tol and rgb[1] <= tol and rgb[2] <= tol


def _pnm_mean(pnm) -> tuple[float, float, float]:
    w, h = pnm.get_x_size(), pnm.get_y_size()
    if w < 1 or h < 1:
        return (0.0, 0.0, 0.0)
    r = g = b = 0.0
    for y in range(h):
        for x in range(w):
            r += pnm.get_red(x, y)
            g += pnm.get_green(x, y)
            b += pnm.get_blue(x, y)
    n = float(w * h)
    return (r / n, g / n, b / n)


def _prc_quiet() -> None:
    from panda3d.core import loadPrcFileData

    loadPrcFileData("", "audio-library-name null")
    loadPrcFileData("", "notify-level-p3d warning")
    loadPrcFileData("", "notify-level warning")
    loadPrcFileData("", "show-frame-rate-meter false")
    loadPrcFileData("", "sync-video false")
    loadPrcFileData("", "textures-power-2 none")


def _make_base(host: str):
    from panda3d.core import loadPrcFileData, WindowProperties
    from direct.showbase.ShowBase import ShowBase

    _prc_quiet()
    if host == "A":
        return ShowBase(windowType="offscreen")
    if host == "C":
        loadPrcFileData("", f"win-size {PROBE_SIZE} {PROBE_SIZE}")
        loadPrcFileData("", "win-origin -32000 -32000")
        loadPrcFileData("", "undecorated true")
        base = ShowBase()
        return base
    # B: visible on-screen (may flash a window)
    loadPrcFileData("", f"win-size {PROBE_SIZE} {PROBE_SIZE}")
    base = ShowBase()
    if base.win is not None:
        props = WindowProperties()
        props.set_size(PROBE_SIZE, PROBE_SIZE)
        base.win.request_properties(props)
    return base


def _make_probe_card(parent, shader=None, texture=None, extra_stages=None):
    """XZ card at (0,5,0) facing the origin (camera at origin looks +Y)."""
    from panda3d.core import CardMaker

    cm = CardMaker("probe_card")
    cm.set_frame(-1, 1, -1, 1)
    card = parent.attach_new_node(cm.generate())
    card.set_pos(0, 5, 0)
    card.set_h(180)
    card.set_two_sided(True)
    if shader is not None:
        card.set_shader(shader)
    if texture is not None:
        card.set_texture(texture)
    if extra_stages:
        for ts, tex in extra_stages:
            card.set_texture(ts, tex)
    return card


def _buffer_screenshot(base, setup_card) -> tuple[bool, tuple[float, float, float], str]:
    """`setup_card(root)` attaches a card under `base.render`. Buffer cam looks +Y at it."""
    from panda3d.core import PNMImage, PerspectiveLens

    if base.win is None:
        return False, (0.0, 0.0, 0.0), "no win"
    buf = base.win.make_texture_buffer("probe_buf", PROBE_SIZE, PROBE_SIZE)
    if not buf:
        return False, (0.0, 0.0, 0.0), "make_texture_buffer failed"
    buf.set_clear_color((0.0, 1.0, 0.0, 1.0))
    buf.set_clear_color_active(True)
    cam = base.make_camera(buf)
    cam.reparent_to(base.render)
    cam.set_pos(0, 0, 0)
    cam.look_at(0, 5, 0)
    lens = PerspectiveLens()
    lens.set_fov(90, 90)
    lens.set_near_far(0.1, 50)
    cam.node().set_lens(lens)
    setup_card(base.render)
    base.graphicsEngine.render_frame()
    base.graphicsEngine.render_frame()
    pnm = PNMImage()
    ok = buf.get_screenshot(pnm)
    base.graphicsEngine.remove_window(buf)
    cam.remove_node()
    if not ok:
        return False, (0.0, 0.0, 0.0), "get_screenshot failed"
    return True, _pnm_mean(pnm), ""


def _load_shader(vert_name: str, frag_name: str):
    from panda3d.core import Shader

    vert = SHADER_DIR / vert_name
    frag = SHADER_DIR / frag_name
    if not vert.is_file() or not frag.is_file():
        return None
    # Shader.load searches the model path; make() compiles from source.
    return Shader.make(
        Shader.SL_GLSL, vert.read_text(encoding="utf-8"), frag.read_text(encoding="utf-8")
    )


def probe_constant_color(host: str) -> dict[str, Any]:
    """Render a constant-red GLSL card through make_texture_buffer on `host`."""
    out: dict[str, Any] = {"ok": False, "mean": [0.0, 0.0, 0.0], "error": ""}
    base = None
    try:
        base = _make_base(host)
        sh = _load_shader("probe_const.vert.glsl", "probe_const.frag.glsl")
        if sh is None:
            out["error"] = "Shader.make failed (probe_const)"
            return out
        grabbed, mean, err = _buffer_screenshot(
            base, lambda root: _make_probe_card(root, shader=sh)
        )
        out["mean"] = [round(mean[0], 4), round(mean[1], 4), round(mean[2], 4)]
        if not grabbed:
            out["error"] = err or "screenshot failed"
            return out
        out["ok"] = mean_is_red(mean)
        if not out["ok"]:
            out["error"] = f"not red (mean={out['mean']}); July 2026 failure mode is cleared black"
        return out
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        out["traceback"] = traceback.format_exc()
        return out
    finally:
        if base is not None:
            try:
                base.destroy()
            except Exception:
                pass


def probe_arrays() -> dict[str, Any]:
    """Sample a 2D array texture (#version 140) on an offscreen-buffer host A."""
    out: dict[str, Any] = {"ok": False, "mean": [0.0, 0.0, 0.0], "error": ""}
    base = None
    try:
        from panda3d.core import Texture

        base = _make_base("A")
        sh = _load_shader("probe_array.vert.glsl", "probe_array.frag.glsl")
        if sh is None:
            out["error"] = "Shader.make failed (probe_array)"
            return out
        tex = Texture("probe_array")
        tex.setup_2d_texture_array(4, 4, 1, Texture.T_unsigned_byte, Texture.F_rgba)
        tex.set_ram_image(bytes([255, 0, 0, 255]) * 16)
        grabbed, mean, err = _buffer_screenshot(
            base, lambda root: _make_probe_card(root, shader=sh, texture=tex)
        )
        out["mean"] = [round(mean[0], 4), round(mean[1], 4), round(mean[2], 4)]
        if not grabbed:
            out["error"] = err or "screenshot failed"
            return out
        out["ok"] = mean_is_red(mean)
        if not out["ok"]:
            out["error"] = f"array sample not red (mean={out['mean']})"
        return out
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        out["traceback"] = traceback.format_exc()
        return out
    finally:
        if base is not None:
            try:
                base.destroy()
            except Exception:
                pass


def probe_auto_extra_stage() -> dict[str, Any]:
    """ShaderGenerator + extra normal TextureStage still writes color (not black)."""
    out: dict[str, Any] = {"ok": False, "mean": [0.0, 0.0, 0.0], "error": ""}
    base = None
    try:
        from panda3d.core import Texture, TextureStage

        base = _make_base("A")
        diff = Texture("probe_diff")
        diff.setup_2d_texture(4, 4, Texture.T_unsigned_byte, Texture.F_rgba)
        diff.set_ram_image(bytes([255, 0, 0, 255]) * 16)
        nrm = Texture("probe_n")
        nrm.setup_2d_texture(4, 4, Texture.T_unsigned_byte, Texture.F_rgba)
        nrm.set_ram_image(bytes([128, 128, 255, 255]) * 16)
        ts = TextureStage("n")
        ts.set_mode(TextureStage.MNormal)

        def _setup(root):
            card = _make_probe_card(root, texture=diff, extra_stages=[(ts, nrm)])
            card.look_at(0, 0, 0)
            card.set_shader_auto()
            return card

        grabbed, mean, err = _buffer_screenshot(base, _setup)
        out["mean"] = [round(mean[0], 4), round(mean[1], 4), round(mean[2], 4)]
        if not grabbed:
            out["error"] = err or "screenshot failed"
            return out
        # Auto-shader lights may darken; require not-cleared (not near-black) and some red.
        out["ok"] = mean[0] > 0.15 and mean[1] < 0.2 and mean[2] < 0.2
        if not out["ok"]:
            out["error"] = f"auto+extra stage not visibly red (mean={out['mean']})"
        return out
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        out["traceback"] = traceback.format_exc()
        return out
    finally:
        if base is not None:
            try:
                base.destroy()
            except Exception:
                pass


def run_all() -> dict[str, Any]:
    result: dict[str, Any] = {
        "A": False,
        "B": False,
        "C": False,
        "arrays": False,
        "auto_extra_stage": False,
        "detail": {},
    }
    for host in ("A", "B", "C"):
        detail = probe_constant_color(host)
        result["detail"][host] = {k: v for k, v in detail.items() if k != "traceback"}
        if detail.get("traceback"):
            result["detail"][host]["traceback"] = detail["traceback"]
        result[host] = bool(detail.get("ok"))
    arr = probe_arrays()
    result["detail"]["arrays"] = {k: v for k, v in arr.items() if k != "traceback"}
    result["arrays"] = bool(arr.get("ok"))
    extra = probe_auto_extra_stage()
    result["detail"]["auto_extra_stage"] = {
        k: v for k, v in extra.items() if k != "traceback"
    }
    result["auto_extra_stage"] = bool(extra.get("ok"))
    result["path"] = _decide_path(result)
    return result


def _decide_path(result: dict[str, Any]) -> str:
    a, b, c = result["A"], result["B"], result["C"]
    if a:
        return "custom_shader_offscreen"
    if b:
        return "custom_shader_hidden_buffer"
    if c:
        return "custom_shader_hidden_window"
    if result["auto_extra_stage"]:
        return "cpu_expand_auto_parallax"
    return "cpu_expand_no_pom"


def write_result(result: dict[str, Any], path: Optional[Path] = None) -> Path:
    dest = path or PROBE_JSON
    dest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return dest


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--once"] and len(argv) >= 2:
        # Isolated child: one host, JSON on stdout.
        host = argv[1]
        if host == "arrays":
            json.dump(probe_arrays(), sys.stdout)
        elif host == "auto_extra_stage":
            json.dump(probe_auto_extra_stage(), sys.stdout)
        else:
            json.dump(probe_constant_color(host), sys.stdout)
        return 0

    print("[shader_probe] Running hosts A (offscreen), B (onscreen+buffer), C (hidden)...")
    result = run_all()
    dest = write_result(result)
    print(f"[shader_probe] Wrote {dest}")
    for key in ("A", "B", "C", "arrays", "auto_extra_stage"):
        flag = "PASS" if result[key] else "FAIL"
        err = result.get("detail", {}).get(key, {}).get("error", "")
        extra = f"  {err}" if err else ""
        print(f"  {key:18} {flag}{extra}")
    print(f"  path               {result['path']}")
    return 0 if result["A"] or result["B"] or result["C"] else 1


if __name__ == "__main__":
    sys.exit(main())
