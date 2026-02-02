"""X11 text replacer — sends synthetic key events via XTest."""
import time
import logging
import threading
from typing import Optional

from Xlib import X, XK, display
from Xlib.ext import xtest

logger = logging.getLogger(__name__)

# Key name to keysym mapping for special chars
_SPECIAL_KEYSYMS = {
    ' ': XK.XK_space,
    '\t': XK.XK_Tab,
    '\n': XK.XK_Return,
}


class X11Replacer:
    """Replaces text by sending synthetic backspaces then retyping."""

    def __init__(self):
        self._display: Optional[display.Display] = None
        self._replacing = threading.Event()  # set while replacement in progress

    @property
    def is_replacing(self) -> bool:
        return self._replacing.is_set()

    def _ensure_display(self):
        if self._display is None:
            self._display = display.Display()

    def replace_text(self, old_len: int, new_text: str, listener=None):
        """Replace old_len characters with new_text.

        Args:
            old_len: Number of characters to delete (backspaces to send).
            new_text: Text to type in place.
            listener: Optional X11KeyListener to suppress during replacement.
        """
        self._ensure_display()

        # Count total synthetic key events we'll generate
        # Each char = KeyPress + KeyRelease (+ shift pair if needed)
        # Each backspace = KeyPress + KeyRelease
        expected_events = old_len + len(new_text)

        # Suppress listener during replacement to avoid feedback loop
        self._replacing.set()
        if listener:
            listener.begin_suppress(expected_events)

        try:
            # Small delay to let any pending events settle
            time.sleep(0.01)

            # Send backspaces
            self._send_backspaces(old_len)

            # Small delay between delete and type
            time.sleep(0.01)

            # Type new text
            self._type_text(new_text)

            self._display.flush()

            # Wait for synthetic events to be processed by X server
            time.sleep(0.05)
        finally:
            self._replacing.clear()
            if listener:
                listener.end_suppress()

    def _send_backspaces(self, count: int):
        """Send N backspace key events."""
        backspace_code = self._display.keysym_to_keycode(XK.XK_BackSpace)
        for _ in range(count):
            xtest.fake_input(self._display, X.KeyPress, backspace_code)
            xtest.fake_input(self._display, X.KeyRelease, backspace_code)
        self._display.flush()

    def _type_text(self, text: str):
        """Type text by sending synthetic key events."""
        for char in text:
            self._type_char(char)

    def _type_char(self, char: str):
        """Type a single character via XTest."""
        keysym = self._char_to_keysym(char)
        if keysym is None:
            logger.warning("Cannot type character: %r", char)
            return

        keycode = self._display.keysym_to_keycode(keysym)
        if keycode == 0:
            # Try Unicode keysym
            keysym = 0x01000000 + ord(char)
            keycode = self._display.keysym_to_keycode(keysym)
            if keycode == 0:
                # Use xdotool fallback for Unicode
                self._type_unicode_char(char)
                return

        # Check if shift is needed
        need_shift = False
        if char.isupper() or char in '~!@#$%^&*()_+{}|:"<>?':
            # Check if keysym is in index 1 (shifted)
            keysym_unshifted = self._display.keycode_to_keysym(keycode, 0)
            keysym_shifted = self._display.keycode_to_keysym(keycode, 1)
            if keysym_shifted == keysym and keysym_unshifted != keysym:
                need_shift = True

        if need_shift:
            shift_code = self._display.keysym_to_keycode(XK.XK_Shift_L)
            xtest.fake_input(self._display, X.KeyPress, shift_code)

        xtest.fake_input(self._display, X.KeyPress, keycode)
        xtest.fake_input(self._display, X.KeyRelease, keycode)

        if need_shift:
            xtest.fake_input(self._display, X.KeyRelease, shift_code)

        self._display.flush()

    def _type_unicode_char(self, char: str):
        """Fallback: type a Unicode char via Ctrl+Shift+U method (GTK) or xdotool."""
        import subprocess
        try:
            subprocess.run(
                ['xdotool', 'type', '--clearmodifiers', char],
                timeout=1.0,
                capture_output=True,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("xdotool fallback failed for char: %r", char)

    @staticmethod
    def _char_to_keysym(char: str) -> Optional[int]:
        """Convert a character to X keysym."""
        if char in _SPECIAL_KEYSYMS:
            return _SPECIAL_KEYSYMS[char]

        # ASCII printable
        if 0x20 <= ord(char) <= 0x7E:
            return ord(char)

        # Cyrillic: use Unicode keysym encoding
        if '\u0400' <= char <= '\u04FF':
            return 0x01000000 + ord(char)

        # General Unicode
        return 0x01000000 + ord(char)
