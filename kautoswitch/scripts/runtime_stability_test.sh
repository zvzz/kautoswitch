#!/bin/bash
# =============================================================================
# KAutoSwitch — Real Runtime Stability Test (Option 2: Manual-Assisted)
# =============================================================================
#
# This script starts kautoswitch with debug logging and provides a checklist
# for manually verifying that the feedback loop bug is fixed.
#
# Prerequisites:
#   - X11 session (echo $XDG_SESSION_TYPE should say "x11")
#   - kautoswitch installed (.deb) or venv activated
#   - XRecord + XTest extensions available
#
# What it proves:
#   - No infinite correction loop after replacement
#   - SPACE passes through after correction
#   - Each word is corrected exactly once
#   - Typing continues normally after correction
#
# Usage:
#   ./scripts/runtime_stability_test.sh
#
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="/tmp/kautoswitch-stability-test.log"

echo "=== KAutoSwitch Runtime Stability Test ==="
echo ""

# Check X11
if [ "${XDG_SESSION_TYPE:-}" != "x11" ] && [ -z "${DISPLAY:-}" ]; then
    echo "WARNING: Not in X11 session. This test requires X11."
    echo "  XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-unset}"
    echo "  DISPLAY=${DISPLAY:-unset}"
    echo ""
    echo "You can still run the non-X11 tests:"
    echo "  PYTHONPATH=$PROJECT_DIR python3 $PROJECT_DIR/tests/test_daemon_stability.py"
    echo "  PYTHONPATH=$PROJECT_DIR python3 $PROJECT_DIR/tests/test_stability.py"
    exit 1
fi

echo "X11 session detected: DISPLAY=${DISPLAY:-:0}"
echo "Log file: $LOG_FILE"
echo ""

# Determine how to run kautoswitch
KAUTOSWITCH_CMD=""
if command -v kautoswitch-daemon &>/dev/null; then
    KAUTOSWITCH_CMD="kautoswitch-daemon"
elif [ -f "$PROJECT_DIR/.venv/bin/python" ]; then
    KAUTOSWITCH_CMD="$PROJECT_DIR/.venv/bin/python -m kautoswitch.main --daemon"
else
    KAUTOSWITCH_CMD="python3 -m kautoswitch.main --daemon"
fi

echo "Starting daemon: $KAUTOSWITCH_CMD"
echo "Debug logging enabled → $LOG_FILE"
echo ""

# Kill any existing instance
pkill -f "kautoswitch.main" 2>/dev/null || true
sleep 0.5

# Start with debug logging
KAUTOSWITCH_DEBUG=1 PYTHONPATH="$PROJECT_DIR" $KAUTOSWITCH_CMD > "$LOG_FILE" 2>&1 &
DAEMON_PID=$!

echo "Daemon PID: $DAEMON_PID"
sleep 1

if ! kill -0 "$DAEMON_PID" 2>/dev/null; then
    echo "FAIL: Daemon failed to start. Check $LOG_FILE"
    cat "$LOG_FILE"
    exit 1
fi

echo "Daemon running."
echo ""
echo "================================================================"
echo " MANUAL TEST CHECKLIST"
echo "================================================================"
echo ""
echo " Open a text editor (Kate, KWrite, gedit, or terminal) and"
echo " perform the following steps. After each step, press ENTER here"
echo " to check the log for expected behavior."
echo ""

# Test 1: Basic correction
echo "--- TEST 1: Basic correction ---"
echo "  1. Switch keyboard to EN layout"
echo "  2. Type: ghbdtn"
echo "  3. Press SPACE"
echo "  Expected: 'ghbdtn' is replaced with 'привет '"
echo "  Expected log: exactly ONE 'Correcting:' line"
echo ""
read -p "  Press ENTER after typing 'ghbdtn' + SPACE... "

echo ""
echo "  Log analysis:"
CORRECT_COUNT=$(grep -c "Correcting:.*ghbdtn.*привет" "$LOG_FILE" 2>/dev/null || echo "0")
LOOP_COUNT=$(grep -c "LOOP\|re-trigger\|Idempotency" "$LOG_FILE" 2>/dev/null || echo "0")

if [ "$CORRECT_COUNT" -eq 1 ]; then
    echo "  [PASS] Exactly 1 correction: ghbdtn → привет"
