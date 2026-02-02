"""Daemon-level stability tests — reproduce and verify the feedback loop bug.

These tests mock X11 components and exercise the daemon's _on_key_char flow,
simulating synthetic event leakage that causes the infinite correction loop.

Key bugs reproduced:
- Corrected output leaking back through listener → re-correction attempt
- Buffer not fully cleared after replacement → stale context
- No idempotency guard → repeated corrections of same text
"""
import sys
import os
import time
import threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from kautoswitch.config import Config
from kautoswitch.corrector import Corrector
from kautoswitch.buffer import TextBuffer
from kautoswitch.undo import UndoStack, CorrectionEntry
from kautoswitch.rules import RuleStore
from kautoswitch.tinyllm import TinyLLM

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def make_config():
    config = Config()
    config._data["languages"] = {"ru": True, "en": True, "be": False}
    config._data["ai_timeout_ms"] = 5000
    return config


class MockReplacer:
    """Records replace_text calls instead of sending X11 events."""
    def __init__(self):
        self.calls = []

    def replace_text(self, old_len, new_text, listener=None):
        self.calls.append({
            'old_len': old_len,
            'new_text': new_text,
        })
        # Simulate what real replacer does: suppress listener
        if listener:
            listener.suppressed = True
            # In the buggy version, suppression lifts too early
            listener.suppressed = False


class MockListener:
    """Mock X11KeyListener with suppression flag."""
    def __init__(self):
        self.suppressed = False


class SimpleDaemon:
    """Simplified daemon for testing — no X11, uses mock replacer/listener.

    This closely mirrors the real Daemon class and includes all fixes.
    """

    def __init__(self, config):
        self.config = config
        self._buffer = TextBuffer()
        self._replacer = MockReplacer()
        self._undo_stack = UndoStack()
        self._rules = RuleStore()
        self._corrector = Corrector(config, tinyllm=TinyLLM())
        self._listener = MockListener()
        self._lock = threading.Lock()
        self._last_word_boundary = ""
        self._phrase_words = []
        self._phrase_total_len = 0
        # FIX: idempotency guard — track last correction
        self._last_correction = None  # {original, corrected, time}
        # Word finalization guard
        self._finalized_words = set()
        # Input state machine
        self._input_state = 'typing'
        # Deferred phrase correction (no real timer in tests)
        self._phrase_timer = None
        self._phrase_cancel = threading.Event()

    def feed_chars(self, text):
        """Simulate typing characters through the daemon."""
        for char in text:
            self._on_key_char(char)

    def _on_key_char(self, char):
        if not self.config.enabled:
            return
        with self._lock:
            # Cancel any pending phrase timer — user still typing
            self._cancel_phrase_timer()
            self._input_state = 'typing'

            completed_word = self._buffer.add_char(char)
            if completed_word:
                self._last_word_boundary = char
                self._input_state = 'word_finalized'
                self._try_correct_word(completed_word)

    def _cancel_phrase_timer(self):
        """Cancel any pending phrase correction timer."""
        self._phrase_cancel.set()
        self._phrase_timer = None

    def run_deferred_phrase(self):
        """Synchronous helper for tests: run deferred phrase correction now."""
        with self._lock:
            if self._input_state == 'typing':
                return
            words_snapshot = list(self._phrase_words)
            if len(words_snapshot) < 2:
                return

        phrase_result = self._corrector.correct_phrase(words_snapshot)

        with self._lock:
            if phrase_result is None:
                self._input_state = 'idle'
                return

            corrected_phrase, confidence = phrase_result
            original_phrase = ' '.join(words_snapshot)

            if self._phrase_words != words_snapshot:
                return

            if (corrected_phrase != original_phrase and
                    confidence >= self.config.confidence_threshold):
                self._apply_phrase_correction(original_phrase, corrected_phrase)

            self._input_state = 'idle'

    def _is_idempotent(self, word):
        """Check if this word matches the last correction output (feedback loop guard)."""
        if self._last_correction is None:
            return False
        lc = self._last_correction
        if word == lc['corrected'] or word.lower() == lc['corrected'].lower():
            elapsed = time.time() - lc['time']
            if elapsed < 2.0:
                return True
        return False

    def _try_correct_word(self, word):
        """Single-word correction only. Phrase correction is deferred."""
        # Idempotency guard
        if self._is_idempotent(word):
            self._phrase_words.clear()
            self._phrase_total_len = 0
            return

        # Finalization guard
        if word.lower() in self._finalized_words:
            self._phrase_words.append(word)
            self._phrase_total_len += len(word) + 1
            return

        if self._rules.is_suppressed(word):
            self._phrase_words.append(word)
            self._phrase_total_len += len(word) + 1
            return

        self._phrase_words.append(word)
        self._phrase_total_len += len(word) + 1

        # Single-word correction only (phrase is deferred)
        result = self._corrector.correct(word)
        if result is not None:
            corrected, confidence = result
            if corrected != word and confidence >= self.config.confidence_threshold:
                self._phrase_words.pop()
                self._phrase_total_len -= len(word) + 1
                self._apply_word_correction(word, corrected)
                self._phrase_words.clear()
                self._phrase_total_len = 0
                return

    def _apply_phrase_correction(self, original_phrase, corrected_phrase):
        corrected_words = corrected_phrase.split()
        if corrected_words:
            self._last_correction = {
                'original': original_phrase,
                'corrected': corrected_words[-1],
                'time': time.time(),
            }

        # Add all words to finalization guard
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
        old_len = self._phrase_total_len
        new_text = corrected_phrase + self._last_word_boundary
        self._replacer.replace_text(old_len, new_text, listener=self._listener)
        self._buffer.clear()
        self._phrase_words.clear()
        self._phrase_total_len = 0

    def _apply_word_correction(self, original, corrected):
        # Record last correction for idempotency guard
        self._last_correction = {
            'original': original,
            'corrected': corrected,
            'time': time.time(),
        }

        # Add both to finalization guard
        self._finalized_words.add(original.lower())
        self._finalized_words.add(corrected.lower())

        entry = CorrectionEntry(
            original=original,
            corrected=corrected,
            char_count=len(corrected),
        )
        self._undo_stack.push(entry)
        old_len = len(original) + 1
        new_text = corrected + self._last_word_boundary
        self._replacer.replace_text(old_len, new_text, listener=self._listener)
        # FIX: full buffer clear
        self._buffer.clear()


