"""Stability tests — reproduce and verify fixes for the feedback loop bug.

These tests simulate the daemon's correction flow without X11,
verifying that:
- Correction is NOT re-triggered on corrected output
- Buffer state after replacement is clean
- Undo restores original text exactly
- Space after correction is preserved
- Exactly ONE correction happens per word
"""
import sys
import os
import time
import threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from kautoswitch.config import Config
from kautoswitch.corrector import Corrector
from kautoswitch.tinyllm import TinyLLM
from kautoswitch.buffer import TextBuffer
from kautoswitch.undo import UndoStack, CorrectionEntry
from kautoswitch.rules import RuleStore

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


# ====================================================================
# Test: Corrected output must NOT re-trigger correction
# ====================================================================
def test_no_retrigger_on_corrected_output():
    """After 'ghbdtn' → 'привет', feeding 'привет' back must NOT trigger
    another correction. This is the core feedback loop bug."""
    print("\nTest: No re-trigger on corrected output")

    config = make_config()
    corrector = Corrector(config, tinyllm=TinyLLM())

    # Step 1: correct 'ghbdtn' → should produce 'привет'
    result = corrector.correct('ghbdtn')
    check("'ghbdtn' corrects to something",
          result is not None, f"got {result}")

    if result:
        corrected = result[0]
        check("correction is 'привет'",
              'привет' in corrected.lower(), f"got '{corrected}'")

        # Step 2: feed the corrected output back — must return None
        result2 = corrector.correct(corrected)
        check("corrected output 'привет' does NOT re-trigger",
              result2 is None,
              f"FEEDBACK LOOP: corrected '{corrected}' triggered another correction: {result2}")


# ====================================================================
# Test: Buffer state is clean after simulated replacement
# ====================================================================
def test_buffer_clean_after_replacement():
    """After a word is corrected and replaced, the buffer must be empty/clean
    so that next typed characters start fresh."""
    print("\nTest: Buffer clean after replacement")

    buf = TextBuffer()

    # Simulate typing 'ghbdtn' + space
    for c in 'ghbdtn':
        buf.add_char(c)
    completed = buf.add_char(' ')
    check("word 'ghbdtn' completed on space", completed == 'ghbdtn')

    # Simulate what daemon does after correction: clear everything
    buf.clear()

    check("buffer word is empty after clear", buf.get_current_word() == '')
    check("buffer context is empty after clear", buf.get_context() == '')

    # Now simulate typing the next word — must work cleanly
    for c in 'world':
        buf.add_char(c)
    check("next word accumulates correctly",
          buf.get_current_word() == 'world')


# ====================================================================
# Test: Undo restores original text exactly
# ====================================================================
def test_undo_restores_exact():
    """Undo must restore the exact original text, not a re-corrected version."""
    print("\nTest: Undo restores exact original")

    stack = UndoStack()
    entry = CorrectionEntry(
        original='ghbdtn',
        corrected='привет',
        char_count=6,
    )
    stack.push(entry)

    popped = stack.pop()
    check("undo entry has exact original",
          popped.original == 'ghbdtn',
          f"got '{popped.original}'")
    check("undo entry has exact corrected",
          popped.corrected == 'привет',
          f"got '{popped.corrected}'")


# ====================================================================
# Test: Space after correction is preserved
# ====================================================================
def test_space_preserved():
    """After correction, the space (word boundary) must remain.
    User must be able to continue typing."""
    print("\nTest: Space after correction is preserved")

    buf = TextBuffer()

    # Type 'ghbdtn '
    for c in 'ghbdtn':
        buf.add_char(c)
    completed = buf.add_char(' ')
    check("word completed", completed == 'ghbdtn')

    # Simulate: correction replaces 'ghbdtn ' with 'привет '
    # Buffer is cleared after replacement
    buf.clear()

    # Simulate user typing 'мир' after the space
    for c in 'мир':
        result = buf.add_char(c)
    check("next word in buffer is clean", buf.get_current_word() == 'мир')

    # Complete it
    completed2 = buf.add_char(' ')
    check("next word completes normally", completed2 == 'мир')


