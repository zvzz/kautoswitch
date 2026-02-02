"""Correction pipeline — layout detection, spell check, AI integration."""
import logging
from typing import Optional, Tuple, List
from kautoswitch.spellcheck_compat import SpellChecker

from kautoswitch.layout_map import (
    map_en_to_ru, map_ru_to_en, detect_layout_mismatch,
    fix_mixed_layout, is_all_caps, EN_ALPHA, RU_ALPHA,
)

logger = logging.getLogger(__name__)


class Corrector:
    """Main correction pipeline.

    Priority:
    1. Skip if all caps (CapsLock)
    2. Skip if text is valid in current layout
    3. Try layout swap → check if result is valid (+ spell-correct mapped result)
    4. Try mixed-layout fix
    5. Try spelling correction (Damerau-Levenshtein)
    6. Optionally invoke TinyLLM/API for semantic correction
    """

    def __init__(self, config, tinyllm=None, api_client=None):
        self.config = config
        self.tinyllm = tinyllm
        self.api_client = api_client
        self._spell_en = SpellChecker(language='en')
        self._spell_ru = SpellChecker(language='ru')
        self._recent_words: List[str] = []  # recent uncorrected words for phrase context
        self._max_phrase_words = 10

    def add_context_word(self, word: str):
        """Add a word to recent context for phrase-level analysis."""
        self._recent_words.append(word)
        if len(self._recent_words) > self._max_phrase_words:
            self._recent_words.pop(0)

    def clear_context(self):
        self._recent_words.clear()

    def correct_phrase(self, words: List[str]) -> Optional[Tuple[str, float]]:
        """Try correcting an entire phrase (multiple words at once).

        This handles cases where individual words are ambiguous but the
        phrase clearly belongs to another layout.
        """
        if not words:
            return None

        phrase = ' '.join(words)

        if is_all_caps(phrase):
            return None

        if self._is_valid_text(phrase):
            return None

        # Try layout swap of entire phrase
        result = self._try_layout_swap_with_spell(phrase)
        if result:
            corrected_phrase, conf = result
            # Also spell-correct the mapped phrase if not already done
            spell_fixed = self._spell_correct_phrase(corrected_phrase)
            if spell_fixed and spell_fixed != corrected_phrase:
                return (spell_fixed, conf * 0.95)
            return result

        return None

    def correct(self, text: str, context: str = "") -> Optional[Tuple[str, float]]:
        """Attempt to correct a single word/text.

        Returns (corrected_text, confidence) or None if no correction needed.
        """
        if not text or not text.strip():
            return None

        # Rule: never correct all-caps (CapsLock)
        if is_all_caps(text):
            return None

        # Check if text is already valid
        if self._is_valid_text(text):
            return None

        # Try layout swap + spell correction of mapped result
        result = self._try_layout_swap_with_spell(text)
        if result:
            return result

        # Try mixed layout fix
        result = self._try_mixed_layout(text)
        if result:
            return result

        # Try spelling correction
        result = self._try_spelling(text)
        if result:
            return result

        # Try AI (TinyLLM or API) — this is the semantic fallback
        result = self._try_ai(text, context)
        if result:
            return result

        return None

    def _is_valid_text(self, text: str) -> bool:
        """Check if text is valid in any enabled language."""
        words = text.split()
        if not words:
            return True

        valid_count = 0
        for word in words:
            clean = self._clean_word(word)
            if not clean:
                valid_count += 1
                continue
            if self._is_valid_word(clean):
                valid_count += 1

        return valid_count == len(words)

    def _is_valid_word(self, word: str) -> bool:
        """Check if a word is valid in any enabled language."""
        if not word:
            return True

        langs = self.config.languages

        if langs.get("en") and self._is_english(word):
            if word.lower() in self._spell_en:
                return True

        if langs.get("ru") and self._is_russian(word):
            if word.lower() in self._spell_ru:
                return True

        return False

    def _is_english(self, word: str) -> bool:
        alpha = [c for c in word if c.isalpha()]
        return all(c.lower() in EN_ALPHA or c.upper() in EN_ALPHA for c in alpha) if alpha else False

    def _is_russian(self, word: str) -> bool:
        alpha = [c for c in word if c.isalpha()]
        if not alpha:
            return False
        for c in alpha:
            cl = c.lower()
            if cl not in RU_ALPHA and c not in RU_ALPHA:
                # Check by Unicode range
                if not ('\u0400' <= c <= '\u04ff' or '\u0400' <= cl <= '\u04ff'):
                    return False
        return True

    def _try_layout_swap_with_spell(self, text: str) -> Optional[Tuple[str, float]]:
        """Try swapping layout AND spell-correcting the mapped result."""
        mismatch = detect_layout_mismatch(text)
        if not mismatch:
            return None

        if mismatch == 'en_meant_ru':
            mapped = map_en_to_ru(text)
            # Check if mapped is valid
            if self._is_valid_text(mapped):
                return (mapped, 0.95)

            # Try spell-correcting the mapped result
            spell_result = self._spell_correct_phrase(mapped)
            if spell_result and self._is_valid_text(spell_result):
                return (spell_result, 0.9)

            # Even if not fully valid, if most words are valid, accept the map
            validity = self._text_validity_score(mapped)
            if validity > 0.5:
                return (mapped, validity)

        elif mismatch == 'ru_meant_en':
            mapped = map_ru_to_en(text)
            if self._is_valid_text(mapped):
                return (mapped, 0.95)

        return None

    def _try_mixed_layout(self, text: str) -> Optional[Tuple[str, float]]:
        """Try fixing mixed-layout characters."""
        mismatch = detect_layout_mismatch(text)
        if mismatch != 'mixed':
            return None

        alpha = [c for c in text if c.isalpha()]
        ru_count = sum(1 for c in alpha if c in RU_ALPHA or ('\u0400' <= c <= '\u04ff'))
        en_count = sum(1 for c in alpha if c.lower() in EN_ALPHA)

        if ru_count > en_count:
            fixed = fix_mixed_layout(text, target='ru')
        else:
            fixed = fix_mixed_layout(text, target='en')

        if fixed != text:
            if self._is_valid_text(fixed):
                return (fixed, 0.9)
            # Try spell-correcting the fixed result
            spell_fixed = self._spell_correct_phrase(fixed)
            if spell_fixed and self._is_valid_text(spell_fixed):
                return (spell_fixed, 0.85)

        return None

    def _try_spelling(self, text: str) -> Optional[Tuple[str, float]]:
        """Try spelling correction for each word."""
        result = self._spell_correct_phrase(text)
        if result and result != text:
            return (result, 0.8)
        return None

    def _spell_correct_phrase(self, text: str) -> Optional[str]:
        """Spell-correct each word in a phrase."""
        words = text.split()
        corrected_words = []
        any_corrected = False

        for word in words:
            clean = self._clean_word(word)
            if not clean or self._is_valid_word(clean):
                corrected_words.append(word)
                continue

            correction = self._spell_correct_word(clean)
            if correction and correction != clean.lower():
                corrected_words.append(self._apply_casing(word, correction))
                any_corrected = True
            else:
                corrected_words.append(word)

        if any_corrected:
            return ' '.join(corrected_words)
        return None

    def _spell_correct_word(self, word: str) -> Optional[str]:
        """Find spelling correction for a word using Damerau-Levenshtein."""
        lower = word.lower()

        # Try Russian
        if self._is_russian(word) or any(
            c in RU_ALPHA or ('\u0400' <= c <= '\u04ff') for c in word
        ):
            candidates = self._spell_ru.candidates(lower)
            if candidates:
                best = self._pick_best_candidate(lower, candidates)
                if best and self._damerau_levenshtein(lower, best) <= 3:
                    return best

        # Try English
        if self._is_english(word):
            candidates = self._spell_en.candidates(lower)
            if candidates:
                best = self._pick_best_candidate(lower, candidates)
                if best and self._damerau_levenshtein(lower, best) <= 3:
                    return best

        return None

    def _pick_best_candidate(self, original: str, candidates: set) -> Optional[str]:
        """Pick the best spelling candidate preferring minimal edit + similar length."""
        if not candidates:
            return None

        scored = []
        for c in candidates:
            dist = self._damerau_levenshtein(original, c)
            len_diff = abs(len(original) - len(c))
            # Score: primary=edit distance, secondary=length difference
            scored.append((dist, len_diff, c))

        scored.sort()
        return scored[0][2] if scored else None

    def _try_ai(self, text: str, context: str) -> Optional[Tuple[str, float]]:
        """Try AI correction (TinyLLM or API)."""
        if self.config.model == "api" and self.api_client:
            result = self.api_client.correct(text, context)
            if result and result != text:
                return (result, 0.7)

        if self.tinyllm:
            result = self.tinyllm.correct(text, context)
            if result and result != text:
                return (result, 0.75)

        return None

    def _text_validity_score(self, text: str) -> float:
        """Score how valid the text is (0-1)."""
        words = text.split()
        if not words:
            return 0.0
        valid = sum(1 for w in words if self._is_valid_word(self._clean_word(w)))
        return valid / len(words)

    @staticmethod
    def _clean_word(word: str) -> str:
        """Remove punctuation from word edges."""
        return word.strip('.,;:!?()[]{}"\'/\\-=+@#$%^&*~`<>|')

    @staticmethod
    def _apply_casing(original: str, corrected: str) -> str:
        """Apply the casing pattern of original to corrected."""
        if original.isupper():
            return corrected.upper()
        if original and original[0].isupper():
            return corrected.capitalize()
        return corrected

    @staticmethod
    def _damerau_levenshtein(a: str, b: str) -> int:
        """Damerau-Levenshtein distance (with transpositions)."""
        la, lb = len(a), len(b)
        d = [[0] * (lb + 1) for _ in range(la + 1)]

        for i in range(la + 1):
            d[i][0] = i
        for j in range(lb + 1):
            d[0][j] = j

        for i in range(1, la + 1):
            for j in range(1, lb + 1):
                cost = 0 if a[i - 1] == b[j - 1] else 1
                d[i][j] = min(
                    d[i - 1][j] + 1,       # deletion
                    d[i][j - 1] + 1,       # insertion
                    d[i - 1][j - 1] + cost  # substitution
                )
                # Transposition
                if (i > 1 and j > 1 and
                        a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]):
                    d[i][j] = min(d[i][j], d[i - 2][j - 2] + cost)

        return d[la][lb]
