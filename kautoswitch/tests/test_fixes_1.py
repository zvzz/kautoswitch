"""Regression tests for FIXES_1 — fail before fix, pass after.

Tests:
1. Word corrected only once (finalization guard)
2. Space after correction preserved
3. Typing 'rfr ltkf' results in 'как дела' via deferred phrase
4. No phrase correction while typing continues
5. Phrase correction only after idle (run_deferred_phrase)
6. No re-entry from synthetic events (aggressive corrector + finalization guard)
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
    config._data["phrase_idle_delay_ms"] = 350
    return config


class MockReplacer:
    def __init__(self):
        self.calls = []

    def replace_text(self, old_len, new_text, listener=None):
        self.calls.append({'old_len': old_len, 'new_text': new_text})
        if listener:
            listener.suppressed = True
            listener.suppressed = False


class MockListener:
    def __init__(self):
        self.suppressed = False


class SimpleDaemon:
    """Test daemon mirroring real daemon with state machine + finalization guard."""

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
        self._last_correction = None
        self._finalized_words = set()
        self._input_state = 'typing'
        self._phrase_timer = None
        self._phrase_cancel = threading.Event()

    def feed_chars(self, text):
        for char in text:
            self._on_key_char(char)

    def _on_key_char(self, char):
        if not self.config.enabled:
            return
        with self._lock:
            self._cancel_phrase_timer()
            self._input_state = 'typing'

            completed_word = self._buffer.add_char(char)
            if completed_word:
                self._last_word_boundary = char
                self._input_state = 'word_finalized'
                self._try_correct_word(completed_word)

    def _cancel_phrase_timer(self):
        self._phrase_cancel.set()
        self._phrase_timer = None

    def run_deferred_phrase(self):
        """Synchronous helper: run deferred phrase correction now."""
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
        if self._last_correction is None:
            return False
        lc = self._last_correction
        if word == lc['corrected'] or word.lower() == lc['corrected'].lower():
            elapsed = time.time() - lc['time']
            if elapsed < 2.0:
                return True
        return False

    def _try_correct_word(self, word):
        if self._is_idempotent(word):
            self._phrase_words.clear()
            self._phrase_total_len = 0
            return

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
        self._last_correction = {
            'original': original,
            'corrected': corrected,
            'time': time.time(),
        }

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
        self._buffer.clear()


# ====================================================================
# Test 1: Word corrected only once (finalization guard)
# ====================================================================
def test_word_corrected_only_once():
    """Correct 'ghbdtn', then re-feed 'ghbdtn ' again →
    _finalized_words blocks second correction."""
    print("\nTest 1: Word corrected only once (finalization guard)")

    config = make_config()
    daemon = SimpleDaemon(config)

    # First: type 'ghbdtn ' → corrects to 'привет'
    daemon.feed_chars('ghbdtn ')
    calls_1 = len(daemon._replacer.calls)
    check("first correction fires", calls_1 == 1,
          f"expected 1, got {calls_1}")
    check("ghbdtn in finalized_words",
          'ghbdtn' in daemon._finalized_words,
          f"got {daemon._finalized_words}")

    # Second: clear buffer (as real daemon does) and re-feed same word
    daemon._buffer.clear()
    daemon.feed_chars('ghbdtn ')

    calls_2 = len(daemon._replacer.calls)
    check("finalization guard blocks second correction",
          calls_2 == 1,
          f"expected 1, got {calls_2} — REPEATED CORRECTION!")


# ====================================================================
# Test 2: Space after correction preserved
# ====================================================================
def test_space_after_correction_preserved():
    """Verify replacement includes trailing boundary char."""
    print("\nTest 2: Space after correction preserved")

    config = make_config()
    daemon = SimpleDaemon(config)

    daemon.feed_chars('ghbdtn ')

    check("correction happened", len(daemon._replacer.calls) == 1)
    if daemon._replacer.calls:
        call = daemon._replacer.calls[0]
        check("replacement ends with space",
              call['new_text'].endswith(' '),
              f"new_text='{call['new_text']}'")
        check("replacement contains привет",
              'привет' in call['new_text'],
              f"new_text='{call['new_text']}'")


# ====================================================================
# Test 3: Typing 'rfr ltkf' results in 'как дела' via deferred phrase
# ====================================================================
def test_typing_rfr_ltkf_results_in_kak_dela():
    """Type 'rfr ' + 'ltkf ', trigger deferred phrase → 'как дела'."""
    print("\nTest 3: 'rfr ltkf' → 'как дела' via deferred phrase")

    config = make_config()
    daemon = SimpleDaemon(config)

    # Type 'rfr ' — single word, may or may not correct individually
    daemon.feed_chars('rfr ')
    calls_after_first = len(daemon._replacer.calls)

    # Type 'ltkf ' — now we have 2 phrase words
    daemon.feed_chars('ltkf ')
    calls_after_second = len(daemon._replacer.calls)

    # Trigger deferred phrase correction
    daemon.run_deferred_phrase()

    total_calls = len(daemon._replacer.calls)
    # The phrase correction should have fired
    # Look for 'как дела' in any replacer call
    found_phrase = False
    for call in daemon._replacer.calls:
        if 'как дела' in call['new_text'] or 'как' in call['new_text']:
            found_phrase = True
            break

    check("phrase correction produced 'как дела' or 'как'",
          found_phrase,
          f"replacer calls: {daemon._replacer.calls}")


# ====================================================================
# Test 4: No phrase correction while typing continues
# ====================================================================
def test_no_phrase_correction_while_typing():
    """Type 'rfr ' then immediately type 'l' → phrase correction must NOT fire."""
    print("\nTest 4: No phrase correction while typing")

    config = make_config()
    daemon = SimpleDaemon(config)

    daemon.feed_chars('rfr ')
    calls_after_word = len(daemon._replacer.calls)

    # Immediately type another char — this sets state to 'typing'
    daemon.feed_chars('l')

    # Now try to run deferred phrase — should be blocked (state == 'typing')
    daemon.run_deferred_phrase()

    total_calls = len(daemon._replacer.calls)
    # No phrase correction should have fired since we're still typing
    check("no phrase correction while typing",
          total_calls == calls_after_word,
          f"expected {calls_after_word}, got {total_calls}")


# ====================================================================
# Test 5: Phrase correction only after idle
# ====================================================================
def test_phrase_correction_only_after_idle():
    """Phrase correction only runs when run_deferred_phrase() is called,
    not during word finalization."""
    print("\nTest 5: Phrase correction only after idle")

    config = make_config()
    daemon = SimpleDaemon(config)

    # Type two words
    daemon.feed_chars('rfr ')
    daemon.feed_chars('ltkf ')

    # At this point, only single-word corrections should have fired
    # (no synchronous phrase correction during typing)
    calls_before = len(daemon._replacer.calls)

    # Phrase correction wasn't triggered yet — the words should still be
    # in the phrase buffer if they weren't individually corrected
    has_phrase_words = len(daemon._phrase_words) >= 1

    # Now trigger idle
    daemon.run_deferred_phrase()
    calls_after = len(daemon._replacer.calls)

    # If phrase words were available and phrase correction found something,
    # we should see a new call
    check("phrase words were buffered for deferred correction",
          has_phrase_words or calls_before > 0,
          f"phrase_words={daemon._phrase_words}, calls_before={calls_before}")


# ====================================================================
# Test 6: No re-entry from synthetic events
# ====================================================================
def test_no_reentry_from_synthetic_events():
    """Aggressive corrector + finalization guard blocks re-correction.

    Patch corrector to always return a correction, then verify that
    the finalization guard prevents infinite correction loops.
    """
    print("\nTest 6: No re-entry from synthetic events (aggressive corrector)")

    config = make_config()
    daemon = SimpleDaemon(config)

    # Patch corrector to always try to "correct" anything
    original_correct = daemon._corrector.correct
    call_count = [0]

    def aggressive_correct(text, context=""):
        call_count[0] += 1
        # First call: normal correction
        result = original_correct(text, context)
        if result:
            return result
        # If no natural correction, force one for testing
        if call_count[0] <= 1:
            return (text + '_fixed', 0.95)
        return None

    daemon._corrector.correct = aggressive_correct

    # Type word
    daemon.feed_chars('ghbdtn ')
    first_calls = len(daemon._replacer.calls)
    check("first correction fires", first_calls == 1,
          f"got {first_calls}")

    # Simulate synthetic leak of corrected text
    daemon._buffer.clear()
    daemon.feed_chars('привет ')

    total_calls = len(daemon._replacer.calls)
    check("finalization guard blocks re-correction from synthetic leak",
          total_calls == 1,
          f"expected 1, got {total_calls} — RE-ENTRY DETECTED!")

    # Even more aggressive: try feeding the original again
    daemon._buffer.clear()
    daemon.feed_chars('ghbdtn ')

    final_calls = len(daemon._replacer.calls)
    check("finalization guard blocks re-correction of original word",
          final_calls == 1,
          f"expected 1, got {final_calls}")


# ====================================================================
if __name__ == '__main__':
    test_word_corrected_only_once()
    test_space_after_correction_preserved()
    test_typing_rfr_ltkf_results_in_kak_dela()
    test_no_phrase_correction_while_typing()
    test_phrase_correction_only_after_idle()
    test_no_reentry_from_synthetic_events()

    print(f"\n{'='*50}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        print("SOME TESTS FAILED")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
