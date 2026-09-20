"""Phase 0 shader probe — CPU-safe tests. GPU run is opt-in (PASSAGES_GPU=1)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from passages_tool.renderer.shader_probe import (
    SHADER_DIR,
    _decide_path,
    mean_is_red,
)


def test_probe_shaders_exist():
    for name in (
        "probe_const.vert.glsl",
        "probe_const.frag.glsl",
        "probe_array.vert.glsl",
        "probe_array.frag.glsl",
    ):
        assert (SHADER_DIR / name).is_file(), name


def test_mean_is_red_tolerance():
    assert mean_is_red((1.0, 0.0, 0.0))
    assert mean_is_red((1.0 - 2 / 255, 0.0, 0.0))
    assert not mean_is_red((0.0, 0.0, 0.0))  # July 2026 cleared black
    assert not mean_is_red((0.5, 0.0, 0.0))


def test_decide_path_table():
    assert _decide_path({"A": True, "B": True, "C": False, "auto_extra_stage": True}) == (
        "custom_shader_offscreen"
    )
    assert _decide_path({"A": False, "B": True, "C": False, "auto_extra_stage": True}) == (
        "custom_shader_hidden_buffer"
    )
    assert _decide_path({"A": False, "B": False, "C": True, "auto_extra_stage": False}) == (
        "custom_shader_hidden_window"
    )
    assert _decide_path(
        {"A": False, "B": False, "C": False, "auto_extra_stage": True}
    ) == "cpu_expand_auto_parallax"
    assert _decide_path(
        {"A": False, "B": False, "C": False, "auto_extra_stage": False}
    ) == "cpu_expand_no_pom"


@pytest.mark.gpu
def test_host_a_constant_red_or_skip():
    if os.environ.get("PASSAGES_GPU") != "1":
        pytest.skip("set PASSAGES_GPU=1 to run the offscreen shader probe")
    from passages_tool.renderer.shader_probe import probe_constant_color

    detail = probe_constant_color("A")
    if not detail.get("ok") and "make_texture_buffer" in str(detail.get("error", "")):
        pytest.skip(f"buffer creation failed: {detail.get('error')}")
    # Do not skip a black clear — that *is* the July 2026 answer (fail).
    assert detail["ok"], detail
