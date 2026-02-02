"""Text buffer — accumulates keystrokes, tracks word boundaries."""


class TextBuffer:
    """Maintains the current typing buffer for correction analysis.

    Accumulates characters as they are typed. On word boundary (space,
    punctuation, etc.), the completed word is emitted for correction.
    Handles backspace properly.
    """

    WORD_BOUNDARIES = set(' \t\n.,;:!?()[]{}"\'/\\-=+@#$%^&*~`<>|')

    def __init__(self):
        self._current_word: list[str] = []
        self._current_line: list[str] = []  # full line for context
        self._word_start_pos: int = 0  # character position where current word started

    def add_char(self, char: str) -> str | None:
        """Add a character. Returns completed word if boundary hit, else None."""
        if char in self.WORD_BOUNDARIES:
            word = self.get_current_word()
            self._current_line.append(''.join(self._current_word))
            self._current_line.append(char)
            self._current_word.clear()
            if word:
                return word
            return None

        self._current_word.append(char)
        return None

    def handle_backspace(self):
        """Handle backspace key — remove last character from buffer."""
        if self._current_word:
            self._current_word.pop()
        elif self._current_line:
            self._current_line.pop()

    def get_current_word(self) -> str:
        """Get the current (incomplete) word."""
        return ''.join(self._current_word)

    def get_current_word_len(self) -> int:
        """Get length of current word buffer."""
        return len(self._current_word)

    def get_context(self) -> str:
        """Get recent line context for AI."""
        return ''.join(self._current_line) + ''.join(self._current_word)

    def clear(self):
        """Clear the buffer completely."""
        self._current_word.clear()
        self._current_line.clear()

    def clear_word(self):
        """Clear only the current word."""
        self._current_word.clear()

    def replace_current_word(self, new_word: str):
        """Replace the current word buffer content (after correction applied externally)."""
        self._current_word = list(new_word)

    def force_complete(self) -> str | None:
        """Force-complete the current word (for rethink hotkey)."""
        word = self.get_current_word()
        if word:
            self._current_line.append(word)
            self._current_word.clear()
            return word
        return None
