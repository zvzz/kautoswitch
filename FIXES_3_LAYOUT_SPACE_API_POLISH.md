# FIXES_3_LAYOUT_SPACE_API_POLISH.md  
## Layout Switch, Space Preservation, API Models & Polish Mode

This document is an **additive corrective contract**.

It MUST be applied on top of:
- CLAUDE_TASK_CONTRACT.md
- FIXES_1.md
- FIXES_2_LAYOUT_HANDOFF.md

If any behavior below contradicts current code or assumptions,
THE CODE IS WRONG, not the spec.

Tone note:  
Repeated violations of explicit requirements indicate misunderstanding.
Read carefully and fix root causes, not symptoms.

---

## 0. READ THIS FIRST (IMPORTANT)

Several behaviors described below were already specified multiple times
(in text and tests) and are STILL BROKEN.

This means:
- either requirements were not understood
- or they were understood and ignored

Both are unacceptable at this stage.

You must treat this document as **authoritative**.

---

## 1. Keyboard Layout MUST be switched after correction (CRITICAL)

### Problem

After correcting a mistyped word, the system sometimes:
- replaces the word
- BUT does NOT switch keyboard layout
- or switches layout but continues interfering with typing

This is WRONG.

### Required behavior (non-negotiable)

If the system:
- detects a word typed in the wrong layout
- replaces it with the corrected word

THEN it MUST:

1. Switch the keyboard layout to the layout of the corrected word
2. Immediately enter PASSIVE / HANDOFF mode
3. Stop ALL correction logic
4. Let the user continue typing naturally in the correct layout

This is the **entire point** of a Punto Switcher–like tool.

If you do not switch layout, the UX is broken by definition.

---

## 2. SPACE AND PUNCTUATION MUST NEVER BE EATEN (ABSOLUTE RULE)

This is now the THIRD time this is being stated.

Let this be absolutely clear:

> THE SPACE DOES NOT BELONG TO YOU.

### What is happening now (broken)

User types:
```

<word><space>

```

System:
- uses the space as a trigger
- replaces the word
- DOES NOT EMIT THE SPACE

Result:
- word is corrected
- but space disappears

This is unacceptable.

---

### Required invariant (MANDATORY)

If a correction is triggered by:
- space
- punctuation
- enter

THEN:

- That character MUST be emitted
- Exactly once
- AFTER the correction
- BEFORE entering handoff mode

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

NOT:
```

привет<next word glued>

```

This MUST be enforced in:
- code
- tests
- runtime behavior

If tests pass while this is broken, the tests are insufficient and must be fixed.

---

## 3. API MODEL SELECTION IS INCOMPLETE

### Problem

In API mode:
- It is unclear which model is used
- User cannot choose the model
- UI shows only a URL, which is insufficient

This is not acceptable for a tool intended for daily use.

---

### Required behavior

When **Correction Model = Local API**:

1. The daemon MUST query the API for available models
   (e.g. `/v1/models` or equivalent)
2. The Settings UI MUST:
   - Populate a dropdown with available models
   - Allow the user to select the model
3. The selected model MUST be:
   - Stored in config
   - Used in correction requests
4. If model list cannot be fetched:
   - Show a clear error in UI
   - Do NOT silently fall back

You MUST document:
- expected API response format
- how model switching works

---

## 4. ADD A “POLISH MODE” (HOTKEY-DRIVEN, NON-INTRUSIVE)

This is a NEW MODE. Read carefully.

---

### Motivation

Sometimes the user:
- types a long phrase or paragraph
- only later notices it is in the wrong layout
- or contains many typos / punctuation errors

In this case:
- inline correction is NOT desired
- user wants a **one-shot cleanup before sending**

---

### Required new mode: “Polish / Rethink Input”

This mode MUST be activated ONLY by a hotkey  
(e.g. existing “Rethink last input” or a new one).

Behavior:

1. When hotkey is pressed:
   - NO automatic correction happens
   - The system analyzes text and fixes:
     - wrong layout
     - typos
     - spelling
     - basic punctuation
2. It MUST:
   - NOT rewrite or paraphrase
   - NOT change meaning
   - Only “polish” what is already there

---

### Scope rules (VERY IMPORTANT)

- If there is a selection:
  - ONLY the selected text is processed
- If there is NO selection:
  - Process text from:
    - beginning of current line
    - OR last hard boundary (configurable, choose sensible default)

---

### Layout rule for polish mode

After polish is applied:

- Keyboard layout MUST be switched to the layout
  corresponding to the LAST word of the polished text

Rationale:
- user continues typing from there

---

### This mode MUST be:

- Explicit (hotkey only)
- Non-intrusive
- Deterministic
- Reversible via Undo

---

## 5. Tests That MUST Be Added

If these tests do not exist, ADD THEM.

### Layout & space tests

- `test_layout_switch_after_correction`
- `test_space_preserved_after_word_correction`
- `test_no_space_eaten_on_punctuation`

### API tests

- `test_api_model_list_populates_ui`
- `test_selected_api_model_used_in_request`

### Polish mode tests

- `test_polish_entire_line`
- `test_polish_selection_only`
- `test_layout_switched_to_last_word_after_polish`
- `test_polish_does_not_rewrite_text`

---

## 6. Runtime Validation (MANDATORY AGAIN)

You MUST perform real typing tests (VM or Xvfb):

Demonstrate at least:

1. Typing:
```

ghbdtn␣hello

```
Result:
```

привет␣hello

```

2. Typing long garbage phrase → press polish hotkey →
clean corrected phrase appears

3. Space is always visible on screen

Document:
- exact input
- exact output
- confirmation layout switched correctly

---

## Definition of Done

This fix is COMPLETE only if:

- Layout switches immediately after correction
- Space / punctuation is never swallowed
- API model is selectable and visible
- Polish mode works exactly as specified
- Inline and polish modes do not conflict
- All tests pass
- Version is bumped (e.g. 0.1.0-4)
- Behavior verified by real typing

---

## Non-Goals

- No Wayland
- No cloud APIs
- No rewriting / paraphrasing
- No “smart” guesses beyond correction

---

Proceed immediately.
Do not argue with the requirements.
Fix the system to match them.
