# Acceptance Tests, Failure Recovery Rules & Minimal X11 Tech Spec
This document is a mandatory extension to CLAUDE_TASK_CONTRACT.md

You MUST implement until all Acceptance Tests pass.
You MUST obey Failure Recovery Rules.
You MUST follow the Minimal X11 Tech Spec unless explicitly blocked.

====================================================================
PART A — ACCEPTANCE TESTS
====================================================================

All tests below MUST pass on Ubuntu KDE (X11 session).

--------------------------------------------------
A1. Basic wrong-layout correction
--------------------------------------------------
Input sequence (typed naturally, no Enter):
  b jy dsrk.xb

Expected visible result:
  и он выключил

Requirements:
- correction happens automatically
- correction happens while typing or immediately after last character
- no manual hotkey required
- no cursor jump
- no extra characters

--------------------------------------------------
A2. Typo correction (same layout)
--------------------------------------------------
Input:
  он ывгключил

Expected:
  он выключил

Requirements:
- fixes internal typos
- preserves spaces
- preserves original word order

--------------------------------------------------
A3. Mixed-layout word
--------------------------------------------------
Input:
  выклюchил

Expected:
  выключил

--------------------------------------------------
A4. Correct text must remain unchanged
--------------------------------------------------
Input:
  Hello world

Expected:
  Hello world

Requirements:
- no correction
- no flicker
- no replacement attempt

--------------------------------------------------
A5. CapsLock non-interference
--------------------------------------------------
Input:
  GHBDTN VBH

Expected:
  GHBDTN VBH

Requirements:
- NO correction
- NO layout switch
- NO undo entry

--------------------------------------------------
A6. Undo last correction
--------------------------------------------------
Steps:
1. Type: b jy dsrk.xb
2. Observe auto-correction
3. Press Undo hotkey

Expected:
- original text restored exactly: b jy dsrk.xb
- cursor position restored correctly

--------------------------------------------------
A7. Rethink last input
--------------------------------------------------
Steps:
1. Type incorrect text
2. Trigger "rethink last input" hotkey

Expected:
- correction is re-applied using current model/settings

--------------------------------------------------
A8. Learning rule (3x undo)
--------------------------------------------------
Steps:
1. Type same incorrect pattern
2. Undo correction
3. Repeat 3 times total
4. Type same pattern again

Expected:
- NO auto-correction anymore
- rule stored persistently
- rule survives restart

--------------------------------------------------
A9. Global scope
--------------------------------------------------
Repeat A1–A6 in:
- terminal (bash)
- browser text input
- messenger input
- Qt application text field

Expected:
- identical behavior everywhere

--------------------------------------------------
A10. Disable behavior
--------------------------------------------------
Steps:
1. Disable via tray
2. Type incorrect text

Expected:
- NO correction
- NO undo entries
- typing works normally

====================================================================
PART B — FAILURE RECOVERY RULES
====================================================================

The system MUST remain safe under all failure conditions.

--------------------------------------------------
B1. AI timeout
--------------------------------------------------
If AI (TinyLLM or API) does not respond within timeout:
- typing MUST continue normally
- no freeze
- no partial replacement
- correction skipped silently

--------------------------------------------------
B2. AI crash / unavailable
--------------------------------------------------
If AI module crashes or fails to load:
- daemon continues running
- rule-based minimal layout correction MAY be used
- OR correction skipped
- user is notified via tray state

--------------------------------------------------
B3. Daemon crash
--------------------------------------------------
If daemon crashes:
- system typing MUST NOT be blocked
- no stuck grabs
- user can continue typing immediately

--------------------------------------------------
B4. GUI crash
--------------------------------------------------
If GUI crashes:
- daemon continues working
- typing correction still functions
- GUI can be restarted independently

--------------------------------------------------
B5. Input safety
--------------------------------------------------
Under NO circumstances:
- input may be lost
- input may be duplicated
- keyboard may be locked
- focus may be stolen

--------------------------------------------------
B6. Emergency escape
--------------------------------------------------
There MUST exist a way to fully disable functionality:
- tray toggle OR
- config flag
- disabling must be immediate and safe

====================================================================
PART C — MINIMAL X11 TECH SPEC (MANDATORY)
====================================================================

This defines the MINIMUM acceptable X11 implementation.
Do NOT over-engineer.

--------------------------------------------------
C1. Input interception (X11)
--------------------------------------------------
Preferred methods (in order):
1. XInput2 (XI_RawKeyPress / XI_RawKeyRelease)
2. XRecord extension

Requirements:
- global (no focused window dependency)
- non-blocking
- no keyboard grab

--------------------------------------------------
C2. Key interpretation
--------------------------------------------------
- Use XKB to resolve:
  - keycode → keysym
  - respect current layout
- Track:
  - characters
  - backspace
  - word boundaries

--------------------------------------------------
C3. Text replacement
--------------------------------------------------
Replacement MUST be done via:
- synthetic key events (XTest / equivalent)

Procedure:
1. Send Backspace N times
2. Send corrected characters
3. Restore cursor position if needed

Clipboard-based replacement is FORBIDDEN.

--------------------------------------------------
C4. Layout switching
--------------------------------------------------
- Prefer XKB API
- setxkbmap usage acceptable as fallback
- switching must be deterministic

--------------------------------------------------
C5. Threading model
--------------------------------------------------
- Input hook MUST be realtime-safe
- AI processing MUST be async
- Hard timeout enforced
- No blocking in input path

--------------------------------------------------
C6. Wayland stance
--------------------------------------------------
Wayland support MAY be:
- experimental
- limited
- disabled by default

But MUST:
- be explicitly documented
- NOT silently fail
- NOT degrade X11 behavior

====================================================================
END OF DOCUMENT
