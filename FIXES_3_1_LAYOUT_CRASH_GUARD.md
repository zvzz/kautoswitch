# FIXES_3_1_LAYOUT_CRASH_GUARD.md
## Prevent Fatal Crashes During Layout Switching

This is a CRITICAL hotfix.

The daemon currently crashes immediately after first correction.
This is unacceptable.

---

## Root Cause

Layout switching logic is executed in real X11 environment
without sufficient guards.

Any failure in layout detection or switching MUST NOT crash the daemon.

---

## Mandatory Rules (Non-Negotiable)

1. Layout switching MUST be best-effort
2. Layout switching MUST be wrapped in try/except
3. ANY exception during layout switch:
   - must be logged
   - must NOT propagate
   - must NOT stop correction flow
4. If layout cannot be switched:
   - continue in handoff mode
   - user will manually type correct layout

---

## Required Code Changes

### In layout_switch.py

- Wrap ALL external calls:
  - subprocess
  - Xlib
  - xkb-switch
  in try/except Exception

- No function in this module may raise uncaught exception

Example pattern (conceptual):

```python
try:
    switch_layout(...)
except Exception as e:
    log.warning("Layout switch failed: %s", e)
````

---

### Threading Safety

* Layout switching MUST run:

  * in main daemon thread
  * NOT inside timer threads
  * NOT inside synthetic input emission

If currently called from timer or background thread:

* move call to main event loop
* or queue it safely

---

## Tests to Add

* test_layout_switch_failure_does_not_crash
* simulate missing xkb-switch binary
* simulate Xlib exception
* daemon must remain alive

---

## Runtime Validation (MANDATORY)

* Run daemon on real X11
* Type:

  ```
  rfr␣
  ```
* Observe:

  * correction happens
  * daemon continues running
  * no crash
  * warning logged if layout switch fails

---

## Definition of Done

* kautoswitch does NOT crash on first correction
* layout switching failure is non-fatal
* daemon stays alive indefinitely

