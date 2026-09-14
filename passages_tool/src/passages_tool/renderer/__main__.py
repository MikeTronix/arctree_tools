"""
renderer/__main__.py
────────────────────
CLI entry point to bake all viewpoints in a level.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from passages_tool.io.level_format import LevelIOError, load
from passages_tool.renderer.manifest import (
    build_manifest,
    find_missing_images,
    find_stale_images,
    save_manifest,
)
from passages_tool.converter.scene_builder import build_scene
from passages_tool.renderer.viewpoint_renderer import ViewpointRenderer



def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render all EyePath viewpoint transitions to PNG files."
    )
    parser.add_argument(
        "level_file", type=str, help="Path to input level .passages.json file."
    )
    parser.add_argument(
        "scene_dir",
        type=str,
        help="Path to directory containing compiled component .egg files.",
    )
    parser.add_argument(
        "output_dir", type=str, help="Target directory for rendered images."
    )
    parser.add_argument(
        "--force", action="store_true", help="Force re-rendering all images."
    )
    parser.add_argument(
        "--width", type=int, default=None, help="Render width (defaults to level parameter or 1024)."
    )
    parser.add_argument(
        "--height", type=int, default=None, help="Render height (defaults to level render_height, typically 576)."
    )
    parser.add_argument(
        "--textures",
        type=str,
        default="assets/sample_textures",
        help="Path to texture directory containing image files.",
    )

    args = parser.parse_args()

    level_path = Path(args.level_file)
    scene_dir = Path(args.scene_dir)
    output_dir = Path(args.output_dir)
    tex_dir = Path(args.textures) if args.textures else None

    if not level_path.is_file():
        print(f"Error: Level file not found: {level_path}", file=sys.stderr)
        sys.exit(1)

    if not scene_dir.is_dir():
        print(f"Error: Scene directory not found: {scene_dir}", file=sys.stderr)
        sys.exit(1)

    if tex_dir and not tex_dir.is_dir():
        print(f"Error: Texture directory not found: {tex_dir}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading level: {level_path}")
    try:
        level = load(level_path)
    except LevelIOError as e:
        print(f"Error loading level: {e}", file=sys.stderr)
        sys.exit(1)

    # 1. Build manifest
    manifest = build_manifest(level, output_dir, tex_dir)
    if not manifest.get("edges"):
        paths = level.eyepaths()
        has_eyepath = bool(paths)
        has_vertices = bool(paths and paths[0].vertices)
        has_edges = bool(paths and paths[0].edges)
        if not has_eyepath:
            print("Error: The level file has no EyePath polyline defined. Cannot render viewpoints.", file=sys.stderr)
        elif not has_vertices:
            print("Error: The EyePath polyline in the level file has no vertices.", file=sys.stderr)
        elif not has_edges:
            print("Error: The EyePath polyline in the level file has no edges defined.", file=sys.stderr)
        else:
            print("Error: No viewpoints could be generated for this level.", file=sys.stderr)
        sys.exit(1)

    save_path = output_dir / "manifest.json"
    save_manifest(manifest, save_path)
    print(f"Saved manifest skeleton to {save_path}")

    # 2. Check for missing images
    if args.force:
        to_render = list(manifest["edges"].keys())
    else:
        to_render = find_missing_images(manifest, output_dir)

    if not to_render:
        print("All viewpoints already rendered. Use --force to re-render.")
        sys.exit(0)

    # 3. Build scene geometry
    print("Building 3D scene geometry...")
    try:
        build_scene(level, scene_dir, tex_dir, write_combined=False)
    except Exception as e:
        print(f"Error compiling scene geometry: {e}", file=sys.stderr)
        sys.exit(1)

    # 4. Instantiate ViewpointRenderer and render each frame
    try:
        renderer = ViewpointRenderer(level, scene_dir, tex_dir)
    except Exception as e:
        print(f"Error initializing graphics renderer: {e}", file=sys.stderr)
        sys.exit(1)

    rendered_count = 0
    skipped_count = 0

    width = args.width if args.width is not None else level.meta.render_width
    height = args.height if args.height is not None else level.meta.render_height
    print(f"Target rendering resolution: {width}x{height}")

    try:
        # Extract edge indices from key (e.g. v0000_to_v0001 -> 0, 1)
        for i, key in enumerate(to_render):
            parts = key.split("_to_")
            v_from = int(parts[0][1:])
            v_to = int(parts[1][1:])

            dest_png = output_dir / f"render_{key}.png"
            print(f"[{i+1}/{len(to_render)}] Rendering {dest_png.name}...")

            ok = renderer.render_edge(
                v_from, v_to, dest_png, width, height
            )
            if ok:
                rendered_count += 1
                manifest["edges"][key]["rendered"] = True
            else:
                print(f"  Failed to render: {key}", file=sys.stderr)
                skipped_count += 1

        # Re-save manifest with updated viewpoint "rendered" statuses
        save_manifest(manifest, save_path)
        print("Updated manifest with rendered statuses.")

        # 5. Bake midpoint traversal frames
        print("\nBaking midpoint traversal frames...")
        paths = level.eyepaths()
        eyepath_pl = paths[0] if paths else None

        mid_rendered = 0
        mid_skipped = 0
        mid_failed = 0

        if eyepath_pl and eyepath_pl.edges:
            # Midpoint frames are undirected (shared by both travel directions):
            # bake one per edge using a sorted/undirected name.
            undirected = []
            _seen_mid = set()
            for a, b in eyepath_pl.edges:
                lo, hi = (a, b) if a <= b else (b, a)
                if (lo, hi) not in _seen_mid:
                    _seen_mid.add((lo, hi))
                    undirected.append((lo, hi))
            for idx, (v_from, v_to) in enumerate(undirected):
                key = f"v{v_from:04d}_to_v{v_to:04d}"
                dest_mid_png = output_dir / f"mid_{key}.png"

                needs_render = args.force or not dest_mid_png.is_file()
                if not needs_render:
                    mid_skipped += 1
                    continue

                print(f"[{idx+1}/{len(undirected)}] Rendering midpoint frame {dest_mid_png.name}...")
                ok = renderer.render_midpoint(
                    v_from, v_to, dest_mid_png, width, height
                )
                if ok:
                    mid_rendered += 1
                else:
                    print(f"  Failed to render midpoint: {key}", file=sys.stderr)
                    mid_failed += 1
            print(f"Midpoint frame baking completed. Rendered {mid_rendered} images. Skipped: {mid_skipped}. Failed: {mid_failed}.")
        else:
            print("No EyePath edges found. Skipping midpoint frame baking.")

        # 6. Final manifest rebuild to capture viewpoints and midpoints
        manifest = build_manifest(level, output_dir, tex_dir)
        save_manifest(manifest, save_path)
        print("Final manifest saved with all rendered assets.")

        stale = find_stale_images(manifest, output_dir)
        for stale_path in stale:
            try:
                stale_path.unlink()
                print(f"Removed stale render: {stale_path.name}")
            except OSError as e:
                print(f"Could not remove stale {stale_path.name}: {e}", file=sys.stderr)
    finally:
        renderer.close()

    print(
        f"Baking completed. Successfully rendered {rendered_count} static images. "
        f"Failed/Skipped: {skipped_count}."
    )


if __name__ == "__main__":
    main()