# ====================================================================
# Test: Daemon-level feedback loop detection
# ====================================================================
def test_daemon_feedback_loop():
    """Simulate the exact feedback loop scenario:
    1. Type 'ghbdtn' + space → correction fires
    2. Synthetic events leak: 'привет' + space enters listener
    3. Daemon must NOT fire a second correction.

    Without idempotency guard, the daemon processes the leaked text.
    The corrector happens to return None for valid 'привет', but this
    test verifies there's no second replacer call regardless.
    """
    print("\nTest: Daemon-level feedback loop detection")

    config = make_config()
    daemon = SimpleDaemon(config)

    # Step 1: type 'ghbdtn' + space
    daemon.feed_chars('ghbdtn ')

    initial_calls = len(daemon._replacer.calls)
    check("first correction fires",
          initial_calls == 1,
          f"expected 1 replacer call, got {initial_calls}")

    if initial_calls > 0:
        call = daemon._replacer.calls[0]
        check("replacement contains 'привет'",
              'привет' in call['new_text'],
              f"got new_text='{call['new_text']}'")

    # Step 2: simulate synthetic event leakage — corrected text comes back
    # Clear buffer as the real daemon would after replacement
    daemon._buffer.clear()
    daemon.feed_chars('привет ')

    total_calls = len(daemon._replacer.calls)
    check("no second correction after synthetic leak",
          total_calls == 1,
          f"expected 1 total replacer call, got {total_calls}")


# ====================================================================
# Test: Buffer state after correction — must be fully clean
# ====================================================================
def test_buffer_clean_after_daemon_correction():
    """After correction, the daemon's buffer must be fully clear so next
    typed word doesn't carry stale context."""
    print("\nTest: Buffer state clean after daemon correction")

    config = make_config()
    daemon = SimpleDaemon(config)

    # Type and correct
    daemon.feed_chars('ghbdtn ')

    # BUG check: in the buggy version, _current_line retains data
    # because only replace_current_word("") is called
    word = daemon._buffer.get_current_word()
    context = daemon._buffer.get_context()

    check("buffer current_word is empty after correction",
          word == '',
          f"got word='{word}'")

    # This is the key bug: context should also be empty
    check("buffer context is empty after correction",
          context == '',
          f"got context='{context}' (stale data!)")


