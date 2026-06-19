"""
renderer/convert_to_jpeg.py
───────────────────────────
CLI tool to convert offline rendered PNGs to shipping formats (KTX2, JPEG, PNG).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image


def find_basisu(custom_path: str | None = None) -> str | None:
    """Finds the basisu binary, looking at custom_path, local bin directory, and system PATH."""
    if custom_path:
        p = Path(custom_path)
        if p.is_file():
            return str(p)
        elif p.is_dir():
            binary = p / ("basisu.exe" if os.name == "nt" else "basisu")
            if binary.is_file():
                return str(binary)

    # Check local bin subdirectory (../../bin/basisu)
    local_bin = Path(__file__).parent.parent.parent / "bin" / ("basisu.exe" if os.name == "nt" else "basisu")
    if local_bin.is_file():
        return str(local_bin)

    # Fallback to system PATH
    return shutil.which("basisu")


def convert_renders(
    input_dir: Path, output_dir: Path, quality: int = 92, basisu_path: str | None = None
) -> int:
    """
    Convert all PNG images in input_dir to KTX2 in output_dir (using basisu).
    Generates JPEG/PNG fallbacks for device compatibility.
    Rewrites and copies manifest.json to point to compiled format.
    Returns the count of processed images.
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    if not input_path.is_dir():
        raise ValueError(f"Input directory does not exist: {input_path}")

    output_path.mkdir(parents=True, exist_ok=True)

    # Resolve basisu binary
    basisu_bin = find_basisu(basisu_path)
    if basisu_bin:
        print(f"Found Basis Universal transcoder at: {basisu_bin}")
    else:
        print("Warning: basisu executable not found in PATH or local bin/ directory.", file=sys.stderr)
        print("Skipping KTX2 supercompression, generating JPEG and PNG fallbacks only.", file=sys.stderr)

    count = 0
    compiled_formats = {}  # Maps PNG name to compiled extension ('.ktx2', '.jpg', or '.png')

    for file_path in sorted(input_path.iterdir()):
        if file_path.suffix.lower() == ".png":
            try:
                with Image.open(file_path) as img:
                    # Check for alpha channel
                    has_alpha = False
                    alpha_min = 255

                    if img.mode in ("RGBA", "LA") or ("transparency" in img.info):
                        rgba = img.convert("RGBA")
                        alpha = rgba.getchannel("A")
                        extrema = alpha.getextrema()
                        if extrema and extrema[0] < 255:
                            has_alpha = True
                            alpha_min = extrema[0]

                    if has_alpha:
                        # 1. Output KTX2 (UASTC mode for transparency)
                        if basisu_bin:
                            cmd = [
                                basisu_bin,
                                "-ktx2",
                                "-uastc",
                                "-file",
                                str(file_path),
                                "-output_dir",
                                str(output_path),
                            ]
                            subprocess.run(
                                cmd,
                                check=True,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                            compiled_formats[file_path.name] = ".ktx2"
                        else:
                            compiled_formats[file_path.name] = ".png"

                        # 2. Output PNG fallback
                        dest_png = output_path / file_path.name
                        shutil.copy2(file_path, dest_png)
                        count += 1
                    else:
                        # Opaque viewpoint or midpoint background
                        # 1. Output KTX2 (ETC1S mode for high compression)
                        if basisu_bin:
                            cmd = [
                                basisu_bin,
                                "-ktx2",
                                "-file",
                                str(file_path),
                                "-output_dir",
                                str(output_path),
                            ]
                            subprocess.run(
                                cmd,
                                check=True,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                            compiled_formats[file_path.name] = ".ktx2"
                        else:
                            compiled_formats[file_path.name] = ".jpg"

                        # 2. Output JPEG fallback
                        final_img = img.convert("RGB")
                        dest_jpg = output_path / (file_path.stem + ".jpg")
                        final_img.save(dest_jpg, "JPEG", quality=quality)
                        count += 1
            except Exception as e:
                print(
                    f"Error converting {file_path.name}: {e}", file=sys.stderr
                )

    # 3. Process and write manifest.json
    manifest_src = input_path / "manifest.json"
    if manifest_src.is_file():
        try:
            with open(manifest_src, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)

            # Rewrite image paths in manifest entries
            for key, entry in list(manifest_data.items()):
                # Resolve primary viewpoint image extension
                png_name = entry.get("image_path")
                if png_name and png_name in compiled_formats:
                    ext = compiled_formats[png_name]
                    stem = Path(png_name).stem
                    entry["image_path"] = stem + ext

                # Resolve midpoint transition image extension
                mid_png_name = entry.get("midpoint_image_path")
                if mid_png_name:
                    if mid_png_name in compiled_formats:
                        ext = compiled_formats[mid_png_name]
                        stem = Path(mid_png_name).stem
                        entry["midpoint_image_path"] = stem + ext
                    else:
                        # If midpoint PNG was recorded in manifest but file is missing
                        entry["midpoint_image_path"] = None

            dest_manifest = output_path / "manifest.json"
            with open(dest_manifest, "w", encoding="utf-8") as f:
                json.dump(manifest_data, f, indent=2)
            print("Successfully processed and wrote manifest.json to shipping folder.")
        except Exception as e:
            print(f"Error processing manifest: {e}", file=sys.stderr)

    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert rendered PNGs to shipping formats (KTX2 with JPEG/PNG fallbacks)."
    )
    parser.add_argument(
        "input_dir", type=str, help="Directory containing rendered PNGs."
    )
    parser.add_argument(
        "output_dir", type=str, help="Target directory for compiled outputs."
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=92,
        help="JPEG fallback output quality (1-100, default 92).",
    )
    parser.add_argument(
        "--basisu-path",
        type=str,
        default=None,
        help="Path to the basisu executable (binary or directory).",
    )

    args = parser.parse_args()

    try:
        count = convert_renders(
            Path(args.input_dir),
            Path(args.output_dir),
            args.quality,
            args.basisu_path,
        )
        print(f"Successfully processed {count} images.")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
