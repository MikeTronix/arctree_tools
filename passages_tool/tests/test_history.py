"""
tests/test_history.py — Unit tests for the undo/redo History stack.
"""
from passages_tool.editor.history import History


def test_initial_state():
    h = History()
    assert not h.can_undo()
    assert not h.can_redo()
    assert h.undo_count == 0
    assert h.redo_count == 0


def test_push_enables_undo():
    h = History()
    h.push({"v": 1})
    assert h.can_undo()
    assert not h.can_redo()


def test_undo_returns_snapshot():
    h = History()
    snap = {"v": 1}
    h.push(snap)
    restored = h.undo({"v": 2})   # current state is v=2
    assert restored == {"v": 1}


def test_undo_enables_redo():
    h = History()
    h.push({"v": 1})
    h.undo({"v": 2})
    assert h.can_redo()
    assert not h.can_undo()


def test_redo_returns_snapshot():
    h = History()
    h.push({"v": 1})
    undone = h.undo({"v": 2})       # v=1 goes to redo; returns v=1
    restored = h.redo(undone)       # should give us back the state after the action
    assert restored == {"v": 2}


def test_undo_redo_undo_restores_intermediate():
    """Redo must push current onto undos so the next undo does not skip a state."""
    h = History()
    h.push({"v": 0})   # before action A (state 0 → 1)
    h.push({"v": 1})   # before action B (state 1 → 2)
    s1 = h.undo({"v": 2})
    assert s1 == {"v": 1}
    s2 = h.redo(s1)
    assert s2 == {"v": 2}
    s1_again = h.undo(s2)
    assert s1_again == {"v": 1}
    assert h.can_undo()
    s0 = h.undo(s1_again)
    assert s0 == {"v": 0}


def test_new_push_clears_redo():
    h = History()
    h.push({"v": 1})
    h.undo({"v": 2})       # now can redo
    h.push({"v": 3})       # new action clears redo stack
    assert not h.can_redo()


def test_undo_on_empty_returns_none():
    h = History()
    assert h.undo({"v": 0}) is None


def test_redo_on_empty_returns_none():
    h = History()
    assert h.redo({"v": 0}) is None


def test_clear():
    h = History()
    h.push({"v": 1})
    h.push({"v": 2})
    h.clear()
    assert not h.can_undo()
    assert not h.can_redo()


def test_max_size_respected():
    h = History(max_size=3)
    for i in range(10):
        h.push({"v": i})
    assert h.undo_count <= 3
