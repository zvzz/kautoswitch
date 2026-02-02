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

    exit_code = app.exec_()
    daemon.stop()
    sys.exit(exit_code)


def run_daemon():
    """Run daemon only (headless, for systemd user service)."""
    import time
    from kautoswitch.config import Config
    from kautoswitch.tinyllm import TinyLLM
    from kautoswitch.api_client import APIClient
    from kautoswitch.daemon import Daemon

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
            time.sleep(1)
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
