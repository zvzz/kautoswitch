# KAutoSwitch

Local-only keyboard layout auto-corrector for Ubuntu KDE (X11).
Intercepts keystrokes globally, detects wrong keyboard layout / typos / mixed-layout words, and corrects them in-place.

## Install from .deb (recommended for target machines)

### Build the .deb

On a machine with build tools:
```bash
# Path A: build on host
sudo apt-get install -y devscripts debhelper dh-python python3-all python3-setuptools
cd kautoswitch
dpkg-buildpackage -us -uc -b
# .deb appears in parent directory

# Path B: build in container (preferred)
./scripts/build_deb.sh --container
# .deb appears in dist/
```

### Install on target machine

```bash
sudo apt install ./kautoswitch_0.1.0-1_all.deb
```

This installs all dependencies automatically (`python3-xlib`, `python3-pyqt5`, `python3-requests`, `xdotool`) and the vendored spell checker.

### Enable the service

```bash
# Reload systemd user units
systemctl --user daemon-reload

# Enable and start the daemon
systemctl --user enable --now kautoswitch.service

# Verify
systemctl --user status kautoswitch.service
```

The tray icon auto-starts on next login via `/etc/xdg/autostart/kautoswitch-tray.desktop`.
To start it immediately without re-login:
```bash
kautoswitch-tray &
```

### Disable / uninstall

```bash
# Stop and disable
systemctl --user disable --now kautoswitch.service

# Uninstall
sudo apt remove kautoswitch
```

### Smoke test after install

```bash
/usr/share/kautoswitch/smoke_test_local.sh
```

### Verify on target machine

1. `sudo apt install ./kautoswitch_*.deb`
2. `systemctl --user daemon-reload && systemctl --user enable --now kautoswitch.service`
3. `systemctl --user status kautoswitch.service` — should show active (running)
4. Tray icon appears (green circle with "П") on next login or `kautoswitch-tray &`
5. Open any text field, type `Ghbdtn` + space → becomes `Привет`
6. Press `Ctrl+/` to undo
7. `/usr/share/kautoswitch/smoke_test_local.sh` — all checks pass

---

## Development Setup

## Requirements

- Ubuntu (KDE Plasma recommended) with X11 session
- Python 3.8+
- X11 (XRecord + XTest extensions)
- xdotool (fallback for Unicode input)

### System packages

```bash
sudo apt-get install -y python3-venv python3-dev xdotool
# For hunspell dictionaries (optional, pyspellchecker includes built-in dicts):
sudo apt-get install -y hunspell hunspell-ru hunspell-en-us
```

## Build

```bash
cd kautoswitch

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install pyspellchecker

# Install the package
pip install -e .
```

## Run

```bash
# Activate venv
source .venv/bin/activate

# Run the application
python -m kautoswitch.main
```

Or after `pip install -e .`:
```bash
kautoswitch
```

### What you should see

1. A green circle icon with "П" appears in the system tray
2. Right-click the icon for: Enable/Disable, Model selection, Language toggles, Settings
3. Start typing in any application — wrong-layout text will be auto-corrected

### Hotkeys

| Hotkey | Action |
|---|---|
| `Ctrl+/` | Undo last auto-correction |
| `Ctrl+Shift+/` | Rethink last input (re-run correction) |
| `Ctrl+Shift+P` | Toggle enable/disable |

## Test

### Unit / integration tests (no X11 required)

```bash
source .venv/bin/activate
cd kautoswitch
PYTHONPATH=. python tests/test_integration.py
```

### Manual test checklist (requires X11 session)

1. **Wrong layout**: Open a text editor. Switch to EN layout. Type `Ghbdtn vbh` then space.
   Expected: text is replaced with `Привет мир`.

2. **Typo correction**: Switch to RU layout. Type `ывгключил` then space.
   Expected: text is replaced with `выключил`.

3. **Mixed layout**: Type `выклюchил` then space.
   Expected: text is replaced with `выключил`.

4. **Correct text unchanged**: Type `Hello world` then space.
   Expected: no change.

5. **CapsLock**: Enable CapsLock. Type `GHBDTN VBH`.
   Expected: no correction.

6. **Undo**: After a correction happens, press `Ctrl+/`.
   Expected: original text restored.

7. **Learning rule**: Undo the same correction 3 times. Type the same text again.
   Expected: no auto-correction.

8. **Disable**: Right-click tray → Disable. Type wrong-layout text.
   Expected: no correction.

9. **Global scope**: Test corrections in terminal, browser, and messenger.

## Architecture

```
┌────────────────────────────────────────────────────┐
│              kautoswitch (single process)             │
│                                                    │
│  X11 Listener → Buffer → Corrector → Replacer     │
│  (XRecord)      (word)   (pipeline)   (XTest)      │
│                    ↕                                │
│              Undo Stack ← Rule Store               │
│                                                    │
│  ┌──────────────────────────────────────────────┐  │
│  │ TinyLLM (rule-based) │ API Client (optional) │  │
│  └──────────────────────────────────────────────┘  │
│                                                    │
│  ┌──────────────────────────────────────────────┐  │
│  │     PyQt5: System Tray + Settings Window     │  │
│  └──────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────┘
```

