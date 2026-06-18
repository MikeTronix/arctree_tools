"""
tests/test_convert_to_jpeg.py
─────────────────────────────
Tests for the PNG-to-JPEG shipping conversion tool.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from passages_tool.renderer.convert_to_jpeg import convert_renders


def test_convert_opaque_png(tmp_path):
    input_dir = tmp_path / "renders"
    output_dir = tmp_path / "shipping"
    input_dir.mkdir()

    # Create a fully opaque red square PNG
    img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
    img_path = input_dir / "render_001.png"
    img.save(img_path, "PNG")

    # Run converter
    count = convert_renders(input_dir, output_dir, quality=90)
    assert count == 1

    dest_path = output_dir / "render_001.jpg"
    assert dest_path.is_file()

    # Check that it converted to RGB
    with Image.open(dest_path) as out_img:
        assert out_img.mode == "RGB"
        assert out_img.size == (100, 100)


def test_convert_transparent_png_warning(tmp_path, capsys):
    input_dir = tmp_path / "renders"
    output_dir = tmp_path / "shipping"
    input_dir.mkdir()

    # Create a PNG with a semi-transparent pixel (alpha=128)
    img = Image.new("RGBA", (10, 10), (255, 255, 255, 255))
    img.putpixel((5, 5), (0, 0, 0, 128))
    img_path = input_dir / "render_trans.png"
    img.save(img_path, "PNG")

    # Run converter
    count = convert_renders(input_dir, output_dir)
    assert count == 1

    # Verify that a warning was printed to stderr
    captured = capsys.readouterr()
    assert "Warning: render_trans.png contains transparent pixels!" in captured.err
    assert "Minimum alpha: 128" in captured.err

    dest_path = output_dir / "render_trans.jpg"
    assert dest_path.is_file()


def test_manifest_copy(tmp_path):
    input_dir = tmp_path / "renders"
    output_dir = tmp_path / "shipping"
    input_dir.mkdir()

    # Create manifest
    manifest_data = {"version": 1, "images": []}
    with open(input_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)

    convert_renders(input_dir, output_dir)
    assert (output_dir / "manifest.json").is_file()
