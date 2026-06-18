"""
io/level_format.py
──────────────────
JSON save/load for .passages.json level files.

Handles both v1 (legacy) and v2 files transparently.  V1 files are
migrated to the v2 data structure in memory on load; the original
file on disk is NOT automatically overwritten (save explicitly to upgrade).

All I/O is synchronous (file sizes are tiny).  Error handling uses
LevelIOError so the caller can display a message without crashing.
"""
from __future__ import annotations

import json
from pathlib import Path

from passages_tool.config import LEVEL_FILE_EXT, LEVEL_FILE_VERSION
from passages_tool.editor.level import Level


class LevelIOError(Exception):
    """Raised when a level file cannot be read or written."""


def save(level: Level, path: str | Path) -> None:
    """
    Serialise `level` to a JSON file at `path` (v2 format).
    Adds .passages.json extension if not already present.
    Raises LevelIOError on failure.
    """
    p = Path(path)
    if not p.name.endswith(LEVEL_FILE_EXT):
        p = p.with_suffix("").with_suffix("")   # strip double ext if any
        p = Path(str(p) + LEVEL_FILE_EXT)

    data = level.to_dict()
    try:
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as e:
        raise LevelIOError(f"Cannot write level: {e}") from e

    level.dirty = False


def load(path: str | Path) -> Level:
    """
    Deserialise a level from `path`.

    Accepts both v1 and v2 files:
    - v1 files are migrated to v2 in memory via Level.migrate_v1_to_v2().
    - v2 files are loaded directly.
    - Files newer than the current tool version raise LevelIOError.

    Raises LevelIOError on failure.
    """
    p = Path(path)
    if not p.is_file():
        raise LevelIOError(f"File not found: {p}")

    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as e:
        raise LevelIOError(f"Cannot read file: {e}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise LevelIOError(f"Invalid JSON: {e}") from e

    version = data.get("version", 0)

    if version > LEVEL_FILE_VERSION:
        raise LevelIOError(
            f"Level version {version} is newer than this tool "
            f"(max supported: {LEVEL_FILE_VERSION}). Please update the tool."
        )

    if version < 2:
        data = Level.migrate_v1_to_v2(data)

    try:
        return Level.from_dict(data)
    except Exception as e:
        raise LevelIOError(f"Failed to parse level data: {e}") from e
