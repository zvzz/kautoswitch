"""Core daemon — ties together input listener, buffer, corrector, replacer, undo."""
import threading
import logging
import time
from typing import Optional, List, Set

from Xlib import XK

from kautoswitch.buffer import TextBuffer
from kautoswitch.corrector import Corrector
from kautoswitch.replacer import X11Replacer
from kautoswitch.undo import UndoStack, CorrectionEntry
from kautoswitch.rules import RuleStore
from kautoswitch.config import Config
from kautoswitch.layout_map import detect_target_layout

logger = logging.getLogger(__name__)


class Daemon:
    """Background daemon managing keyboard interception and correction."""

    def __init__(self, config: Config):
        self.config = config
        self._running = False
        self._listener = None
        self._buffer = TextBuffer()
        self._replacer = X11Replacer()
        self._undo_stack = UndoStack()
        self._rules = RuleStore()
        self._corrector: Optional[Corrector] = None
        self._tinyllm = None
        self._api_client = None
        self._lock = threading.Lock()
        self._last_word_boundary: str = ""
        # Phrase tracking: recent words that were NOT individually corrected
        self._phrase_words: List[str] = []
        self._phrase_total_len: int = 0  # total chars typed including spaces
        # Idempotency guard: track last correction to prevent feedback loop
        self._last_correction: Optional[dict] = None  # {original, corrected, time}
        # Word finalization guard: lowercased words already corrected in this context
        self._finalized_words: Set[str] = set()
        # Input state machine: 'typing', 'word_finalized', 'idle', 'handoff'
        self._input_state: str = 'typing'
        # Deferred phrase correction timer
        self._phrase_timer: Optional[threading.Timer] = None
        self._phrase_cancel: threading.Event = threading.Event()
        # Handoff mode: after correction, stop all correction until new wrong-layout detected
        self._handoff_layout: Optional[str] = None  # layout we switched to
        # Layout switch request: daemon sets this, Qt main thread consumes it.
        # This is the ONLY way layout switching is communicated — daemon NEVER
        # calls X11/subprocess layout functions directly (segfault-safe).
        self._requested_layout: Optional[str] = None

    @property
    def running(self):
        return self._running

    @property
    def rules(self):
        return self._rules

    @property
    def undo_stack(self):
        return self._undo_stack

    def consume_layout_request(self) -> Optional[str]:
        """Consume and return any pending layout switch request.

        Called from Qt main thread via QTimer. Returns layout name
        ('us', 'ru') or None if no request pending.
        Thread-safe: reads and clears under lock.
        """
        with self._lock:
            layout = self._requested_layout
            self._requested_layout = None
            return layout

    def set_tinyllm(self, tinyllm):
        self._tinyllm = tinyllm
        if self._corrector:
            self._corrector.tinyllm = tinyllm

    def set_api_client(self, api_client):
        self._api_client = api_client
        if self._corrector:
            self._corrector.api_client = api_client

    def start(self):
        if self._running:
            return
        self._running = True

        self._corrector = Corrector(
            self.config,
            tinyllm=self._tinyllm,
            api_client=self._api_client,
        )

        try:
            from kautoswitch.x11_input import X11KeyListener
            self._listener = X11KeyListener(
                on_key_char=self._on_key_char,
                on_backspace=self._on_backspace,
                on_special=self._on_special,
            )
            self._listener.start()
            logger.info("Daemon started — X11 input listener active")
        except Exception as e:
            logger.error("Failed to start X11 listener: %s", e)
            self._running = False

    def stop(self):
        self._running = False
        self._cancel_phrase_timer()
        if self._listener:
            self._listener.stop()
        logger.info("Daemon stopped")

    def _on_key_char(self, char: str):
        """Called for each printable character typed."""
        if not self.config.enabled:
            return

        with self._lock:
            # Cancel any pending phrase timer — user is still typing
            self._cancel_phrase_timer()

            # In HANDOFF mode: just buffer characters, no correction.
            # Exit handoff when a new wrong-layout word is detected.
            if self._input_state == 'handoff':
                completed_word = self._buffer.add_char(char)
                if completed_word:
                    self._last_word_boundary = char
                    # Check if this word looks like wrong layout — exit handoff
                    from kautoswitch.layout_map import detect_layout_mismatch
                    mismatch = detect_layout_mismatch(completed_word)
                    if mismatch and mismatch in ('en_meant_ru', 'ru_meant_en'):
                        # New wrong-layout word detected — exit handoff, correct it
                        self._input_state = 'word_finalized'
                        self._handoff_layout = None
                        self._finalized_words.clear()
                        self._try_correct_word(completed_word)
                        self._schedule_phrase_correction()
                    else:
                        # Valid word in correct layout — stay in handoff
                        self._phrase_words.append(completed_word)
                        self._phrase_total_len += len(completed_word) + 1
                return

            self._input_state = 'typing'

            completed_word = self._buffer.add_char(char)
            if completed_word:
                self._last_word_boundary = char
                self._input_state = 'word_finalized'
                self._try_correct_word(completed_word)
                # Schedule deferred phrase correction
                self._schedule_phrase_correction()

    def _on_backspace(self):
        """Called when backspace is pressed."""
        with self._lock:
            self._cancel_phrase_timer()
            self._buffer.handle_backspace()

    def _on_special(self, keysym: int, state: int):
        """Called for special/hotkey key events."""
        ctrl = bool(state & 0x4)   # ControlMask
        shift = bool(state & 0x1)  # ShiftMask

        # Undo: Ctrl+/ (to avoid conflict with app Ctrl+Z)
        if ctrl and not shift and keysym == XK.XK_slash:
            self._do_undo()
            return

        # Rethink: Ctrl+Shift+/
        if ctrl and shift and keysym == XK.XK_slash:
            self._do_rethink()
            return

        # Toggle: Ctrl+Shift+P
        if ctrl and shift and keysym == XK.XK_p:
            self.config.enabled = not self.config.enabled
            logger.info("Toggled enabled: %s", self.config.enabled)
            return

        # Polish mode: Ctrl+Shift+L — one-shot cleanup of current line/selection
        if ctrl and shift and keysym == XK.XK_l:
            self._do_polish()
            return

        # Navigation/context-breaking keys → clear buffers
        if keysym in (XK.XK_Return, XK.XK_Escape, XK.XK_Home, XK.XK_End,
                       XK.XK_Left, XK.XK_Right, XK.XK_Up, XK.XK_Down,
                       XK.XK_Page_Up, XK.XK_Page_Down):
            with self._lock:
                self._cancel_phrase_timer()
                self._buffer.clear()
                self._phrase_words.clear()
                self._phrase_total_len = 0
                self._finalized_words.clear()
                self._input_state = 'typing'
                if self._corrector:
                    self._corrector.clear_context()

    def _cancel_phrase_timer(self):
        """Cancel any pending phrase correction timer."""
        self._phrase_cancel.set()
        if self._phrase_timer is not None:
            self._phrase_timer.cancel()
            self._phrase_timer = None

    def _schedule_phrase_correction(self):
        """Schedule deferred phrase correction if we have >=2 phrase words."""
        if len(self._phrase_words) < 2:
            return
        delay_sec = self.config.phrase_idle_delay_ms / 1000.0
        self._phrase_cancel = threading.Event()
        self._phrase_timer = threading.Timer(delay_sec, self._deferred_phrase_correction)
        self._phrase_timer.daemon = True
        self._phrase_timer.start()

    def _deferred_phrase_correction(self):
        """Run phrase correction after idle timeout. Runs on Timer thread."""
        with self._lock:
            # Check if cancelled or state changed
            if self._phrase_cancel.is_set():
                return
            if self._input_state == 'typing':
                return
            # Take snapshot
            words_snapshot = list(self._phrase_words)
            if len(words_snapshot) < 2:
                return

        # Run correction outside lock (may be slow)
        phrase_result = self._correct_phrase_with_timeout(words_snapshot)

        with self._lock:
            # Re-check cancel signal after correction completed
            if self._phrase_cancel.is_set():
                return
            if phrase_result is None:
                self._input_state = 'idle'
                return

            corrected_phrase, confidence = phrase_result
            original_phrase = ' '.join(words_snapshot)

            # Verify phrase words haven't changed while we were correcting
            if self._phrase_words != words_snapshot:
                return

            if (corrected_phrase != original_phrase and
                    confidence >= self.config.confidence_threshold):
                self._apply_phrase_correction(original_phrase, corrected_phrase)

            self._input_state = 'idle'

    def _is_idempotent(self, word: str) -> bool:
        """Check if this word matches the last correction output (feedback loop guard)."""
        if self._last_correction is None:
            return False
        lc = self._last_correction
        # Skip if word matches the corrected output of the last correction
        if word == lc['corrected'] or word.lower() == lc['corrected'].lower():
            elapsed = time.time() - lc['time']
            if elapsed < 2.0:  # within 2 seconds of last correction
                logger.debug("Idempotency guard: skipping %r (matches last correction output %r, %.1fs ago)",
                             word, lc['corrected'], elapsed)
                return True
        return False

    def _try_correct_word(self, word: str):
        """Attempt single-word correction on a completed word.

        Phrase correction is deferred to _deferred_phrase_correction.
        """
        # Idempotency guard: skip if this word is the output of the last correction
        if self._is_idempotent(word):
            self._phrase_words.clear()
            self._phrase_total_len = 0
            return

        # Finalization guard: skip if already corrected in this context
        if word.lower() in self._finalized_words:
            logger.debug("Finalization guard: skipping %r (already finalized)", word)
            self._phrase_words.append(word)
            self._phrase_total_len += len(word) + 1
            return

        # Check suppression rules
        if self._rules.is_suppressed(word):
            logger.debug("Suppressed by learned rule: %r", word)
            self._phrase_words.append(word)
            self._phrase_total_len += len(word) + 1
            return

        # Always add word to phrase buffer
        self._phrase_words.append(word)
        self._phrase_total_len += len(word) + 1  # +1 for boundary char

        # Single-word correction only (phrase is deferred)
        result = self._correct_with_timeout(word)
        if result is not None:
            corrected, confidence = result
            if corrected != word and confidence >= self.config.confidence_threshold:
                # Remove the word we just added to phrase buffer
                self._phrase_words.pop()
                self._phrase_total_len -= len(word) + 1
                self._apply_word_correction(word, corrected)
                # Clear phrase buffer since context is now different
                self._phrase_words.clear()
                self._phrase_total_len = 0
                return

    def _apply_phrase_correction(self, original_phrase: str, corrected_phrase: str):
        """Apply a phrase-level correction."""
        logger.info("Phrase correction: %r → %r", original_phrase, corrected_phrase)

        # Record last correction for idempotency guard
        # Store each corrected word so individual leaks are also caught
        corrected_words = corrected_phrase.split()
        if corrected_words:
            self._last_correction = {
                'original': original_phrase,
                'corrected': corrected_words[-1],  # last word most likely to leak
                'time': time.time(),
            }

        # Add all words (original and corrected) to finalization guard
        for w in original_phrase.split():
            self._finalized_words.add(w.lower())
        for w in corrected_words:
            self._finalized_words.add(w.lower())

        entry = CorrectionEntry(
            original=original_phrase,
            corrected=corrected_phrase,
            char_count=len(corrected_phrase),
        )
        self._undo_stack.push(entry)

        # Replace: delete all phrase chars + trailing boundary
        old_len = self._phrase_total_len
        new_text = corrected_phrase + self._last_word_boundary
        self._replacer.replace_text(old_len, new_text, listener=self._listener)

        # Signal layout switch intent — actual switch happens in Qt main thread
        target_layout = detect_target_layout(corrected_phrase)
        self._requested_layout = target_layout

        # Enter HANDOFF mode — stop all correction, let user type naturally
        self._input_state = 'handoff'
        self._handoff_layout = target_layout

        # Full buffer clear — prevents stale context from leaking
        self._buffer.clear()
        self._phrase_words.clear()
        self._phrase_total_len = 0

    def _apply_word_correction(self, original: str, corrected: str):
        """Apply a single-word correction."""
        logger.info("Correcting: %r → %r", original, corrected)

        # Record last correction for idempotency guard
        self._last_correction = {
            'original': original,
            'corrected': corrected,
            'time': time.time(),
        }

        # Add both original and corrected to finalization guard
        self._finalized_words.add(original.lower())
        self._finalized_words.add(corrected.lower())

        entry = CorrectionEntry(
            original=original,
            corrected=corrected,
            char_count=len(corrected),
        )
        self._undo_stack.push(entry)

        # Replace: delete the word + boundary char, then retype corrected + boundary
        old_len = len(original) + 1  # +1 for the boundary char
        new_text = corrected + self._last_word_boundary
        self._replacer.replace_text(old_len, new_text, listener=self._listener)

        # Signal layout switch intent — actual switch happens in Qt main thread
        target_layout = detect_target_layout(corrected)
        self._requested_layout = target_layout

        # Enter HANDOFF mode — stop all correction, let user type naturally
        self._input_state = 'handoff'
        self._handoff_layout = target_layout

        # Full buffer clear — prevents stale context from leaking
        self._buffer.clear()

    def _correct_with_timeout(self, word: str, context: str = "") -> Optional[tuple]:
        """Run single-word correction with hard timeout."""
        result = [None]
        timeout_sec = self.config.ai_timeout_ms / 1000.0

        def _run():
            try:
                result[0] = self._corrector.correct(word, context)
            except Exception as e:
                logger.error("Correction error: %s", e)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=timeout_sec)

        if thread.is_alive():
            logger.warning("Correction timed out for %r", word)
            return None

        return result[0]

    def _correct_phrase_with_timeout(self, words: List[str]) -> Optional[tuple]:
        """Run phrase-level correction with hard timeout."""
        result = [None]
        timeout_sec = self.config.ai_timeout_ms / 1000.0

        def _run():
            try:
                result[0] = self._corrector.correct_phrase(words)
            except Exception as e:
                logger.error("Phrase correction error: %s", e)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=timeout_sec)

        if thread.is_alive():
            logger.warning("Phrase correction timed out")
            return None

        return result[0]

    def _do_undo(self):
        """Undo the last auto-correction."""
        entry = self._undo_stack.pop()
        if entry is None:
            logger.debug("Nothing to undo")
            return

        logger.info("Undo: %r → %r", entry.corrected, entry.original)

        old_len = len(entry.corrected) + 1
        new_text = entry.original + " "
        self._replacer.replace_text(old_len, new_text, listener=self._listener)

        suppressed = self._rules.record_undo(entry.original)
        if suppressed:
            logger.info("Learned suppression rule for: %r", entry.original)

    def _do_rethink(self):
        """Rethink (re-run correction on) the last input."""
        entry = self._undo_stack.peek()
        if entry is None:
            word = self._buffer.force_complete()
            if word:
                self._try_correct_word(word)
            return

        result = self._correct_with_timeout(entry.original)
        if result is None:
            return

        corrected, confidence = result
        if corrected == entry.corrected:
            return

        logger.info("Rethink: %r → %r (was %r)", entry.original, corrected, entry.corrected)

        old_len = len(entry.corrected) + 1
        new_text = corrected + " "
        self._replacer.replace_text(old_len, new_text, listener=self._listener)

        entry.corrected = corrected

    def _do_polish(self):
        """Polish mode: one-shot cleanup of current line text.

        Activated by hotkey. Corrects layout, typos, spelling, punctuation
        of the text accumulated in the buffer (current line or selection).
        Does NOT rewrite or paraphrase — only polishes.
        """
        with self._lock:
            # Get accumulated line text from the buffer
            line_text = self._buffer.get_context()
            if not line_text or not line_text.strip():
                logger.debug("Polish: nothing to polish")
                return

            original_text = line_text.strip()
            logger.info("Polish mode activated on: %r", original_text)

        # Run correction outside lock
        polished = self._polish_text(original_text)

        with self._lock:
            if polished is None or polished == original_text:
                logger.debug("Polish: no changes needed for %r", original_text)
                return

            logger.info("Polish: %r → %r", original_text, polished)

            # Record for undo
            entry = CorrectionEntry(
                original=original_text,
                corrected=polished,
                char_count=len(polished),
            )
            self._undo_stack.push(entry)

            # Replace: delete entire line text, retype polished version
            old_len = len(line_text)
            self._replacer.replace_text(old_len, polished, listener=self._listener)

            # Signal layout switch intent — actual switch happens in Qt main thread
            target_layout = detect_target_layout(polished)
            self._requested_layout = target_layout

            # Enter handoff mode
            self._input_state = 'handoff'
            self._handoff_layout = target_layout

            # Clear buffers
            self._buffer.clear()
            self._phrase_words.clear()
            self._phrase_total_len = 0
            self._finalized_words.clear()

    def _polish_text(self, text: str) -> Optional[str]:
        """Run the polish pipeline on text: layout fix + spelling + punctuation.

        Does NOT rewrite or paraphrase — only corrects.
        """
        if not self._corrector:
            return None

        from kautoswitch.layout_map import (
            detect_layout_mismatch, map_en_to_ru, map_ru_to_en, fix_mixed_layout,
        )

        words = text.split()
        if not words:
            return None

        # Step 1: Try layout swap of entire text
        mismatch = detect_layout_mismatch(text)
        if mismatch == 'en_meant_ru':
            candidate = map_en_to_ru(text)
            if self._corrector._is_valid_text(candidate) or \
               self._corrector._text_validity_score(candidate) > 0.5:
                text = candidate
                words = text.split()
        elif mismatch == 'ru_meant_en':
            candidate = map_ru_to_en(text)
            if self._corrector._is_valid_text(candidate):
                text = candidate
                words = text.split()
        elif mismatch == 'mixed':
            # Determine dominant script
            alpha = [c for c in text if c.isalpha()]
            ru_count = sum(1 for c in alpha if '\u0400' <= c <= '\u04ff')
            en_count = sum(1 for c in alpha if c.isascii())
            target = 'ru' if ru_count > en_count else 'en'
            candidate = fix_mixed_layout(text, target=target)
            if candidate != text:
                text = candidate
                words = text.split()

        # Step 2: Word-by-word spelling correction
        corrected_words = []
        any_changed = False
        for word in words:
            result = self._corrector.correct(word)
            if result is not None:
                corrected, confidence = result
                if corrected != word and confidence >= self.config.confidence_threshold:
                    corrected_words.append(corrected)
                    any_changed = True
                    continue
            corrected_words.append(word)

        if any_changed:
            text = ' '.join(corrected_words)

        # Step 3: Basic punctuation cleanup
        # Ensure single space between words (collapse multiple spaces)
        import re
        text = re.sub(r' +', ' ', text).strip()

        return text
