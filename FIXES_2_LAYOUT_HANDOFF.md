# FIXES_2_LAYOUT_HANDOFF.md  
## Layout Handoff & Boundary Preservation Fixes

This document is an **additive corrective contract** to the existing project.

It MUST be applied **on top of**:
- CLAUDE_TASK_CONTRACT.md
- FIXES_1.md

Nothing in previous contracts may be removed or weakened.

---

## Problem Statement

Current behavior is improved but still violates expected human UX:

1. After correcting a mistyped word and switching keyboard layout,
   the system continues to interfere with subsequent typing.
2. Boundary characters (space / punctuation) that triggered correction
   are sometimes consumed or not rendered.
3. The system does not properly “hand off control” to the user after
   correcting layout.

---

## Required UX Semantics (Authoritative)

### 1. Layout handoff rule (CRITICAL)

Once the system:
- detects an incorrectly typed word
- corrects it
- switches keyboard layout

👉 **Control MUST be handed off to the user immediately.**

From that point on:

- The system MUST NOT attempt any further correction
- The system MUST NOT reinterpret input
- The system MUST NOT run word-level or phrase-level correction

UNTIL one of the following happens:
- User manually switches layout
- User starts typing again in the *wrong* layout (new detection cycle)

This mirrors how human users expect Punto Switcher–like tools to behave.

---

### 2. Explicit post-correction state

You MUST introduce an explicit state, e.g.:

- `LAYOUT_HANDOFF` or `PASSIVE`

Semantics:
- Entered immediately after:
  - word correction
  - layout switch
- While in this state:
  - all correction logic is disabled
  - input is passed through verbatim

Transition out of this state ONLY when:
- a new incorrect-layout pattern is detected
- OR user manually changes layout

---

### 3. Boundary preservation rule (MANDATORY)

If correction is triggered by a boundary character
(space or punctuation):

- That boundary character MUST be emitted to the application
- It MUST appear exactly once
- It MUST NOT be swallowed or delayed

Example:

Input:
```

ghbdtn␣

```

Correct output:
```

привет␣

```

NOT:
```

привет

```

NOT:
```

привет␣␣

```

---

### 4. Ordering rule (very important)

The correct sequence MUST be:

1. Replace incorrect word
2. Switch keyboard layout
3. Emit boundary character
4. Enter `LAYOUT_HANDOFF` state
5. Pass through all further input unchanged

Any other ordering is considered a bug.

---

## Required Code Changes (Conceptual)

### In daemon / input state machine

Add a new state:

- `HANDOFF` (or equivalent)

State transitions:

- `WORD_FINALIZED → HANDOFF`  
  when correction + layout switch occurs

- `HANDOFF → TYPING`  
  only when new incorrect-layout typing is detected

### Correction guards

While in `HANDOFF`:

- `_try_correct_word` MUST NOT run
- `_schedule_phrase_correction` MUST NOT run
- No timers should be scheduled
- No finalization logic should trigger

---

## Tests to Add (MANDATORY)

### Unit / logic tests

- `test_layout_handoff_disables_correction`
- `test_boundary_preserved_after_correction`
- `test_no_second_correction_after_layout_switch`

### Integration / runtime tests

- Typing sequence:
```

ghbdtn␣hello world␣

```
MUST result in:
```

привет␣hello world␣

```

- Ensure:
- no correction attempts on `hello`
- no phrase-level correction triggered
- layout remains user-controlled

---

## Runtime Validation (MANDATORY)

You MUST repeat **real typing validation**, as in FIXES_1:

- Xvfb + xdotool OR real VM
- Demonstrate:
- correction happens once
- layout switches
- user continues typing freely
- space is preserved

Document:
- what was typed
- what appeared on screen
- confirmation of correct handoff behavior

---

## Definition of Done

This fix is COMPLETE only if:

- After correction, the system becomes passive
- User can type normally in the new layout
- No further corrections occur until a new mistake
- Space / punctuation is always preserved
- All tests pass
- Version is bumped (e.g. 0.1.0-3)
- Behavior confirmed in real typing session

---

## Non-Goals

- No ML quality improvements
- No UI changes
- No Wayland support
- No new languages

---

Proceed immediately.  
Ask **ONE** question only if absolutely necessary.
