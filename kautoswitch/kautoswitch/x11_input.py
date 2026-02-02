"""X11 global keyboard input listener using XRecord extension."""
import threading
import logging
from typing import Callable, Optional

from Xlib import X, XK, display
from Xlib.ext import record
from Xlib.protocol import rq

logger = logging.getLogger(__name__)

# Keysym ranges for common characters
_PRINTABLE_MIN = 0x0020
_PRINTABLE_MAX = 0x007E
_CYRILLIC_MIN = 0x06A1
_CYRILLIC_MAX = 0x06FF
_BACKSPACE = XK.XK_BackSpace
_RETURN = XK.XK_Return
_SPACE = XK.XK_space
_TAB = XK.XK_Tab
_ESCAPE = XK.XK_Escape


class X11KeyListener:
    """Listens to global keyboard events via XRecord.

    Calls on_key_press(char) for printable characters,
    on_backspace() for backspace, on_special(keysym) for others.
    """

    def __init__(
        self,
        on_key_char: Callable[[str], None],
        on_backspace: Callable[[], None],
        on_special: Optional[Callable[[int, int], None]] = None,
    ):
        self._on_key_char = on_key_char
        self._on_backspace = on_backspace
        self._on_special = on_special
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._record_display = None
        self._local_display = None
        self._ctx = None
        self._suppressed = False  # flag to ignore events during replacement
        self._suppress_count = 0  # expected synthetic events remaining
        self._suppress_lock = threading.Lock()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._record_display and self._ctx:
            try:
                self._record_display.record_disable_context(self._ctx)
                self._record_display.flush()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2.0)

    @property
    def suppressed(self):
        return self._suppressed

    @suppressed.setter
    def suppressed(self, val: bool):
        self._suppressed = val

    def begin_suppress(self, expected_events: int = 0):
        """Begin suppression of synthetic events during replacement.

        Args:
            expected_events: Number of synthetic key events expected.
        """
        with self._suppress_lock:
            self._suppressed = True
            self._suppress_count = expected_events
            logger.debug("Suppression ON — expecting %d synthetic events", expected_events)

    def end_suppress(self):
        """End suppression after replacement is complete."""
        with self._suppress_lock:
            self._suppressed = False
            remaining = self._suppress_count
            self._suppress_count = 0
            if remaining > 0:
                logger.debug("Suppression OFF — %d events were not seen (ok)", remaining)

    def _count_suppressed_event(self):
        """Decrement the expected synthetic event counter."""
        with self._suppress_lock:
            if self._suppress_count > 0:
                self._suppress_count -= 1

    def _run(self):
        try:
            self._record_display = display.Display()
            self._local_display = display.Display()

            ctx = self._record_display.record_create_context(
                0,
                [record.AllClients],
                [{
                    'core_requests': (0, 0),
                    'core_replies': (0, 0),
                    'ext_requests': (0, 0, 0, 0),
                    'ext_replies': (0, 0, 0, 0),
                    'delivered_events': (0, 0),
                    'device_events': (X.KeyPress, X.KeyRelease),
                    'errors': (0, 0),
                    'client_started': False,
                    'client_died': False,
                }]
            )
            self._ctx = ctx

            self._record_display.record_enable_context(ctx, self._handle_event)
            self._record_display.record_free_context(ctx)
        except Exception as e:
            logger.error("XRecord listener failed: %s", e)
            self._running = False

    def _handle_event(self, reply):
        if reply.category != record.FromServer:
            return
        if reply.client_swapped:
            return
        if not len(reply.data) or reply.data[0] == 0:
            return

        data = reply.data
        while len(data):
            event, data = rq.EventField(None).parse_binary_value(
                data, self._record_display.display, None, None
            )

            if event.type == X.KeyPress:
                if self._suppressed:
                    self._count_suppressed_event()
                    continue
                self._process_keypress(event)

    def _process_keypress(self, event):
        keycode = event.detail
        state = event.state

        # Get keysym considering modifiers
        keysym = self._local_display.keycode_to_keysym(keycode, 0)
        if state & X.ShiftMask:
            keysym_shift = self._local_display.keycode_to_keysym(keycode, 1)
            if keysym_shift:
                keysym = keysym_shift

        if keysym == _BACKSPACE:
            self._on_backspace()
            return

        # Check for special/modifier keys — report to hotkey handler
        if self._on_special:
            ctrl = bool(state & X.ControlMask)
            shift = bool(state & X.ShiftMask)
            if ctrl or keysym in (XK.XK_F1, XK.XK_F2, XK.XK_F3, XK.XK_F4,
                                   XK.XK_F5, XK.XK_F6, XK.XK_F7, XK.XK_F8,
                                   XK.XK_F9, XK.XK_F10, XK.XK_F11, XK.XK_F12):
                self._on_special(keysym, state)
                return

        # Convert keysym to character
        char = self._keysym_to_char(keysym)
        if char:
            self._on_key_char(char)

    def _keysym_to_char(self, keysym: int) -> Optional[str]:
        """Convert X keysym to Unicode character."""
        # Latin range
        if _PRINTABLE_MIN <= keysym <= _PRINTABLE_MAX:
            return chr(keysym)

        # Cyrillic range (X11 keysyms for Cyrillic are 0x6xx)
        if _CYRILLIC_MIN <= keysym <= _CYRILLIC_MAX:
            # Map Xlib Cyrillic keysyms to Unicode
            # Cyrillic_io (ё) = 0x06A3 → U+0451
            # Cyrillic_a = 0x06C1 → U+0430, etc.
            return self._cyrillic_keysym_to_unicode(keysym)

        # Unicode keysyms (0x01xxxxxx)
        if keysym > 0x01000000:
            return chr(keysym - 0x01000000)

        # Space, tab, return
        if keysym == _SPACE:
            return ' '
        if keysym == _TAB:
            return '\t'
        if keysym == _RETURN:
            return '\n'

        return None

    @staticmethod
    def _cyrillic_keysym_to_unicode(keysym: int) -> Optional[str]:
        """Map X11 Cyrillic keysym to Unicode codepoint."""
        # X11 Cyrillic keysym mapping table
        _MAP = {
            0x06A1: 0x0452, 0x06A2: 0x0453, 0x06A3: 0x0451,
            0x06A4: 0x0454, 0x06A5: 0x0455, 0x06A6: 0x0456,
            0x06A7: 0x0457, 0x06A8: 0x0458, 0x06A9: 0x0459,
            0x06AA: 0x045A, 0x06AB: 0x045B, 0x06AC: 0x045C,
            0x06AE: 0x045E, 0x06AF: 0x045F,
            0x06B0: 0x2116,  # №
            0x06B1: 0x0402, 0x06B2: 0x0403, 0x06B3: 0x0401,
            0x06B4: 0x0404, 0x06B5: 0x0405, 0x06B6: 0x0406,
            0x06B7: 0x0407, 0x06B8: 0x0408, 0x06B9: 0x0409,
            0x06BA: 0x040A, 0x06BB: 0x040B, 0x06BC: 0x040C,
            0x06BE: 0x040E, 0x06BF: 0x040F,
        }
        if keysym in _MAP:
            return chr(_MAP[keysym])

        # Standard Cyrillic block: 0x06C0-0x06DF → uppercase, 0x06E0-0x06FF → lowercase
        if 0x06C0 <= keysym <= 0x06CF:
            return chr(keysym - 0x06C0 + 0x0410)  # А-П
        if 0x06D0 <= keysym <= 0x06DF:
            return chr(keysym - 0x06D0 + 0x0420)  # Р-Я
        if 0x06E0 <= keysym <= 0x06EF:
            return chr(keysym - 0x06E0 + 0x0430)  # а-п
        if 0x06F0 <= keysym <= 0x06FF:
            return chr(keysym - 0x06F0 + 0x0440)  # р-я

        return None