elif [ "$CORRECT_COUNT" -eq 0 ]; then
    echo "  [INFO] No correction logged (might be expected if daemon didn't capture input)"
else
    echo "  [FAIL] $CORRECT_COUNT corrections logged — FEEDBACK LOOP!"
fi

if [ "$LOOP_COUNT" -gt 0 ]; then
    echo "  [INFO] Idempotency guard triggered $LOOP_COUNT time(s) — guard working"
fi

echo ""

# Test 2: No re-trigger after correction
echo "--- TEST 2: Typing continues after correction ---"
echo "  1. After 'привет ' appeared, continue typing: мир"
echo "  2. Press SPACE"
echo "  Expected: 'мир' remains unchanged (valid Russian word)"
echo "  Expected: cursor is after 'мир '"
echo ""
read -p "  Press ENTER after typing 'мир' + SPACE... "

echo ""
echo "  Log analysis:"
MIR_CORRECT=$(grep -c "Correcting:.*мир" "$LOG_FILE" 2>/dev/null || echo "0")
if [ "$MIR_CORRECT" -eq 0 ]; then
    echo "  [PASS] 'мир' was NOT corrected (valid word)"
else
    echo "  [FAIL] 'мир' was incorrectly corrected $MIR_CORRECT time(s)"
fi

echo ""

# Test 3: Second wrong-layout word
echo "--- TEST 3: Second correction (no cascade) ---"
echo "  1. Type: vbh"
echo "  2. Press SPACE"
echo "  Expected: 'vbh' is replaced with 'мир '"
echo "  Expected log: exactly ONE new 'Correcting:' line for vbh"
echo ""
read -p "  Press ENTER after typing 'vbh' + SPACE... "

echo ""
echo "  Log analysis:"
VBH_COUNT=$(grep -c "Correcting:.*vbh.*мир" "$LOG_FILE" 2>/dev/null || echo "0")
if [ "$VBH_COUNT" -eq 1 ]; then
    echo "  [PASS] Exactly 1 correction: vbh → мир"
elif [ "$VBH_COUNT" -eq 0 ]; then
    echo "  [INFO] No correction logged for vbh"
else
    echo "  [FAIL] $VBH_COUNT corrections for vbh — cascade!"
fi

echo ""

# Test 4: Undo
echo "--- TEST 4: Undo ---"
echo "  1. Press Ctrl+/"
echo "  Expected: last correction is undone (мир → vbh)"
echo ""
read -p "  Press ENTER after pressing Ctrl+/ ... "

UNDO_COUNT=$(grep -c "Undo:" "$LOG_FILE" 2>/dev/null || echo "0")
if [ "$UNDO_COUNT" -ge 1 ]; then
    echo "  [PASS] Undo logged ($UNDO_COUNT total)"
else
    echo "  [INFO] No undo logged"
fi

echo ""

# Summary
echo "================================================================"
echo " SUMMARY"
echo "================================================================"
echo ""
TOTAL_CORRECTIONS=$(grep -c "Correcting:" "$LOG_FILE" 2>/dev/null || echo "0")
TOTAL_LOOPS=$(grep -c "Idempotency guard" "$LOG_FILE" 2>/dev/null || echo "0")
TOTAL_SUPPRESS=$(grep -c "Suppression ON" "$LOG_FILE" 2>/dev/null || echo "0")

echo "  Total corrections:       $TOTAL_CORRECTIONS"
echo "  Idempotency guards:      $TOTAL_LOOPS"
echo "  Suppression activations: $TOTAL_SUPPRESS"
echo ""

if [ "$TOTAL_CORRECTIONS" -le 3 ] && [ "$TOTAL_CORRECTIONS" -ge 1 ]; then
    echo "  RESULT: STABLE — corrections are bounded, no infinite loop"
else
    echo "  RESULT: Check log for anomalies"
fi

echo ""
echo "  Full log: $LOG_FILE"
echo "  Relevant lines:"
grep -E "(Correcting:|Undo:|Idempotency|Suppression|LOOP)" "$LOG_FILE" 2>/dev/null || echo "  (no matching log lines)"

echo ""

# Cleanup
echo "Stopping daemon (PID $DAEMON_PID)..."
kill "$DAEMON_PID" 2>/dev/null || true
wait "$DAEMON_PID" 2>/dev/null || true
echo "Done."
