"""Entry point for KAutoSwitch.

Usage:
    python -m kautoswitch.main             # full mode (daemon + tray)
    python -m kautoswitch.main --daemon    # daemon only (no GUI)
    python -m kautoswitch.main --tray      # tray GUI only (connects to running daemon)
"""
import sys
import signal
import logging
import argparse


def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _start_layout_switch_timer(daemon):
    """Start a QTimer that polls daemon for layout switch requests.

    Runs in the Qt main thread — the ONLY safe place for X11/layout calls.
    Xlib is NOT thread-safe: calling it from daemon/XRecord/Timer threads
    causes segfaults that cannot be caught by try/except.
    """
    from PyQt5.QtCore import QTimer
    from kautoswitch.layout_switch import switch_to_layout, get_current_layout

    _log = logging.getLogger(__name__ + '.layout_timer')

    def _poll_layout_request():
        layout = daemon.consume_layout_request()
        if layout is None:
            return
        try:
            current = get_current_layout()
            if current == layout:
                _log.debug("Layout already %s, no switch needed", layout)
                return
            _log.info("Switching layout: %s → %s (from Qt main thread)", current, layout)
            switch_to_layout(layout)
        except Exception as e:
            _log.warning("Layout switch failed (non-fatal): %s", e)

    timer = QTimer()
    timer.setInterval(50)  # poll every 50ms — low overhead, fast response
    timer.timeout.connect(_poll_layout_request)
    timer.start()
    return timer  # caller must keep reference to prevent GC


def run_full():
    """Run daemon + tray in a single process (default mode)."""
    from PyQt5.QtWidgets import QApplication
    from kautoswitch.config import Config
    from kautoswitch.tinyllm import TinyLLM
    from kautoswitch.api_client import APIClient
    from kautoswitch.tray import TrayIcon
    from kautoswitch.daemon import Daemon

    app = QApplication(sys.argv)
    app.setApplicationName("KAutoSwitch")
    app.setQuitOnLastWindowClosed(False)

    config = Config()
    setup_logging(config.debug_logging)

    daemon = Daemon(config)
    tinyllm = TinyLLM()
    daemon.set_tinyllm(tinyllm)
    api_client = APIClient(url=config.api_url, timeout_ms=config.ai_timeout_ms)
    daemon.set_api_client(api_client)

    tray = TrayIcon(config, daemon)
    tray.show()
    daemon.start()

    # Layout switching runs ONLY in Qt main thread via this timer
    layout_timer = _start_layout_switch_timer(daemon)

    exit_code = app.exec_()
    layout_timer.stop()
    daemon.stop()
    sys.exit(exit_code)


def run_daemon():
    """Run daemon only (headless, for systemd user service).

    In headless mode, layout switching is done from the main thread's
    poll loop (same thread that calls time.sleep). This is safe because
    the main thread is not the XRecord listener thread.
    """
    import time
    from kautoswitch.config import Config
    from kautoswitch.tinyllm import TinyLLM
    from kautoswitch.api_client import APIClient
    from kautoswitch.daemon import Daemon
    from kautoswitch.layout_switch import switch_to_layout, get_current_layout

    config = Config()
    setup_logging(config.debug_logging)

    logger = logging.getLogger(__name__)
    logger.info("Starting KAutoSwitch daemon (headless mode)")

    daemon = Daemon(config)
    tinyllm = TinyLLM()
    daemon.set_tinyllm(tinyllm)
    api_client = APIClient(url=config.api_url, timeout_ms=config.ai_timeout_ms)
    daemon.set_api_client(api_client)
    daemon.start()

    try:
        while daemon.running:
            # Poll for layout switch requests from main thread (X11-safe)
            layout = daemon.consume_layout_request()
            if layout is not None:
                try:
                    current = get_current_layout()
                    if current != layout:
                        logger.info("Switching layout: %s → %s (from main thread)", current, layout)
                        switch_to_layout(layout)
                except Exception as e:
                    logger.warning("Layout switch failed (non-fatal): %s", e)
            time.sleep(0.05)  # 50ms poll interval
    except KeyboardInterrupt:
        pass
    finally:
        daemon.stop()
        logger.info("Daemon stopped")


def run_tray():
    """Run tray GUI only (connects to daemon via shared config)."""
    from PyQt5.QtWidgets import QApplication
    from kautoswitch.config import Config
    from kautoswitch.tray import TrayIcon
    from kautoswitch.daemon import Daemon

    app = QApplication(sys.argv)
    app.setApplicationName("KAutoSwitch")
    app.setQuitOnLastWindowClosed(False)

    config = Config()
    setup_logging(config.debug_logging)

    # Lightweight daemon reference (no input hook, just config bridge)
    daemon = Daemon(config)

    tray = TrayIcon(config, daemon)
    tray.show()

    exit_code = app.exec_()
    sys.exit(exit_code)


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    parser = argparse.ArgumentParser(description="KAutoSwitch")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--daemon", action="store_true",
                       help="Run daemon only (headless, for systemd)")
    group.add_argument("--tray", action="store_true",
                       help="Run tray GUI only")
    args = parser.parse_args()

    if args.daemon:
        run_daemon()
    elif args.tray:
        run_tray()
    else:
        run_full()


if __name__ == "__main__":
    main()
