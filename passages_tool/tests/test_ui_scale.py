"""CPU tests for Feature 12 UI scale (no ImGui / GPU)."""
from __future__ import annotations

from passages_tool.ui.scale import (
    apply_imgui_ui_scale,
    clamp_ui_scale,
    detect_os_ui_scale,
    resolve_ui_scale,
    scaled_px,
    snap_ui_scale_preset,
    style_sizes_scale_factor,
    ui_scale_from_state,
)


class _FakeStyle:
    def __init__(self) -> None:
        self.font_scale_main = 1.0
        self.factors: list[float] = []

    def scale_all_sizes(self, factor: float) -> None:
        self.factors.append(factor)


def test_clamp_ui_scale():
    assert clamp_ui_scale(1.25) == 1.25
    assert clamp_ui_scale(0.0) == 1.0
    assert clamp_ui_scale(5.0) == 2.0


def test_snap_presets():
    assert snap_ui_scale_preset(1.0) == 1.0
    assert snap_ui_scale_preset(1.1) == 1.0
    assert snap_ui_scale_preset(1.2) == 1.25
    assert snap_ui_scale_preset(1.375) == 1.5  # tie → larger
    assert snap_ui_scale_preset(3.0) == 2.0


def test_ui_scale_from_state():
    assert ui_scale_from_state({}) is None
    assert ui_scale_from_state(None) is None
    assert ui_scale_from_state({"ui_scale": 1.5}) == 1.5
    assert ui_scale_from_state({"ui_scale": True}) is None
    assert ui_scale_from_state({"ui_scale": "1.5"}) is None
    assert ui_scale_from_state({"ui_scale": 0}) == 1.0


def test_resolve_prefers_saved_over_os(monkeypatch):
    monkeypatch.setattr("passages_tool.ui.scale.detect_os_ui_scale", lambda: 2.0)
    assert resolve_ui_scale({"ui_scale": 1.25}) == 1.25
    assert resolve_ui_scale({}) == 2.0


def test_detect_os_ui_scale_from_dpi(monkeypatch):
    monkeypatch.setattr("passages_tool.ui.scale._windows_dpi", lambda: 144)
    assert detect_os_ui_scale() == 1.5
    monkeypatch.setattr("passages_tool.ui.scale._windows_dpi", lambda: None)
    assert detect_os_ui_scale() == 1.0


def test_style_sizes_scale_factor_is_relative():
    assert style_sizes_scale_factor(1.0, 1.0) is None
    assert style_sizes_scale_factor(1.5, 1.0) == 1.5
    assert abs(style_sizes_scale_factor(1.0, 2.0) - 0.5) < 1e-9


def test_apply_imgui_ui_scale_does_not_restack_every_call():
    style = _FakeStyle()
    applied = 1.0
    applied = apply_imgui_ui_scale(style, target=1.5, applied=applied)
    assert style.font_scale_main == 1.5
    assert style.factors == [1.5]
    applied = apply_imgui_ui_scale(style, target=1.5, applied=applied)
    assert style.factors == [1.5]
    applied = apply_imgui_ui_scale(style, target=2.0, applied=applied)
    assert style.font_scale_main == 2.0
    assert abs(style.factors[-1] - (2.0 / 1.5)) < 1e-9


def test_scaled_px():
    assert scaled_px(300, 1.0) == 300
    assert scaled_px(300, 2.0) == 600
    assert scaled_px(20, 0.0) == 20  # clamped to 1.0
