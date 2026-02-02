# TASK: Fix feedback loop + add real runtime stability tests

You must fix a critical runtime bug and prove the fix via tests and real execution.

## Observed critical bug (must be fixed)
- After correcting a word (e.g. ghbdtn → привет):
  - input becomes blocked
  - SPACE does not pass through
  - daemon enters infinite correction loop
- Logs show repeated correction of the same word.

Root cause is assumed to be:
- lack of suppression of synthetic (XTest) input
- lack of idempotency guard on replacements

## Mandatory fixes (all required)

### 1. Synthetic input suppression
- While performing replacement (XTest events):
  - input listener MUST ignore events
- Implement explicit guard:
  - suppress_input = True during replacement
  - suppress_input = False after
- Synthetic events must NOT re-enter correction pipeline.

### 2. Idempotency / re-entrancy protection
- Track last auto-correction:
  - original text
  - corrected text
  - character range
  - timestamp
- If a new correction candidate:
  - matches last corrected output
  - or falls within the same range
→ skip correction

### 3. Cursor and boundary correctness
- Replacement must:
  - only delete the intended token
  - not consume following SPACE or punctuation
  - restore cursor correctly
- User must be able to continue typing immediately.

## Testing requirements (mandatory)

### A. Unit tests (pure Python)
Add tests that verify:
- correction is not re-triggered on corrected output
- buffer state after replacement is clean
- undo restores original text exactly
- space after correction is preserved

### B. Integration tests (mocked input)
- Simulate sequence:
  - type g h b d t n SPACE
- Verify:
  - exactly ONE correction happens
  - final visible text: "привет "
  - no further corrections triggered

### C. Real runtime test (required)
You MUST provide one of the following:

#### Option 1 (preferred): VM-based test
- Use a lightweight Ubuntu VM (QEMU / virt-install)
- Install the built .deb
- Run kautoswitch in a real X11 session
- Demonstrate via log/assertion that:
  - no infinite loop occurs
  - typing continues after correction

#### Option 2 (fallback): Manual-assisted real run
- Provide a documented script + checklist:
  - start daemon with debug logging
  - type test sequences in terminal
  - show expected log sequence (finite)
- Explain how this proves loop is fixed.

## Acceptance criteria (strict)

This task is COMPLETE only when:
- Infinite correction loop is impossible
- SPACE and further typing always work after correction
- Logs show exactly one correction per word
- Tests fail BEFORE fix and pass AFTER fix
- Behavior is stable in a real X11 session

Do NOT add new features.
Do NOT refactor unrelated code.
Focus on correctness and stability.

Start with:
1) reproducing the bug in tests
2) implementing the guard
3) proving the fix
