"""Compatibility shim: import SpellChecker from system package or vendored copy."""
try:
    from spellchecker import SpellChecker  # system or venv
except ImportError:
    import sys
    import os
    # Add vendored path
    _vendor_dir = os.path.join(os.path.dirname(__file__), "vendor")
    if _vendor_dir not in sys.path:
        sys.path.insert(0, _vendor_dir)
    from spellchecker import SpellChecker  # vendored copy

__all__ = ["SpellChecker"]