# ====================================================================
# Test: Simulated full sequence — exactly ONE correction
# ====================================================================
def test_exactly_one_correction():
    """Simulate typing 'ghbdtn' + SPACE through the daemon's logic.
    Must produce exactly ONE correction, not an infinite loop."""
    print("\nTest: Exactly one correction per word")

    config = make_config()
    corrector = Corrector(config, tinyllm=TinyLLM())
    buf = TextBuffer()
    corrections = []

    # Simulate typing 'ghbdtn' char by char
    for c in 'ghbdtn':
        completed = buf.add_char(c)
        assert completed is None  # no word boundary yet

    # Type space — triggers word completion
    completed = buf.add_char(' ')
    assert completed == 'ghbdtn'

    # Run correction
    result = corrector.correct(completed)
    if result:
        corrected, confidence = result
        if corrected != completed and confidence >= 0.6:
            corrections.append((completed, corrected))

    check("exactly one correction triggered",
          len(corrections) == 1,
          f"got {len(corrections)} corrections")

    if corrections:
        orig, fixed = corrections[0]
        check("correction is ghbdtn→привет",
              'привет' in fixed.lower(),
              f"got {orig}→{fixed}")

    # Now simulate: the corrected text 'привет' appears.
    # Clear buffer (daemon does this after replacement)
    buf.clear()

    # If synthetic events leak, 'привет' would be fed back.
    # Simulate this worst case:
    for c in 'привет':
        completed = buf.add_char(c)
        assert completed is None

    leaked_word = buf.add_char(' ')
    assert leaked_word == 'привет'

    # Try to correct the leaked word — must be None (already valid)
    result2 = corrector.correct(leaked_word)
    check("leaked corrected text does NOT re-trigger",
          result2 is None,
          f"LOOP: '{leaked_word}' triggered: {result2}")


# ====================================================================
# Test: Idempotency guard in daemon-level logic
# ====================================================================
def test_idempotency_guard():
    """The daemon must track the last correction and skip if the same
    corrected text comes back as input."""
    print("\nTest: Idempotency guard")

    config = make_config()
    corrector = Corrector(config, tinyllm=TinyLLM())

    # Correct 'jy' → 'он'
    r1 = corrector.correct('jy')
    check("'jy' corrects", r1 is not None)

    if r1:
        corrected = r1[0]
        # Now: if 'он' comes back as input, it must not be corrected
        r2 = corrector.correct(corrected)
        check(f"'{corrected}' not re-corrected",
              r2 is None,
              f"re-triggered: {r2}")

    # Another example: 'ghbdtn' → 'привет'
    r3 = corrector.correct('ghbdtn')
    check("'ghbdtn' corrects", r3 is not None)

    if r3:
        corrected = r3[0]
        r4 = corrector.correct(corrected)
        check(f"'{corrected}' not re-corrected",
              r4 is None,
              f"re-triggered: {r4}")


# ====================================================================
# Test: Multiple words in sequence — no cascading corrections
# ====================================================================
def test_no_cascade():
    """Typing multiple wrong-layout words in sequence must correct each
    exactly once, with no cascade."""
    print("\nTest: No cascading corrections")

    config = make_config()
    corrector = Corrector(config, tinyllm=TinyLLM())

    words = ['ghbdtn', 'vbh']
    all_corrections = []

    for word in words:
        result = corrector.correct(word)
        if result and result[0] != word:
            all_corrections.append((word, result[0]))

            # Simulate feeding corrected text back (worst-case leak)
            result2 = corrector.correct(result[0])
            check(f"no re-trigger after correcting '{word}'→'{result[0]}'",
                  result2 is None,
                  f"cascade: {result2}")

    check("each word corrected exactly once",
          len(all_corrections) == len(words),
          f"got {len(all_corrections)} corrections for {len(words)} words")


# ====================================================================
if __name__ == '__main__':
    test_no_retrigger_on_corrected_output()
    test_buffer_clean_after_replacement()
    test_undo_restores_exact()
    test_space_preserved()
    test_exactly_one_correction()
    test_idempotency_guard()
    test_no_cascade()

    print(f"\n{'='*50}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        print("SOME TESTS FAILED")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