### Correction pipeline

1. Keystroke → XRecord listener → character
2. Character → word buffer (accumulates until space/punctuation)
3. Word complete → correction pipeline:
   - Check suppression rules (3x undo learning)
   - Try phrase-level layout swap (multiple words)
   - Try single-word layout swap (QWERTY↔ЙЦУКЕН)
   - Try mixed-layout fix (e.g. `выклюchил` → `выключил`)
   - Try spell correction (Damerau-Levenshtein, pyspellchecker)
   - Try TinyLLM / API (semantic fallback)
4. If correction found with confidence ≥ threshold:
   - Push original to undo stack
   - Send Backspace×N via XTest
   - Send corrected characters via XTest

### Text replacement

Uses XTest synthetic key events (NOT clipboard). Procedure:
1. Suppress XRecord listener (avoid feedback loop)
2. Send Backspace × (word length + 1)
3. Send corrected characters one by one
4. Re-enable listener

## Configuration

Config file: `~/.config/kautoswitch/config.json`

```json
{
  "enabled": true,
  "languages": {"ru": true, "en": true, "be": false},
  "model": "tinyllm",
  "api_url": "http://localhost:8080/v1/correct",
  "ai_timeout_ms": 100,
  "hotkey_undo": "ctrl+/",
  "hotkey_rethink": "ctrl+shift+/",
  "hotkey_toggle": "ctrl+shift+p",
  "debug_logging": false,
  "correction_confidence_threshold": 0.6
}
```

Learned rules (3x undo): `~/.config/kautoswitch/learned_rules.json`

## API Mode

When model is set to "api", correction requests are sent to a local HTTP endpoint:

```
POST http://localhost:8080/v1/correct
Content-Type: application/json

{
  "prompt": "<tinyllm_prompt.md content>\n<RAW_INPUT>\n...\n</RAW_INPUT>",
  "text": "raw input text",
  "context": "surrounding context",
  "max_tokens": 100,
  "temperature": 0.0
}
```

Expected response (any of these formats):
```json
{"output": "<OUTPUT>\ncorrected text\n</OUTPUT>"}
{"text": "corrected text"}
{"choices": [{"text": "corrected text"}]}
```

## Known Limitations

1. **X11 only**: Requires X11 session. Wayland is not supported (XRecord/XTest are X11-only).
   - Under Wayland, the app will start but input interception will not work.
   - Documented limitation per contract. See "Wayland" section below.

2. **Grammar-level correction**: The built-in TinyLLM is rule-based and cannot do grammar analysis.
   - Example: `b jy dsrk.xb` maps to `и он выключи` (layout swap). The final `'л'` in `'выключил'` requires grammatical inference that `'он выключи'` should be `'он выключил'`.
   - Use API mode with an actual LLM for grammar-aware corrections.

3. **Single-character words**: Ambiguous in isolation (e.g., `'b'` is valid English).
   - Handled by phrase-level correction (corrected when context is available).

4. **Speed**: pyspellchecker dictionary lookups add some overhead.
   - The 100ms timeout is enforced; if correction takes too long, it's skipped.

## Wayland

**Status: Not supported (documented limitation)**

The application uses XRecord for input interception and XTest for synthetic key events. Both are X11-only APIs that do not work under Wayland.

Potential future approaches:
- evdev (`/dev/input`) for input (requires `input` group membership)
- uinput for synthetic events
- Input method framework (Fcitx5 / IBus module)

These are explicitly out of scope per the project contract.

## Troubleshooting

### Tray icon not visible
- Ensure you're running KDE Plasma with system tray support
- Try `QT_QPA_PLATFORM=xcb` environment variable

### Input not intercepted
- Verify X11 session: `echo $XDG_SESSION_TYPE` should say `x11`
- Check XRecord extension: `xdpyinfo | grep RECORD`
- Check XTest extension: `xdpyinfo | grep XTEST`

### Corrections not working
- Enable debug logging in Settings → Advanced → Debug logging
- Check terminal output for correction decisions
- Verify with: `python -c "from kautoswitch.tinyllm import TinyLLM; t=TinyLLM(); print(t.correct('Ghbdtn'))"`

### Permission errors
- XRecord/XTest should work without root
- If using evdev fallback (experimental): `sudo usermod -aG input $USER`

### Troubleshooting on target machine (after .deb install)

**Service won't start:**
```bash
systemctl --user status kautoswitch.service
journalctl --user -u kautoswitch.service -n 20
```

**DISPLAY not set in systemd user service:**
KDE/Plasma typically exports DISPLAY to the user session. If not:
```bash
systemctl --user set-environment DISPLAY=:0
systemctl --user restart kautoswitch.service
```

**Missing dependencies after install:**
```bash
apt --fix-broken install
```

**Module import errors:**
```bash
python3 -c "import kautoswitch; print('OK')"
# If fails, check: dpkg -L kautoswitch | grep python
```
