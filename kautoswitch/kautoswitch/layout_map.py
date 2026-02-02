"""Bidirectional QWERTY ↔ ЙЦУКЕН keyboard layout mapping."""

# Maps EN key position → RU character (standard QWERTY → ЙЦУКЕН)
EN_TO_RU = {
    'q': 'й', 'w': 'ц', 'e': 'у', 'r': 'к', 't': 'е', 'y': 'н',
    'u': 'г', 'i': 'ш', 'o': 'щ', 'p': 'з', '[': 'х', ']': 'ъ',
    'a': 'ф', 's': 'ы', 'd': 'в', 'f': 'а', 'g': 'п', 'h': 'р',
    'j': 'о', 'k': 'л', 'l': 'д', ';': 'ж', "'": 'э',
    'z': 'я', 'x': 'ч', 'c': 'с', 'v': 'м', 'b': 'и', 'n': 'т',
    'm': 'ь', ',': 'б', '.': 'ю', '/': '.',
    'Q': 'Й', 'W': 'Ц', 'E': 'У', 'R': 'К', 'T': 'Е', 'Y': 'Н',
    'U': 'Г', 'I': 'Ш', 'O': 'Щ', 'P': 'З', '{': 'Х', '}': 'Ъ',
    'A': 'Ф', 'S': 'Ы', 'D': 'В', 'F': 'А', 'G': 'П', 'H': 'Р',
    'J': 'О', 'K': 'Л', 'L': 'Д', ':': 'Ж', '"': 'Э',
    'Z': 'Я', 'X': 'Ч', 'C': 'С', 'V': 'М', 'B': 'И', 'N': 'Т',
    'M': 'Ь', '<': 'Б', '>': 'Ю', '?': ',',
    '`': 'ё', '~': 'Ё',
}

# Reverse map: RU → EN
RU_TO_EN = {v: k for k, v in EN_TO_RU.items()}

# Sets for fast membership testing
RU_CHARS = set(EN_TO_RU.values())
EN_CHARS = set(EN_TO_RU.keys())
RU_ALPHA = {c for c in RU_CHARS if c.isalpha()}
EN_ALPHA = {c for c in EN_CHARS if c.isalpha()}


def map_en_to_ru(text: str) -> str:
    """Map text typed on EN layout as if RU layout was active."""
    return ''.join(EN_TO_RU.get(c, c) for c in text)


def map_ru_to_en(text: str) -> str:
    """Map text typed on RU layout as if EN layout was active."""
    return ''.join(RU_TO_EN.get(c, c) for c in text)


def detect_layout_mismatch(text: str) -> str | None:
    """Detect if text was likely typed in the wrong layout.

    Returns 'en_meant_ru' if EN chars that map well to RU,
    'ru_meant_en' if RU chars that map well to EN,
    or None if no mismatch detected.
    """
    if not text.strip():
        return None

    alpha_chars = [c for c in text if c.isalpha()]
    if not alpha_chars:
        return None

    en_count = sum(1 for c in alpha_chars if c in EN_ALPHA)
    ru_count = sum(1 for c in alpha_chars if c in RU_ALPHA)
    total = len(alpha_chars)

    if total == 0:
        return None

    # Mixed layout detection: if BOTH scripts present in a single word/text
    if en_count > 0 and ru_count > 0:
        return 'mixed'

    if en_count / total > 0.7:
        return 'en_meant_ru'
    if ru_count / total > 0.7:
        return 'ru_meant_en'

    return None


def fix_mixed_layout(text: str, target: str = 'ru') -> str:
    """Fix mixed-layout text by converting stray characters to target layout."""
    result = []
    for c in text:
        if target == 'ru':
            if c in EN_TO_RU:
                result.append(EN_TO_RU[c])
            else:
                result.append(c)
        else:
            if c in RU_TO_EN:
                result.append(RU_TO_EN[c])
            else:
                result.append(c)
    return ''.join(result)


def is_all_caps(text: str) -> bool:
    """Check if text is all uppercase (CapsLock detection)."""
    alpha = [c for c in text if c.isalpha()]
    return len(alpha) > 1 and all(c.isupper() for c in alpha)


# Layout identifiers (matching layout_switch.py constants)
LAYOUT_EN = 'us'
LAYOUT_RU = 'ru'


def detect_target_layout(corrected_text: str) -> str | None:
    """Detect which keyboard layout the corrected text belongs to.

    Returns 'us' for English, 'ru' for Russian, or None.
    Pure string analysis — no X11 calls, safe to call from any thread.
    """
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
