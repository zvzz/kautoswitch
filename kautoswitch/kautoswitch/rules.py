"""Persistent rule store for learned suppression rules (3x undo)."""
import json
from pathlib import Path
from kautoswitch.config import RULES_FILE


class RuleStore:
    def __init__(self):
        self._rules: dict[str, int] = {}  # pattern → undo count
        self._suppressed: set[str] = set()  # patterns to never correct
        self.load()

    def load(self):
        if RULES_FILE.exists():
            try:
                with open(RULES_FILE, "r") as f:
                    data = json.load(f)
                self._rules = data.get("undo_counts", {})
                self._suppressed = set(data.get("suppressed", []))
            except (json.JSONDecodeError, IOError):
                pass

    def save(self):
        RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(RULES_FILE, "w") as f:
            json.dump({
                "undo_counts": self._rules,
                "suppressed": list(self._suppressed),
            }, f, indent=2, ensure_ascii=False)

    def record_undo(self, original: str) -> bool:
        """Record an undo for a pattern. Returns True if now suppressed (>=3)."""
        key = original.strip().lower()
        self._rules[key] = self._rules.get(key, 0) + 1
        if self._rules[key] >= 3:
            self._suppressed.add(key)
            self.save()
            return True
        self.save()
        return False

    def is_suppressed(self, text: str) -> bool:
        """Check if correction for this text is suppressed."""
        return text.strip().lower() in self._suppressed

    def clear(self):
        self._rules.clear()
        self._suppressed.clear()
        self.save()
