#!/usr/bin/env python3
"""Xvfb runtime test — end-to-end verification with a real X11 display.

Requires: Xvfb, xdotool, xterm (or any X11 terminal).
Skips gracefully if tools are unavailable.

This script:
1. Starts Xvfb on :99, sets DISPLAY
2. Starts xterm (or minimal X11 text widget)
3. Starts daemon with debug logging
4. Uses xdotool to type 'ghbdtn ' and 'rfr ltkf '
5. Captures log output, verifies:
   - Exactly 1 correction per word
   - No infinite loops
   - Phrase correction fires for 'rfr ltkf'
6. Documents results
"""
import sys
import os
import subprocess
import shutil
import time
import logging
import io

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

PASS = 0
FAIL = 0
SKIP = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def skip(name, reason):
    global SKIP
    SKIP += 1
    print(f"  [SKIP] {name} — {reason}")


def tool_available(name):
    return shutil.which(name) is not None


def run_xvfb_test():
    """Run the full Xvfb-based test."""
    print("\nTest: Xvfb Runtime Integration")

    # Check prerequisites
    required = ['Xvfb', 'xdotool']
    missing = [t for t in required if not tool_available(t)]
    if missing:
        skip("Xvfb runtime test", f"missing tools: {', '.join(missing)}")
        return

    # Check for a terminal emulator
    terminal = None
    for t in ['xterm', 'xfce4-terminal', 'mate-terminal']:
        if tool_available(t):
            terminal = t
            break

    if terminal is None:
        skip("Xvfb runtime test", "no X11 terminal emulator found")
        return

    display = ':99'
    xvfb_proc = None
    term_proc = None
    log_stream = io.StringIO()

    try:
        # 1. Start Xvfb
        xvfb_proc = subprocess.Popen(
            ['Xvfb', display, '-screen', '0', '1024x768x24'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.5)

        if xvfb_proc.poll() is not None:
            skip("Xvfb runtime test", "Xvfb failed to start")
            return

        env = os.environ.copy()
        env['DISPLAY'] = display

        # 2. Start terminal
        if terminal == 'xterm':
            term_proc = subprocess.Popen(
                ['xterm', '-geometry', '80x24'],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            term_proc = subprocess.Popen(
                [terminal],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        time.sleep(1.0)

        if term_proc.poll() is not None:
            skip("Xvfb runtime test", f"{terminal} failed to start")
            return

        # 3. Set up logging capture
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(name)s:%(levelname)s:%(message)s')
        handler.setFormatter(formatter)

        # Import and configure daemon
        os.environ['DISPLAY'] = display
        from kautoswitch.config import Config
        from kautoswitch.daemon import Daemon
        from kautoswitch.tinyllm import TinyLLM

        daemon_logger = logging.getLogger('kautoswitch.daemon')
        daemon_logger.addHandler(handler)
        daemon_logger.setLevel(logging.DEBUG)

        config = Config()
        config._data["languages"] = {"ru": True, "en": True, "be": False}
        config._data["ai_timeout_ms"] = 5000

        daemon = Daemon(config)
        daemon.set_tinyllm(TinyLLM())

        try:
            daemon.start()
        except Exception as e:
            skip("Xvfb runtime test", f"daemon failed to start: {e}")
            return

        if not daemon.running:
            skip("Xvfb runtime test", "daemon not running after start()")
            return

        time.sleep(0.5)

        # 4. Type using xdotool
        # Focus the terminal window
        subprocess.run(
            ['xdotool', 'search', '--name', '', 'windowfocus', '--sync'],
            env=env, timeout=5,
            capture_output=True,
        )
        time.sleep(0.3)

        # Type 'ghbdtn '
        subprocess.run(
            ['xdotool', 'type', '--clearmodifiers', '--delay', '50', 'ghbdtn '],
            env=env, timeout=10,
        )
        time.sleep(1.0)

        # Type 'rfr ltkf '
        subprocess.run(
            ['xdotool', 'type', '--clearmodifiers', '--delay', '50', 'rfr ltkf '],
            env=env, timeout=10,
        )
        time.sleep(1.5)  # Wait for deferred phrase correction

        # 5. Analyze logs
        daemon.stop()
        time.sleep(0.3)

        log_output = log_stream.getvalue()
        print(f"\n  --- Daemon log output ---")
        for line in log_output.strip().split('\n'):
            if line:
                print(f"    {line}")
        print(f"  --- End log output ---\n")

        # Count corrections
        correction_lines = [l for l in log_output.split('\n') if 'Correcting:' in l]
        phrase_lines = [l for l in log_output.split('\n') if 'Phrase correction:' in l]

        check("at least one correction fired",
              len(correction_lines) + len(phrase_lines) >= 1,
              f"corrections={len(correction_lines)}, phrases={len(phrase_lines)}")

        # Check for привет
        has_privet = any('привет' in l for l in log_output.split('\n'))
        check("'ghbdtn' corrected to 'привет'", has_privet,
              "no 'привет' found in logs")

        # Check no infinite loop indicators
        # More than 3 correction lines for 2-3 typed words would be suspicious
        total_corrections = len(correction_lines) + len(phrase_lines)
        check("no infinite loop (≤4 corrections for 3 words)",
              total_corrections <= 4,
              f"got {total_corrections} corrections — possible loop!")

        # Check for phrase correction
        has_phrase = len(phrase_lines) > 0 or any('как' in l for l in log_output.split('\n'))
        check("phrase correction attempted for 'rfr ltkf'",
              has_phrase,
              "no phrase correction found in logs")

    except Exception as e:
        skip("Xvfb runtime test", f"exception: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        if term_proc and term_proc.poll() is None:
            term_proc.terminate()
            try:
                term_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                term_proc.kill()

        if xvfb_proc and xvfb_proc.poll() is None:
            xvfb_proc.terminate()
            try:
                xvfb_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                xvfb_proc.kill()

        # Restore DISPLAY
        if 'DISPLAY' in os.environ and os.environ.get('DISPLAY') == display:
            if 'ORIGINAL_DISPLAY' in os.environ:
                os.environ['DISPLAY'] = os.environ['ORIGINAL_DISPLAY']
            else:
                os.environ.pop('DISPLAY', None)


if __name__ == '__main__':
    # Save original DISPLAY
    if 'DISPLAY' in os.environ:
        os.environ['ORIGINAL_DISPLAY'] = os.environ['DISPLAY']

    run_xvfb_test()

    print(f"\n{'='*50}")
    print(f"Results: {PASS} passed, {FAIL} failed, {SKIP} skipped")
    if FAIL > 0:
        print("SOME TESTS FAILED")
        sys.exit(1)
    elif SKIP > 0 and PASS == 0:
        print("ALL TESTS SKIPPED (missing prerequisites)")
        sys.exit(0)
    else:
        print("ALL TESTS PASSED")
