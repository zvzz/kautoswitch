"""Architectural test: daemon.py must NOT import or call layout_switch.

Xlib is NOT thread-safe. The daemon runs on XRecord/Timer threads.
Any X11 call from daemon → guaranteed segfault.

This test ensures the architecture rule is enforced at the code level.
"""
import sys
import os
import ast
import inspect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

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


# ====================================================================
# Test 1: daemon.py does NOT import layout_switch
# ====================================================================
def test_daemon_no_layout_switch_import():
    """daemon.py must not import from kautoswitch.layout_switch."""
    print("\nTest 1: daemon.py does NOT import layout_switch")

    daemon_path = os.path.join(
        os.path.dirname(__file__), '..', 'kautoswitch', 'daemon.py'
    )
    with open(daemon_path, 'r') as f:
        source = f.read()

    tree = ast.parse(source)

    forbidden_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and 'layout_switch' in node.module:
                names = [alias.name for alias in node.names]
                forbidden_imports.append(f"from {node.module} import {', '.join(names)}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if 'layout_switch' in alias.name:
                    forbidden_imports.append(f"import {alias.name}")

    check("no layout_switch imports",
          len(forbidden_imports) == 0,
          f"found: {forbidden_imports}")


# ====================================================================
# Test 2: daemon.py does NOT contain X11-unsafe symbols
# ====================================================================
def test_daemon_no_x11_symbols():
    """daemon.py must not contain subprocess, ctypes, setxkbmap, xkb-switch calls."""
    print("\nTest 2: daemon.py does NOT contain X11-unsafe symbols")

    daemon_path = os.path.join(
        os.path.dirname(__file__), '..', 'kautoswitch', 'daemon.py'
    )
    with open(daemon_path, 'r') as f:
        source = f.read()

    # These symbols must NOT appear in daemon.py (except in comments)
    forbidden = ['subprocess', 'ctypes', 'setxkbmap', 'xkb-switch', 'xdotool',
                 'switch_to_layout', 'switch_to_corrected_layout',
                 'get_current_layout', 'XkbLockGroup', 'XkbGetState']

    # Parse AST to check actual code, not comments
    tree = ast.parse(source)

    # Collect all Name and Attribute references
    code_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            code_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            code_names.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Check string literals too (subprocess calls via string)
            for sym in forbidden:
                if sym in node.value:
                    code_names.add(sym)

    found = []
    for sym in forbidden:
        if sym in code_names:
            found.append(sym)

    check("no X11-unsafe symbols in code",
          len(found) == 0,
          f"found: {found}")


# ====================================================================
# Test 3: daemon has _requested_layout field (handoff mechanism)
# ====================================================================
def test_daemon_has_layout_request_field():
    """Daemon must have _requested_layout for signaling layout switch intent."""
    print("\nTest 3: daemon has _requested_layout handoff field")

    from kautoswitch.config import Config
    from kautoswitch.daemon import Daemon

    config = Config()
    daemon = Daemon(config)

    check("_requested_layout field exists",
          hasattr(daemon, '_requested_layout'))
    check("_requested_layout initially None",
          daemon._requested_layout is None)
    check("consume_layout_request method exists",
          hasattr(daemon, 'consume_layout_request') and callable(daemon.consume_layout_request))

    # Test consume_layout_request
    daemon._requested_layout = 'ru'
    result = daemon.consume_layout_request()
    check("consume_layout_request returns 'ru'",
          result == 'ru',
          f"got: {result}")
    check("consume_layout_request clears field",
          daemon._requested_layout is None)

    # Consuming again returns None
    result2 = daemon.consume_layout_request()
    check("second consume returns None",
          result2 is None)


# ====================================================================
# Test 4: detect_target_layout lives in layout_map (not X11-dependent)
# ====================================================================
def test_detect_target_layout_in_layout_map():
    """detect_target_layout must be importable from layout_map (pure logic)."""
    print("\nTest 4: detect_target_layout in layout_map (no X11)")

    from kautoswitch.layout_map import detect_target_layout

    check("detect_target_layout importable from layout_map", True)

    # Verify it works correctly
    check("RU text → 'ru'",
          detect_target_layout('привет') == 'ru')
    check("EN text → 'us'",
          detect_target_layout('hello') == 'us')
    check("empty → None",
          detect_target_layout('') is None)
    check("numbers → None",
          detect_target_layout('12345') is None)


# ====================================================================
if __name__ == '__main__':
    test_daemon_no_layout_switch_import()
    test_daemon_no_x11_symbols()
    test_daemon_has_layout_request_field()
    test_detect_target_layout_in_layout_map()

    print(f"\n{'='*50}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        print("SOME TESTS FAILED")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
