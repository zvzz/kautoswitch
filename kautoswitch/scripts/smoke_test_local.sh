#!/bin/bash
# Smoke test for kautoswitch after .deb install.
# Verifies: module imports, config paths, unit files, desktop files, corrector pipeline.
# Does NOT require X11 for most checks.
set -euo pipefail

PASS=0
FAIL=0

check() {
    local name="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  [PASS] $name"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $name"
        FAIL=$((FAIL + 1))
    fi
}

check_file() {
    local name="$1"
    local path="$2"
    if [ -f "$path" ]; then
        echo "  [PASS] $name ($path)"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $name — not found: $path"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== KAutoSwitch Smoke Test ==="
echo ""

echo "1) Python module import"
check "import kautoswitch" python3 -c "import kautoswitch"
check "import kautoswitch.main" python3 -c "from kautoswitch.main import main"
check "import kautoswitch.config" python3 -c "from kautoswitch.config import Config"
check "import kautoswitch.corrector" python3 -c "from kautoswitch.corrector import Corrector"
check "import kautoswitch.tinyllm" python3 -c "from kautoswitch.tinyllm import TinyLLM"
check "import kautoswitch.layout_map" python3 -c "from kautoswitch.layout_map import map_en_to_ru"
check "import kautoswitch.spellcheck_compat" python3 -c "from kautoswitch.spellcheck_compat import SpellChecker"

echo ""
echo "2) Config path"
CONFIG_DIR="$HOME/.config/kautoswitch"
check "config dir writable" test -d "$CONFIG_DIR" -o -w "$(dirname "$CONFIG_DIR")"

echo ""
echo "3) Installed files"
check_file "systemd user unit" "/usr/lib/systemd/user/kautoswitch.service"
check_file "autostart desktop" "/etc/xdg/autostart/kautoswitch-tray.desktop"
check_file "kautoswitch binary" "/usr/bin/kautoswitch"
check_file "kautoswitch-daemon binary" "/usr/bin/kautoswitch-daemon"
check_file "kautoswitch-tray binary" "/usr/bin/kautoswitch-tray"

echo ""
echo "4) Corrector pipeline (non-X11)"
check "layout map: Ghbdtn→Привет" \
    python3 -c "from kautoswitch.layout_map import map_en_to_ru; assert map_en_to_ru('Ghbdtn') == 'Привет'"

check "corrector: jy→он" \
    python3 -c "
from kautoswitch.config import Config
from kautoswitch.corrector import Corrector
c = Corrector(Config())
r = c.correct('jy')
assert r is not None and r[0] == 'он', f'got {r}'
"

check "corrector: ывгключил→выключил" \
    python3 -c "
from kautoswitch.config import Config
from kautoswitch.corrector import Corrector
c = Corrector(Config())
r = c.correct('ывгключил')
assert r is not None and r[0] == 'выключил', f'got {r}'
"

check "corrector: Hello→None (unchanged)" \
    python3 -c "
from kautoswitch.config import Config
from kautoswitch.corrector import Corrector
c = Corrector(Config())
r = c.correct('Hello')
assert r is None, f'got {r}'
"

check "corrector: GHBDTN→None (caps)" \
    python3 -c "
from kautoswitch.config import Config
from kautoswitch.corrector import Corrector
c = Corrector(Config())
r = c.correct('GHBDTN')
assert r is None, f'got {r}'
"

check "tinyllm: Ghbdtn vbh→Привет мир" \
    python3 -c "
from kautoswitch.tinyllm import TinyLLM
t = TinyLLM()
r = t.correct('Ghbdtn vbh')
assert r == 'Привет мир', f'got {r}'
"

check "rules: 3x undo suppression" \
    python3 -c "
from kautoswitch.rules import RuleStore
r = RuleStore()
r.clear()
r.record_undo('smoke_test')
r.record_undo('smoke_test')
assert r.record_undo('smoke_test') == True
assert r.is_suppressed('smoke_test')
r.clear()
"

echo ""
echo "5) X11 checks (may fail in headless)"
check "XRecord available (python3-xlib)" \
    python3 -c "from Xlib.ext import record" || true

echo ""
echo "========================================="
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    echo "SOME CHECKS FAILED — see above"
    exit 1
else
    echo "ALL CHECKS PASSED"
fi

echo ""
echo "Manual X11 verification steps:"
echo "  1. Run: kautoswitch"
echo "  2. Verify tray icon appears (green circle with П)"
echo "  3. Open any text editor"
echo "  4. Type 'Ghbdtn' + space → should become 'Привет'"
echo "  5. Press Ctrl+/ to undo"
echo "  6. Right-click tray → Disable → type wrong text → no correction"
