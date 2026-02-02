# CLAUDE TASK CONTRACT — kautoswitch: Stability & UX Correctness

## Role
You are a senior Linux systems developer and input-method engineer.

Your task is to FIX the remaining architectural and UX correctness issues in the kautoswitch project and bring it to a **stable, human-usable state**.

This is NOT about adding features.
This is about **correctness of input handling, state machines, and real-world behavior**.

---

## Absolute Rules

- Do NOT simplify the architecture
- Do NOT remove existing components
- Do NOT hand-wave or assume behavior
- If something is complex — implement the minimal correct solution
- The result MUST work for real typing by a human
- You must test not only code, but **actual typing behavior**

---

## Current Known Problems (All MUST be fixed)

### 1. Repeated correction loop after space

Observed behavior:
- A word is corrected
- Space is typed
- The same word is corrected again
- This repeats indefinitely

Root cause (already identified):
- Word correction is triggered multiple times per word
- There is no strict “word finalization” state

Required fix:
- Introduce explicit **word finalization state**
- A word may be corrected **at most once** between two boundaries

Boundary characters:
- SPACE
- ENTER
- TAB
- `. , ! ? : ;`

Once a word is corrected and a boundary is observed:
- That word MUST NOT be corrected again
- The boundary (space) MUST be preserved and passed through

---

### 2. Correction happens too early while user is typing

Observed behavior:
- While typing a word, partial corrections are applied
- Phrase-level correction triggers mid-typing
- This corrupts the buffer and produces garbage output

Required rules (strict):

- **Word-level correction**:
  - Allowed ONLY when a boundary is typed
  - NEVER while the user is actively typing characters

- **Phrase-level correction**:
  - MUST NOT run while user is typing
  - Allowed ONLY when:
    - A boundary is typed
    - AND there is an idle pause (e.g. 300–500 ms)
  - MUST be cancelable if typing resumes
  - MUST NEVER block input

---

### 3. Phrase-level correction must be deferred and non-destructive

Current incorrect behavior:
- Phrase correction attempts run synchronously
- Timeouts occur while user continues typing

Required behavior:
- Phrase correction runs in background
- If it times out → silently abort
- It must NEVER:
  - Block input
  - Corrupt buffer state
  - Re-trigger word-level correction

---

### 4. Versioning must reflect real changes

Problem:
- Package version remains `0.1.0-1`
- User cannot distinguish old vs new behavior

Required:
- Bump Debian version to `0.1.0-2`
- Update `debian/changelog` with meaningful entries
- Ensure `apt install` clearly shows upgrade

---

## Required Architectural Changes

You MUST implement a clear input state machine with at least these states:

- `TYPING_WORD`
- `WORD_FINALIZED`
- `IDLE`

Mandatory state rules:
- Correction allowed ONLY on transition `TYPING_WORD → WORD_FINALIZED`
- Phrase correction allowed ONLY in `IDLE`
- Synthetic input MUST NOT re-enter correction logic

---

## Testing Requirements (MANDATORY)

### 1. Automated Tests

Add or extend tests to cover ALL of the following:

- `test_word_corrected_only_once`
- `test_space_after_correction_preserved`
- `test_typing_rfr_ltkf_results_in_kak_dela`
- `test_no_phrase_correction_while_typing`
- `test_phrase_correction_only_after_idle`
- `test_no_reentry_from_synthetic_events`

Tests MUST fail before fix and pass after.

---

### 2. Real Runtime Typing Test (MANDATORY)

You MUST test the system as a **real user**, not just unit tests.

You MUST do ONE of the following:

#### Option A (preferred)
- Launch a virtual machine (X11, KDE or similar)
- Install the built `.deb`
- Enable the user service
- Open a terminal or text editor
- Physically simulate typing sequences:
  - `ghbdtn␣`
  - `rfr ltkf␣`
  - mixed language phrases
- Observe actual on-screen behavior

#### Option B (acceptable if VM is impossible)
- Use Xvfb or nested X11 session
- Inject key events programmatically
- Capture resulting text buffer
- Treat this as a human typing simulation

You MUST document:
- What environment was used
- What was typed
- What appeared on screen
- Confirmation that typing continues naturally

---

## Packaging & Validation

You MUST:

1. Build a new `.deb` (`0.1.0-2`)
2. Install it cleanly in the test environment
3. Restart the user service
4. Confirm:
   - No correction loops
   - Spaces work normally
   - Typing feels natural

---

## Definition of Done

The task is DONE only if ALL of the following are true:

- A word is corrected at most once
- Space after correction works normally
- Phrase correction never interferes with active typing
- Typing `rfr ltkf` produces `как дела`
- No infinite correction loops occur
- Version is bumped and visible
- Tests cover all reported issues
- A real typing session was performed and documented

---

## Non-Goals

- No Wayland support
- No new languages
- No UI redesign
- No new ML models

---

## Output Required

At the end, you MUST provide:

1. Summary of changes
2. List of modified files
3. Test results
4. Description of real typing test performed
5. Instructions to build and install the new `.deb`

---

If anything is unclear, you may ask **ONE** clarifying question.
Otherwise, proceed immediately.
