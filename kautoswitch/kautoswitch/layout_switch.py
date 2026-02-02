"""Keyboard layout switching via X11 (setxkbmap / xdotool / ctypes XKB).

CRITICAL RULE: No function in this module may raise an uncaught exception.
Every external call (subprocess, ctypes) is wrapped in try/except.
Layout switching is best-effort — failure is logged and silently ignored.

NOTE: python-xlib is NOT used here. All X11 calls use ctypes with proper
XOpenDisplay/XCloseDisplay. Mixing python-xlib Display objects with ctypes
Xkb calls causes segfaults (fileno() returns int, not Display*).
"""
import ctypes
import ctypes.util
import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Layout names as used by setxkbmap
LAYOUT_EN = 'us'
LAYOUT_RU = 'ru'

# --------------------------------------------------------------------------
# ctypes bindings for libX11 XKB functions
# --------------------------------------------------------------------------
_libX11 = None

try:
    _lib_path = ctypes.util.find_library('X11') or 'libX11.so.6'
    _libX11 = ctypes.CDLL(_lib_path)

    _libX11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    _libX11.XOpenDisplay.restype = ctypes.c_void_p

    _libX11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    _libX11.XCloseDisplay.restype = ctypes.c_int

    _libX11.XFlush.argtypes = [ctypes.c_void_p]
    _libX11.XFlush.restype = ctypes.c_int

    _libX11.XkbGetState.argtypes = [
        ctypes.c_void_p,   # Display*
        ctypes.c_uint,     # deviceSpec (XkbUseCoreKbd = 0x0100)
        ctypes.POINTER(ctypes.c_ubyte * 15),  # placeholder, replaced below
    ]
    _libX11.XkbGetState.restype = ctypes.c_int

    _libX11.XkbLockGroup.argtypes = [
        ctypes.c_void_p,   # Display*
        ctypes.c_uint,     # deviceSpec
        ctypes.c_uint,     # group
    ]
    _libX11.XkbLockGroup.restype = ctypes.c_int

except Exception as e:
    logger.debug("Failed to load libX11 ctypes bindings: %s", e)
    _libX11 = None


class XkbStateRec(ctypes.Structure):
    _fields_ = [
        ('group', ctypes.c_ubyte),
        ('locked_group', ctypes.c_ubyte),
        ('base_group', ctypes.c_ushort),
        ('latched_group', ctypes.c_ushort),
        ('mods', ctypes.c_ubyte),
        ('base_mods', ctypes.c_ubyte),
        ('latched_mods', ctypes.c_ubyte),
        ('locked_mods', ctypes.c_ubyte),
        ('compat_state', ctypes.c_ubyte),
        ('grab_mods', ctypes.c_ubyte),
        ('compat_grab_mods', ctypes.c_ubyte),
        ('lookup_mods', ctypes.c_ubyte),
        ('compat_lookup_mods', ctypes.c_ubyte),
        ('ptr_buttons', ctypes.c_ushort),
    ]


# Fix up XkbGetState argtypes now that XkbStateRec is defined
if _libX11 is not None:
    try:
        _libX11.XkbGetState.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.POINTER(XkbStateRec),
        ]
    except Exception:
        pass

# XkbUseCoreKbd
_XKB_USE_CORE_KBD = 0x0100


def _xkb_get_group(layouts_csv: str) -> Optional[str]:
    """Get current XKB group using ctypes XOpenDisplay + XkbGetState.

    Returns the layout name from layouts_csv corresponding to the active group,
    or None on failure. Never raises.
    """
    if _libX11 is None:
        return None
    try:
        dpy = _libX11.XOpenDisplay(None)
        if not dpy:
            return None
        try:
            state = XkbStateRec()
            ret = _libX11.XkbGetState(dpy, _XKB_USE_CORE_KBD, ctypes.byref(state))
            if ret == 0:
                group = state.group
                layout_list = [l.strip() for l in layouts_csv.split(',')]
                if group < len(layout_list):
                    return layout_list[group]
        finally:
            _libX11.XCloseDisplay(dpy)
    except Exception as e:
        logger.debug("_xkb_get_group failed: %s", e)
    return None


def _xkb_lock_group(group_idx: int) -> bool:
    """Switch XKB group using ctypes XOpenDisplay + XkbLockGroup.

    Returns True on success, False on failure. Never raises.
    """
    if _libX11 is None:
        return False
    try:
        dpy = _libX11.XOpenDisplay(None)
        if not dpy:
            return False
        try:
            ret = _libX11.XkbLockGroup(dpy, _XKB_USE_CORE_KBD, group_idx)
            _libX11.XFlush(dpy)
            return ret == 1  # Success returns True (non-zero)
        finally:
            _libX11.XCloseDisplay(dpy)
    except Exception as e:
        logger.debug("_xkb_lock_group failed: %s", e)
    return False


