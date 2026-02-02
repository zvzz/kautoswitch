"""System tray icon with context menu for KAutoSwitch."""
import logging
from PyQt5.QtWidgets import (
    QSystemTrayIcon, QMenu, QAction, QActionGroup, QApplication,
)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt

logger = logging.getLogger(__name__)


def _create_icon(enabled: bool) -> QIcon:
    """Create a simple colored icon indicating enabled/disabled state."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Circle background
    color = QColor(0x4C, 0xAF, 0x50) if enabled else QColor(0x9E, 0x9E, 0x9E)
    painter.setBrush(color)
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(4, 4, size - 8, size - 8)

    # "П" letter (for KAutoSwitch)
    painter.setPen(QColor(255, 255, 255))
    font = QFont("Sans", 28, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "П")

    painter.end()
    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    """System tray icon with enable/disable, model selection, language toggle."""

    def __init__(self, config, daemon, parent=None):
        super().__init__(parent)
        self.config = config
        self.daemon = daemon
        self._settings_window = None

        self.setIcon(_create_icon(config.enabled))
        self.setToolTip("KAutoSwitch" + (" [ON]" if config.enabled else " [OFF]"))
        self._build_menu()

        self.activated.connect(self._on_activated)

    def _build_menu(self):
        menu = QMenu()

        # Enable / Disable toggle
        self._toggle_action = QAction("Disable" if self.config.enabled else "Enable", menu)
        self._toggle_action.triggered.connect(self._toggle_enabled)
        menu.addAction(self._toggle_action)

        menu.addSeparator()

        # Model selection
        model_menu = menu.addMenu("Model")
        model_group = QActionGroup(model_menu)
        model_group.setExclusive(True)

        self._model_tinyllm = QAction("TinyLLM (local)", model_group)
        self._model_tinyllm.setCheckable(True)
        self._model_tinyllm.setChecked(self.config.model == "tinyllm")
        self._model_tinyllm.triggered.connect(lambda: self._set_model("tinyllm"))
        model_menu.addAction(self._model_tinyllm)

        self._model_api = QAction("API (local)", model_group)
        self._model_api.setCheckable(True)
        self._model_api.setChecked(self.config.model == "api")
        self._model_api.triggered.connect(lambda: self._set_model("api"))
        model_menu.addAction(self._model_api)

        menu.addSeparator()

        # Language toggles
        lang_menu = menu.addMenu("Languages")

        self._lang_ru = QAction("Russian (ru)", lang_menu)
        self._lang_ru.setCheckable(True)
        self._lang_ru.setChecked(self.config.languages.get("ru", True))
        self._lang_ru.setEnabled(False)  # mandatory
        lang_menu.addAction(self._lang_ru)

        self._lang_en = QAction("English (en)", lang_menu)
        self._lang_en.setCheckable(True)
        self._lang_en.setChecked(self.config.languages.get("en", True))
        self._lang_en.setEnabled(False)  # mandatory
        lang_menu.addAction(self._lang_en)

        self._lang_be = QAction("Belarusian (be)", lang_menu)
        self._lang_be.setCheckable(True)
        self._lang_be.setChecked(self.config.languages.get("be", False))
        self._lang_be.triggered.connect(self._toggle_belarusian)
        lang_menu.addAction(self._lang_be)

        menu.addSeparator()

        # Settings
        settings_action = QAction("Settings...", menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        # Quit
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    def _toggle_enabled(self):
        self.config.enabled = not self.config.enabled
        enabled = self.config.enabled
        self._toggle_action.setText("Disable" if enabled else "Enable")
        self.setIcon(_create_icon(enabled))
        self.setToolTip("KAutoSwitch" + (" [ON]" if enabled else " [OFF]"))
        logger.info("Toggled: %s", "enabled" if enabled else "disabled")

    def _set_model(self, model: str):
        self.config.model = model
        self._model_tinyllm.setChecked(model == "tinyllm")
        self._model_api.setChecked(model == "api")
        logger.info("Model set to: %s", model)

    def _toggle_belarusian(self):
        langs = self.config.languages
        langs["be"] = not langs.get("be", False)
        self.config.set("languages", langs)
        self._lang_be.setChecked(langs["be"])

    def _open_settings(self):
        from kautoswitch.settings_ui import SettingsWindow
        if self._settings_window is None:
            self._settings_window = SettingsWindow(self.config, self.daemon)
        self._settings_window.refresh()
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _quit(self):
        self.daemon.stop()
        QApplication.quit()

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:  # left click
            self._toggle_enabled()
