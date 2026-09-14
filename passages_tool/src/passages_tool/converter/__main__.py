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
from passages_tool.log import configure_cli, get_logger

log = get_logger("converter")


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
    configure_cli()

    level_path = Path(args.level_file)
    output_dir = Path(args.output_dir)
    tex_dir = Path(args.textures) if args.textures else None

    if not level_path.is_file():
        log.error("Error: Level file not found: %s", level_path)
        sys.exit(1)

    if tex_dir and not tex_dir.is_dir():
        log.error("Error: Texture directory not found: %s", tex_dir)
        sys.exit(1)

    log.info("Loading level: %s", level_path)
    try:
        level = load(level_path)
    except LevelIOError as e:
        log.error("Error loading level: %s", e)
        sys.exit(1)

    log.info("Building 3D scene geometry...")
    scene_path = build_scene(level, output_dir, tex_dir)
    log.info("Success. Combined scene file exported to: %s", scene_path)


if __name__ == "__main__":
    main()
