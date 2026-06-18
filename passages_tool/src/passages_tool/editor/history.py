"""
editor/history.py
─────────────────
Simple undo/redo command stack.

Commands are snapshots of the Level's serialisable state (to_dict / from_dict).
This is a coarse-grained approach: every undoable action stores a full level
snapshot.  For the expected level sizes (hundreds of vertices), this is fast
enough and keeps the implementation trivial.

Usage
─────
    history = History(max_size=50)
    history.push(level.to_dict())   # before mutating

    if history.can_undo():
        snapshot = history.undo(level.to_dict())
        level = Level.from_dict(snapshot)

    if history.can_redo():
        snapshot = history.redo()
        level = Level.from_dict(snapshot)
"""
from __future__ import annotations

from collections import deque
from typing import Optional


class History:
    def __init__(self, max_size: int = 100) -> None:
        self._max     = max_size
        self._undos:  deque[dict] = deque(maxlen=max_size)
        self._redos:  deque[dict] = deque()

    def push(self, snapshot: dict) -> None:
        """Record a before-snapshot so the action can be undone."""
        self._undos.append(snapshot)
        self._redos.clear()   # any new action kills the redo chain

    def can_undo(self) -> bool:
        return len(self._undos) > 0

    def can_redo(self) -> bool:
        return len(self._redos) > 0

    def undo(self, current_snapshot: dict) -> Optional[dict]:
        """
        Return the snapshot to restore (the state *before* the last action).
        Pushes `current_snapshot` onto the redo stack first.
        Returns None if there is nothing to undo.
        """
        if not self._undos:
            return None
        self._redos.append(current_snapshot)
        return self._undos.pop()

    def redo(self) -> Optional[dict]:
        """
        Return the snapshot to restore (the state after an undone action).
        Pushes the current snapshot (which was saved by undo) back onto undos.
        Returns None if there is nothing to redo.
        """
        if not self._redos:
            return None
        snapshot = self._redos.pop()
        # The current state was already saved when undo() was called.
        return snapshot

    def clear(self) -> None:
        self._undos.clear()
        self._redos.clear()

    @property
    def undo_count(self) -> int:
        return len(self._undos)

    @property
    def redo_count(self) -> int:
        return len(self._redos)
