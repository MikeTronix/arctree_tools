"""
renderer/convert_to_jpeg.py
───────────────────────────
CLI tool to convert offline rendered PNGs to shipping JPEGs, checking for transparency.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from PIL import Image


def convert_renders(
    input_dir: Path, output_dir: Path, quality: int = 92
) -> int:
    """
    Convert all PNG images in input_dir to JPEGs in output_dir.
    Warns if any transparent pixels are detected.
    Copies manifest.json if present.
    Returns the count of converted images.
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    if not input_path.is_dir():
        raise ValueError(f"Input directory does not exist: {input_path}")

    output_path.mkdir(parents=True, exist_ok=True)

    # 1. Convert PNGs to JPGs
    count = 0
    for file_path in sorted(input_path.iterdir()):
        if file_path.suffix.lower() == ".png":
            try:
                with Image.open(file_path) as img:
                    # Check for alpha channel
                    has_alpha = False
                    alpha_min = 255

                    if img.mode in ("RGBA", "LA") or (
                        "transparency" in img.info
                    ):
                        rgba = img.convert("RGBA")
                        alpha = rgba.getchannel("A")
                        extrema = alpha.getextrema()
                        if extrema and extrema[0] < 255:
                            has_alpha = True
                            alpha_min = extrema[0]

                    if has_alpha:
                        print(
                            f"Warning: {file_path.name} contains transparent pixels! "
                            f"(Minimum alpha: {alpha_min})",
                            file=sys.stderr,
                        )
                        # Composite over a black background as a safety fallback
                        background = Image.new("RGB", img.size, (0, 0, 0))
                        background.paste(rgba, mask=alpha)
                        final_img = background
                    else:
                        final_img = img.convert("RGB")

                    dest_path = output_path / (file_path.stem + ".jpg")
                    final_img.save(dest_path, "JPEG", quality=quality)
                    count += 1
            except Exception as e:
                print(
                    f"Error converting {file_path.name}: {e}", file=sys.stderr
                )

    # 2. Copy manifest.json if present
    manifest_src = input_path / "manifest.json"
    if manifest_src.is_file():
        shutil.copy2(manifest_src, output_path / "manifest.json")
        print("Copied manifest.json to shipping folder.")

    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert rendered PNGs to shipping JPEGs with transparency warnings."
    )
    parser.add_argument(
        "input_dir", type=str, help="Directory containing rendered PNGs."
    )
    parser.add_argument(
        "output_dir", type=str, help="Target directory for JPEGs."
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=92,
        help="JPEG output quality (1-100, default 92).",
    )

    args = parser.parse_args()

    try:
        count = convert_renders(
            Path(args.input_dir), Path(args.output_dir), args.quality
        )
        print(f"Successfully converted {count} images.")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
