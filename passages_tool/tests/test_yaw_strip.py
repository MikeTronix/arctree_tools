"""CPU tests for yaw-strip unwrap math and stitching (no GPU)."""
from __future__ import annotations

import pytest
from PIL import Image

from passages_tool.renderer.yaw_strip import (
    FACE_YAWS_DEG,
    YAW_ORIGIN_DEG,
    look_at_from_yaw,
    stitch_cube_faces,
    yaw_strip_face_size,
    yaw_strip_filename,
    yaw_strip_size,
)


def test_default_strip_near_spec_sweet_spot():
    w, h = yaw_strip_size(1024, 576, 60.0)
    assert h == 341
    # 4 × 90° faces; width near 2048 (exact depends on VFOV aspect).
    assert 1800 <= w <= 2800
    assert w % 4 == 0


def test_face_yaws_cover_the_circle():
    assert FACE_YAWS_DEG == (0.0, 90.0, 180.0, 270.0)
    assert YAW_ORIGIN_DEG == -45.0


def test_look_at_from_yaw_plus_x():
    look = look_at_from_yaw((0.0, 0.0), 0.0)
    assert look[0] == pytest.approx(1.0)
    assert look[1] == pytest.approx(0.0)


def test_stitch_order_left_to_right():
    faces = [
        Image.new("RGB", (4, 2), c)
        for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0))
    ]
    strip = stitch_cube_faces(faces)
    assert strip.size == (16, 2)
    assert strip.getpixel((0, 0)) == (255, 0, 0)
    assert strip.getpixel((4, 0)) == (0, 255, 0)
    assert strip.getpixel((8, 0)) == (0, 0, 255)
    assert strip.getpixel((12, 0)) == (255, 255, 0)


def test_yaw_strip_filename():
    assert yaw_strip_filename(0) == "yaw_v0000.png"
    assert yaw_strip_filename(12) == "yaw_v0012.png"


def test_face_size_scales_with_height():
    a = yaw_strip_face_size(1024, 576, 60.0)
    b = yaw_strip_face_size(1024, 288, 60.0)
    assert b[1] == a[1] // 2 or b[1] == round(a[1] / 2)
