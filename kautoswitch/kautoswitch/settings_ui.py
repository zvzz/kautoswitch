"""Settings window (Qt) for KAutoSwitch."""
import logging
import threading
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QCheckBox, QRadioButton,
    QLineEdit, QSpinBox, QPushButton, QButtonGroup,
    QFormLayout, QStatusBar, QComboBox,
)
from PyQt5.QtCore import Qt, QMetaObject, Q_ARG, pyqtSlot

logger = logging.getLogger(__name__)


class SettingsWindow(QMainWindow):
    """Settings window with all configuration options."""

    def __init__(self, config, daemon, parent=None):
        super().__init__(parent)
        self.config = config
        self.daemon = daemon

        self.setWindowTitle("KAutoSwitch — Settings")
        self.setMinimumWidth(450)
        self.setMinimumHeight(560)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # === On/Off ===
        self._enabled_cb = QCheckBox("Enable auto-correction")
        self._enabled_cb.setChecked(config.enabled)
        self._enabled_cb.toggled.connect(self._on_enabled_changed)
        layout.addWidget(self._enabled_cb)

        # === Languages ===
        lang_group = QGroupBox("Languages")
        lang_layout = QVBoxLayout(lang_group)

        self._lang_ru = QCheckBox("Russian (ru)")
        self._lang_ru.setChecked(config.languages.get("ru", True))
        self._lang_ru.setEnabled(False)  # mandatory
        lang_layout.addWidget(self._lang_ru)

        self._lang_en = QCheckBox("English (en)")
        self._lang_en.setChecked(config.languages.get("en", True))
        self._lang_en.setEnabled(False)  # mandatory
        lang_layout.addWidget(self._lang_en)

        self._lang_be = QCheckBox("Belarusian (be) — optional")
        self._lang_be.setChecked(config.languages.get("be", False))
        self._lang_be.toggled.connect(self._on_lang_be_changed)
        lang_layout.addWidget(self._lang_be)

        layout.addWidget(lang_group)

        # === Model ===
        model_group = QGroupBox("Correction Model")
        model_layout = QVBoxLayout(model_group)

        self._model_btn_group = QButtonGroup(self)

        self._radio_tinyllm = QRadioButton("TinyLLM (local rule-based)")
        self._radio_tinyllm.setChecked(config.model == "tinyllm")
        self._model_btn_group.addButton(self._radio_tinyllm, 0)
        model_layout.addWidget(self._radio_tinyllm)

        self._radio_api = QRadioButton("Local API")
        self._radio_api.setChecked(config.model == "api")
        self._model_btn_group.addButton(self._radio_api, 1)
        model_layout.addWidget(self._radio_api)

        # API URL
        api_row = QHBoxLayout()
        api_row.addWidget(QLabel("API URL:"))
        self._api_url_input = QLineEdit(config.api_url)
        self._api_url_input.setPlaceholderText("http://localhost:8080/v1/correct")
        api_row.addWidget(self._api_url_input)
        model_layout.addLayout(api_row)

        # API Model selection
        api_model_row = QHBoxLayout()
        api_model_row.addWidget(QLabel("API Model:"))
        self._api_model_combo = QComboBox()
        self._api_model_combo.setEditable(True)
        self._api_model_combo.setMinimumWidth(200)
        current_model = config.api_model
        if current_model:
            self._api_model_combo.addItem(current_model)
            self._api_model_combo.setCurrentText(current_model)
        else:
            self._api_model_combo.addItem("(auto)")
            self._api_model_combo.setCurrentText("(auto)")
        api_model_row.addWidget(self._api_model_combo)

        self._fetch_models_btn = QPushButton("Fetch Models")
        self._fetch_models_btn.clicked.connect(self._fetch_api_models)
        api_model_row.addWidget(self._fetch_models_btn)

        self._api_model_status = QLabel("")
        api_model_row.addWidget(self._api_model_status)

        model_layout.addLayout(api_model_row)

        self._model_btn_group.buttonClicked.connect(self._on_model_changed)

        layout.addWidget(model_group)

        # === Hotkeys ===
        hotkey_group = QGroupBox("Hotkeys")
        hotkey_layout = QFormLayout(hotkey_group)

        self._hotkey_undo = QLineEdit(config.get("hotkey_undo", "ctrl+/"))
        hotkey_layout.addRow("Undo last correction:", self._hotkey_undo)

        self._hotkey_rethink = QLineEdit(config.get("hotkey_rethink", "ctrl+shift+/"))
        hotkey_layout.addRow("Rethink last input:", self._hotkey_rethink)

        self._hotkey_toggle = QLineEdit(config.get("hotkey_toggle", "ctrl+shift+p"))
        hotkey_layout.addRow("Toggle on/off:", self._hotkey_toggle)

        self._hotkey_polish = QLineEdit(config.get("hotkey_polish", "ctrl+shift+l"))
        hotkey_layout.addRow("Polish / cleanup text:", self._hotkey_polish)

        layout.addWidget(hotkey_group)

        # === Advanced ===
        adv_group = QGroupBox("Advanced")
        adv_layout = QFormLayout(adv_group)

        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(10, 5000)
        self._timeout_spin.setSuffix(" ms")
        self._timeout_spin.setValue(config.ai_timeout_ms)
        adv_layout.addRow("AI timeout:", self._timeout_spin)

        self._confidence_spin = QSpinBox()
        self._confidence_spin.setRange(0, 100)
        self._confidence_spin.setSuffix(" %")
        self._confidence_spin.setValue(int(config.confidence_threshold * 100))
        adv_layout.addRow("Min confidence:", self._confidence_spin)

        self._debug_cb = QCheckBox("Enable debug logging")
        self._debug_cb.setChecked(config.debug_logging)
        adv_layout.addRow(self._debug_cb)

        layout.addWidget(adv_group)

        # === Status ===
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)
        self._status_label = QLabel()
        status_layout.addWidget(self._status_label)

        rules_row = QHBoxLayout()
        self._rules_label = QLabel()
        rules_row.addWidget(self._rules_label)
        clear_rules_btn = QPushButton("Clear learned rules")
        clear_rules_btn.clicked.connect(self._clear_rules)
        rules_row.addWidget(clear_rules_btn)
        status_layout.addLayout(rules_row)

        layout.addWidget(status_group)

        # === Buttons ===
        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

        # Status bar
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)

        self.refresh()

    def refresh(self):
        """Refresh displayed status."""
        running = self.daemon.running
        enabled = self.config.enabled
        model = self.config.model
        api_model = self.config.api_model

        status_parts = []
        status_parts.append(f"Daemon: {'running' if running else 'stopped'}")
        status_parts.append(f"Correction: {'ON' if enabled else 'OFF'}")
        model_str = model
        if model == "api" and api_model:
            model_str = f"api ({api_model})"
        status_parts.append(f"Model: {model_str}")
        self._status_label.setText(" | ".join(status_parts))

        rule_count = len(self.daemon.rules._suppressed) if hasattr(self.daemon, 'rules') else 0
        undo_count = self.daemon.undo_stack.size if hasattr(self.daemon, 'undo_stack') else 0
        self._rules_label.setText(f"Learned rules: {rule_count} | Undo stack: {undo_count}")

    def _on_enabled_changed(self, checked):
        self.config.enabled = checked

    def _on_lang_be_changed(self, checked):
        langs = self.config.languages
        langs["be"] = checked
        self.config.set("languages", langs)

    def _on_model_changed(self):
        if self._radio_tinyllm.isChecked():
            self.config.model = "tinyllm"
        else:
            self.config.model = "api"

    def _fetch_api_models(self):
        """Fetch available models from the API endpoint in a background thread."""
        self._fetch_models_btn.setEnabled(False)
        self._api_model_status.setText("Fetching...")

        url = self._api_url_input.text()
        timeout_ms = self._timeout_spin.value()

        def _do_fetch():
            from kautoswitch.api_client import APIClient
            client = APIClient(url=url, timeout_ms=timeout_ms)
            models = client.fetch_models()
            # Schedule UI update on the main thread
            QMetaObject.invokeMethod(
                self, "_on_models_fetched",
                Qt.QueuedConnection,
                Q_ARG(list, models),
            )

        t = threading.Thread(target=_do_fetch, daemon=True)
        t.start()

    @pyqtSlot(list)
    def _on_models_fetched(self, models):
        """Handle fetched models list (called on main thread)."""
        self._fetch_models_btn.setEnabled(True)

        if not models:
            self._api_model_status.setText("No models found or connection failed")
            self._statusbar.showMessage("Failed to fetch API models. Check URL and server.", 5000)
            return

        current = self._api_model_combo.currentText()
        self._api_model_combo.clear()
        self._api_model_combo.addItem("(auto)")

        for m in models:
            model_id = m.get('id', '')
            if model_id:
                self._api_model_combo.addItem(model_id)

        # Restore previous selection if it exists
        idx = self._api_model_combo.findText(current)
        if idx >= 0:
            self._api_model_combo.setCurrentIndex(idx)

        count = len(models)
        self._api_model_status.setText(f"{count} model(s)")
        self._statusbar.showMessage(f"Fetched {count} API model(s).", 3000)

    def _save(self):
        self.config.set("api_url", self._api_url_input.text())

        # Save API model selection
        api_model = self._api_model_combo.currentText()
        if api_model == "(auto)":
            api_model = ""
        self.config.set("api_model", api_model)

        self.config.set("ai_timeout_ms", self._timeout_spin.value())
        self.config.set("correction_confidence_threshold", self._confidence_spin.value() / 100.0)
        self.config.set("debug_logging", self._debug_cb.isChecked())
        self.config.set("hotkey_undo", self._hotkey_undo.text())
        self.config.set("hotkey_rethink", self._hotkey_rethink.text())
        self.config.set("hotkey_toggle", self._hotkey_toggle.text())
        self.config.set("hotkey_polish", self._hotkey_polish.text())
        self.config.save()
        self._statusbar.showMessage("Settings saved.", 3000)
        self.refresh()

    def _clear_rules(self):
        if hasattr(self.daemon, 'rules'):
            self.daemon.rules.clear()
        self._statusbar.showMessage("Learned rules cleared.", 3000)
        self.refresh()