def get_current_layout() -> Optional[str]:
    """Get the currently active keyboard layout.

    Returns 'us', 'ru', or the raw layout string.
    Never raises — returns None on any failure.
    """
    try:
        layouts = None

        # Try xkb-switch first (fast, reliable)
        try:
            r = subprocess.run(
                ['xkb-switch', '-p'],
                capture_output=True, text=True, timeout=1.0,
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        except Exception as e:
            logger.debug("xkb-switch query failed: %s", e)

        # Try setxkbmap -query to get layout list
        try:
            result = subprocess.run(
                ['setxkbmap', '-query'],
                capture_output=True, text=True, timeout=1.0,
            )
            for line in result.stdout.splitlines():
                if line.strip().startswith('layout:'):
                    layouts = line.split(':', 1)[1].strip()
                    break
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        except Exception as e:
            logger.debug("setxkbmap query failed: %s", e)

        if not layouts:
            return None

        # Try XKB group detection via ctypes (proper XOpenDisplay, no python-xlib)
        xkb_result = _xkb_get_group(layouts)
        if xkb_result is not None:
            return xkb_result

        # Last resort: return first layout from setxkbmap
        return layouts.split(',')[0].strip()

    except Exception as e:
        logger.warning("get_current_layout failed (non-fatal): %s", e)
        return None


def switch_to_layout(layout: str):
    """Switch the keyboard layout to the specified layout.

    Best-effort. Never raises — logs warning on failure.
    """
    try:
        # Try xkb-switch (fast, works with most setups)
        try:
            result = subprocess.run(
                ['xkb-switch', '-s', layout],
                capture_output=True, timeout=1.0,
            )
            if result.returncode == 0:
                logger.info("Layout switched to %s via xkb-switch", layout)
                return
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        except Exception as e:
            logger.debug("xkb-switch set failed: %s", e)

        # Try XKB group switching via ctypes (proper XOpenDisplay)
        try:
            query = subprocess.run(
                ['setxkbmap', '-query'],
                capture_output=True, text=True, timeout=1.0,
            )
            layouts_line = ''
            for line in query.stdout.splitlines():
                if line.strip().startswith('layout:'):
                    layouts_line = line.split(':', 1)[1].strip()
                    break

            layout_list = [l.strip() for l in layouts_line.split(',')]
            if layout in layout_list:
                group_idx = layout_list.index(layout)

                if _xkb_lock_group(group_idx):
                    logger.info("Layout switched to %s (group %d) via XKB ctypes", layout, group_idx)
                    return

                # Fallback: xdotool
                try:
                    subprocess.run(
                        ['xdotool', 'key', f'XF86Switch_VT_{group_idx + 1}'],
                        capture_output=True, timeout=1.0,
                    )
                except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                    pass
                except Exception as e:
                    logger.debug("xdotool group switch failed: %s", e)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        except Exception as e:
            logger.debug("setxkbmap group query failed: %s", e)

        # Final fallback: setxkbmap direct
        try:
            subprocess.run(
                ['setxkbmap', layout],
                capture_output=True, timeout=1.0,
            )
            logger.info("Layout switched to %s via setxkbmap", layout)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            logger.warning("setxkbmap not available — cannot switch layout")
        except Exception as e:
            logger.warning("setxkbmap fallback failed: %s", e)

    except Exception as e:
        logger.warning("switch_to_layout(%s) failed (non-fatal): %s", layout, e)


def detect_target_layout(corrected_text: str) -> Optional[str]:
    """Detect which layout the corrected text belongs to.

    Returns 'us' for English, 'ru' for Russian, or None.
    Never raises.
    """
    try:
        if not corrected_text:
            return None

        words = corrected_text.split()
        last_word = words[-1] if words else corrected_text

        alpha = [c for c in last_word if c.isalpha()]
        if not alpha:
            return None

        ru_count = sum(1 for c in alpha if '\u0400' <= c <= '\u04ff')
        en_count = sum(1 for c in alpha if c.isascii())

        if ru_count > en_count:
            return LAYOUT_RU
        elif en_count > ru_count:
            return LAYOUT_EN

        return None
    except Exception as e:
        logger.warning("detect_target_layout failed (non-fatal): %s", e)
        return None


def switch_to_corrected_layout(corrected_text: str):
    """Switch keyboard layout to match the corrected text.

    This is the main entry point called after a correction is applied.
    Best-effort. Never raises — any failure is logged and ignored.
    The correction itself has already succeeded at this point.
    """
    try:
        target = detect_target_layout(corrected_text)
        if target is None:
            return

        current = get_current_layout()
        if current == target:
            logger.debug("Layout already %s, no switch needed", target)
            return

        logger.info("Switching layout: %s → %s (corrected text: %r)",
                    current, target, corrected_text[:30])
        switch_to_layout(target)
    except Exception as e:
        logger.warning("switch_to_corrected_layout failed (non-fatal): %s", e)
