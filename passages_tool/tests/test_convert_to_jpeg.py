"""
tests/test_convert_to_jpeg.py
─────────────────────────────
Tests for the KTX2 / JPEG / PNG shipping conversion tool.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

from PIL import Image

from passages_tool.renderer.convert_to_jpeg import convert_renders


def test_convert_opaque_png_fallback(tmp_path):
    input_dir = tmp_path / "renders"
    output_dir = tmp_path / "shipping"
    input_dir.mkdir()

    # Create a fully opaque red square PNG
    img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
    img_path = input_dir / "render_001.png"
    img.save(img_path, "PNG")

    # Run converter mocking find_basisu to return None (fallback path)
    with patch("passages_tool.renderer.convert_to_jpeg.find_basisu", return_value=None):
        count = convert_renders(input_dir, output_dir, quality=90)
    
    assert count == 1
    dest_path = output_dir / "render_001.jpg"
    assert dest_path.is_file()

    # Check that it converted to RGB
    with Image.open(dest_path) as out_img:
        assert out_img.mode == "RGB"
        assert out_img.size == (100, 100)


def test_convert_transparent_png_fallback(tmp_path):
    input_dir = tmp_path / "renders"
    output_dir = tmp_path / "shipping"
    input_dir.mkdir()

    # Create a PNG with a semi-transparent pixel (alpha=128)
    img = Image.new("RGBA", (10, 10), (255, 255, 255, 255))
    img.putpixel((5, 5), (0, 0, 0, 128))
    img_path = input_dir / "render_trans.png"
    img.save(img_path, "PNG")

    # Run converter in fallback mode
    with patch("passages_tool.renderer.convert_to_jpeg.find_basisu", return_value=None):
        count = convert_renders(input_dir, output_dir)
        
    assert count == 1

    # Transparent fallback copies the source PNG directly to preserve alpha
    dest_path = output_dir / "render_trans.png"
    assert dest_path.is_file()


def test_manifest_rewriting_fallback(tmp_path):
    input_dir = tmp_path / "renders"
    output_dir = tmp_path / "shipping"
    input_dir.mkdir()

    # Create an opaque render and a transparent render
    img_opaque = Image.new("RGBA", (10, 10), (255, 0, 0, 255))
    img_opaque.save(input_dir / "render_v0000_to_v0001.png", "PNG")

    img_trans = Image.new("RGBA", (10, 10), (0, 0, 0, 0)) # Fully transparent
    img_trans.save(input_dir / "mid_v0000_to_v0001.png", "PNG")

    # Create manifest pointing to PNGs
    manifest_data = {
        "v0000_to_v0001": {
            "image_path": "render_v0000_to_v0001.png",
            "midpoint_image_path": "mid_v0000_to_v0001.png"
        }
    }
    with open(input_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)

    # Run in fallback mode
    with patch("passages_tool.renderer.convert_to_jpeg.find_basisu", return_value=None):
        convert_renders(input_dir, output_dir)
        
    # Read the rewritten manifest
    with open(output_dir / "manifest.json", "r", encoding="utf-8") as f:
        rewritten = json.load(f)

    # Verify extensions are updated to fallback (.jpg for backgrounds, .png for sprites/transparents)
    assert rewritten["v0000_to_v0001"]["image_path"] == "render_v0000_to_v0001.jpg"
    assert rewritten["v0000_to_v0001"]["midpoint_image_path"] == "mid_v0000_to_v0001.png"


def test_convert_with_basisu_active(tmp_path):
    input_dir = tmp_path / "renders"
    output_dir = tmp_path / "shipping"
    input_dir.mkdir()

    # Create opaque render and transparent render
    Image.new("RGBA", (10, 10), (255, 0, 0, 255)).save(input_dir / "render_v0000_to_v0001.png", "PNG")
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(input_dir / "mid_v0000_to_v0001.png", "PNG")

    manifest_data = {
        "v0000_to_v0001": {
            "image_path": "render_v0000_to_v0001.png",
            "midpoint_image_path": "mid_v0000_to_v0001.png"
        }
    }
    with open(input_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)

    # Run transcoder mocking basisu presence
    with patch("passages_tool.renderer.convert_to_jpeg.find_basisu", return_value="basisu_mock"), \
         patch("subprocess.run") as mock_run:
        convert_renders(input_dir, output_dir)
        
    # Verify basisu was executed for both files
    assert mock_run.call_count == 2
    
    # Check calls: mid_v0000_to_v0001.png is transparent (UASTC), render_v0000_to_v0001.png is opaque (ETC1S)
    call_0_args = mock_run.call_args_list[0][0][0]
    call_1_args = mock_run.call_args_list[1][0][0]
    
    if "mid_v0000_to_v0001.png" in str(call_0_args):
        mid_args = call_0_args
        render_args = call_1_args
    else:
        mid_args = call_1_args
        render_args = call_0_args

    assert "basisu_mock" in mid_args
    assert "-ktx2" in mid_args
    assert "-uastc" in mid_args # Transparent needs UASTC

    assert "basisu_mock" in render_args
    assert "-ktx2" in render_args
    assert "-uastc" not in render_args # Opaque doesn't need UASTC


    # Read rewritten manifest
    with open(output_dir / "manifest.json", "r", encoding="utf-8") as f:
        rewritten = json.load(f)

    # Verify both paths are mapped to .ktx2 in the manifest
    assert rewritten["v0000_to_v0001"]["image_path"] == "render_v0000_to_v0001.ktx2"
    assert rewritten["v0000_to_v0001"]["midpoint_image_path"] == "mid_v0000_to_v0001.ktx2"
