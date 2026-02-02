"""Undo stack — tracks corrections for undo/rethink functionality."""
from dataclasses import dataclass, field
from typing import Optional
from collections import deque


@dataclass
class CorrectionEntry:
    original: str       # what the user typed
    corrected: str      # what we replaced it with
    char_count: int     # number of characters replaced (for backspace count)
    context: str = ""   # surrounding context


class UndoStack:
    """Maintains a stack of recent corrections for undo/rethink."""

    def __init__(self, max_size: int = 50):
        self._stack: deque[CorrectionEntry] = deque(maxlen=max_size)

    def push(self, entry: CorrectionEntry):
        self._stack.append(entry)

    def pop(self) -> Optional[CorrectionEntry]:
        if self._stack:
            return self._stack.pop()
        return None

    def peek(self) -> Optional[CorrectionEntry]:
        if self._stack:
            return self._stack[-1]
        return None

    def clear(self):
        self._stack.clear()

    @property
    def size(self) -> int:
        return len(self._stack)