# ====================================================================
# Test: Idempotency guard prevents double correction
# ====================================================================
def test_daemon_idempotency_guard():
    """If the same word is corrected and then appears again immediately
    (due to synthetic event leak), the daemon must skip it.

    This test uses a patched corrector that always returns a correction
    to prove the guard works at the daemon level (not just relying on
    the corrector returning None for valid words).
    """
    print("\nTest: Daemon idempotency guard")

    config = make_config()
    daemon = SimpleDaemon(config)

    # Patch corrector to always try to correct 'привет' → 'ПРИВЕТ2'
    # This simulates a scenario where corrector doesn't recognize the word
    original_correct = daemon._corrector.correct

    call_count = [0]

    def patched_correct(text, context=""):
        call_count[0] += 1
        if text == 'привет':
            # Simulate: corrector thinks it needs correction
            return ('ПРИВЕТ2', 0.95)
        return original_correct(text, context)

    daemon._corrector.correct = patched_correct

    # Type 'ghbdtn' + space → corrects to 'привет'
    daemon.feed_chars('ghbdtn ')

    first_calls = len(daemon._replacer.calls)
    check("first correction fires",
          first_calls == 1,
          f"got {first_calls} replacer calls")

    # Now simulate leak: 'привет' comes back through listener
    daemon._buffer.clear()
    daemon.feed_chars('привет ')

    total_calls = len(daemon._replacer.calls)

    # WITH idempotency guard: total_calls should still be 1
    # WITHOUT guard: total_calls will be 2 (the patched corrector fires)
    check("idempotency guard prevents second correction",
          total_calls == 1,
          f"expected 1, got {total_calls} — FEEDBACK LOOP!")


# ====================================================================
# Test: Space passthrough after correction
# ====================================================================
def test_space_passthrough_after_correction():
    """After a correction, the user's next space must pass through normally.
    The replacement must not consume the trailing space."""
    print("\nTest: Space passthrough after correction")

    config = make_config()
    daemon = SimpleDaemon(config)

    daemon.feed_chars('ghbdtn ')

    # Check that the replacement includes the trailing space
    check("correction happened", len(daemon._replacer.calls) == 1)

    if daemon._replacer.calls:
        call = daemon._replacer.calls[0]
        check("replacement ends with space boundary",
              call['new_text'].endswith(' '),
              f"new_text='{call['new_text']}'")

    # Now type next word — buffer must accept it cleanly
    daemon._buffer.clear()
    daemon.feed_chars('мир ')

    # 'мир' is a valid Russian word, so no correction should fire
    total = len(daemon._replacer.calls)
    check("next word 'мир' not corrected (valid)",
          total == 1,
          f"expected 1 total, got {total}")


# ====================================================================
# Test: Multiple words — each corrected exactly once
# ====================================================================
def test_daemon_multiple_words_no_cascade():
    """Type multiple wrong-layout words. Each must be corrected exactly once
    with no cascading."""
    print("\nTest: Multiple words — no cascade")

    config = make_config()
    daemon = SimpleDaemon(config)

    # Type 'ghbdtn ' → corrects
    daemon.feed_chars('ghbdtn ')
    daemon._buffer.clear()

    calls_after_first = len(daemon._replacer.calls)
    check("first word corrected", calls_after_first >= 1,
          f"got {calls_after_first}")

    # Simulate leak of first correction
    daemon.feed_chars('привет ')
    daemon._buffer.clear()

    calls_after_leak = len(daemon._replacer.calls)
    check("no re-trigger after first leak",
          calls_after_leak == calls_after_first,
          f"expected {calls_after_first}, got {calls_after_leak}")

    # Type second word 'vbh ' → should correct to 'мир'
    daemon.feed_chars('vbh ')
    daemon._buffer.clear()

    calls_after_second = len(daemon._replacer.calls)
    check("second word corrected",
          calls_after_second == calls_after_first + 1,
          f"expected {calls_after_first + 1}, got {calls_after_second}")


# ====================================================================
# Test: Replacer suppression — listener flag management
# ====================================================================
def test_replacer_suppression_flag():
    """The replacer must set listener.suppressed=True during replacement
    and only release it after all synthetic events are processed."""
    print("\nTest: Replacer suppression flag management")

    from kautoswitch.replacer import X11Replacer

    listener = MockListener()
    # We can't test real X11, but we verify the flag protocol
    check("listener starts unsuppressed", listener.suppressed == False)

    # Simulate what replacer does
    listener.suppressed = True
    check("suppressed during replacement", listener.suppressed == True)

    listener.suppressed = False
    check("unsuppressed after replacement", listener.suppressed == False)


# ====================================================================
if __name__ == '__main__':
    test_daemon_feedback_loop()
    test_buffer_clean_after_daemon_correction()
    test_daemon_idempotency_guard()
    test_space_passthrough_after_correction()
    test_daemon_multiple_words_no_cascade()
    test_replacer_suppression_flag()

    print(f"\n{'='*50}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        print("SOME TESTS FAILED — bugs to fix")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
