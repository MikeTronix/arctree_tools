"""
converter/__main__.py
─────────────────────
CLI entry point to convert level JSON files into .egg files.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from passages_tool.converter.scene_builder import build_scene
from passages_tool.io.level_format import LevelIOError, load


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Passages level JSON into Panda3D .egg meshes."
    )
    parser.add_argument(
        "level_file", type=str, help="Path to input level .passages.json file."
    )
    parser.add_argument(
        "output_dir", type=str, help="Path to output directory for .egg files."
    )
    parser.add_argument(
        "--textures",
        type=str,
        default=None,
        help="Optional path to texture directory to inspect image dimensions.",
    )

    args = parser.parse_args()

    level_path = Path(args.level_file)
    output_dir = Path(args.output_dir)
    tex_dir = Path(args.textures) if args.textures else None

    if not level_path.is_file():
        print(f"Error: Level file not found: {level_path}", file=sys.stderr)
        sys.exit(1)

    if tex_dir and not tex_dir.is_dir():
        print(f"Error: Texture directory not found: {tex_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading level: {level_path}")
    try:
        level = load(level_path)
    except LevelIOError as e:
        print(f"Error loading level: {e}", file=sys.stderr)
        sys.exit(1)

    print("Building 3D scene geometry...")
    scene_path = build_scene(level, output_dir, tex_dir)
    print(f"Success. Combined scene file exported to: {scene_path}")


if __name__ == "__main__":
    main()
