"""Configuration management — JSON-based, stored in ~/.config/kautoswitch/."""
import json
import os
from pathlib import Path

DEFAULT_CONFIG = {
    "enabled": True,
    "languages": {"ru": True, "en": True, "be": False},
    "model": "tinyllm",  # "tinyllm" or "api"
    "api_url": "http://localhost:8080/v1/correct",
    "api_model": "",  # selected API model ID (fetched from /v1/models)
    "ai_timeout_ms": 100,
    "hotkey_undo": "ctrl+/",
    "hotkey_rethink": "ctrl+shift+/",
    "hotkey_toggle": "ctrl+shift+p",
    "hotkey_polish": "ctrl+shift+l",
    "debug_logging": False,
    "correction_confidence_threshold": 0.6,
    "phrase_idle_delay_ms": 350,
}

CONFIG_DIR = Path.home() / ".config" / "kautoswitch"
CONFIG_FILE = CONFIG_DIR / "config.json"
RULES_FILE = CONFIG_DIR / "learned_rules.json"


class Config:
    def __init__(self):
        self._data = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    stored = json.load(f)
                self._data.update(stored)
            except (json.JSONDecodeError, IOError):
                pass

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self.save()

    @property
    def enabled(self):
        return self._data["enabled"]

    @enabled.setter
    def enabled(self, val):
        self._data["enabled"] = bool(val)
        self.save()

    @property
    def languages(self):
        return self._data["languages"]

    @property
    def model(self):
        return self._data["model"]

    @model.setter
    def model(self, val):
        self._data["model"] = val
        self.save()

    @property
    def api_url(self):
        return self._data["api_url"]

    @property
    def api_model(self):
        return self._data.get("api_model", "")

    @api_model.setter
    def api_model(self, val):
        self._data["api_model"] = val
        self.save()

    @property
    def ai_timeout_ms(self):
        return self._data["ai_timeout_ms"]

    @property
    def debug_logging(self):
        return self._data["debug_logging"]

    @property
    def confidence_threshold(self):
        return self._data["correction_confidence_threshold"]

    @property
    def phrase_idle_delay_ms(self):
        return self._data.get("phrase_idle_delay_ms", 350)
