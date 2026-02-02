"""TinyLLM — local rule-based correction engine.

This is the "embedded TinyLLM" that handles:
1. Keyboard layout correction (QWERTY↔ЙЦУКЕН)
2. Spelling/typo correction with context awareness
3. Mixed-layout word fixing
4. Phrase-level semantic correction (e.g. verb form agreement)

It follows the rules from tinyllm_prompt.md:
- Never invent words
- Never expand text
- Never rephrase meaning
- Prefer minimal correction
- Return original if confidence < 0.6
"""
import logging
from typing import Optional
from kautoswitch.spellcheck_compat import SpellChecker

from kautoswitch.layout_map import (
    map_en_to_ru, map_ru_to_en, detect_layout_mismatch,
    fix_mixed_layout, is_all_caps, EN_ALPHA, RU_ALPHA,
    EN_TO_RU, RU_TO_EN,
)

logger = logging.getLogger(__name__)


class TinyLLM:
    """Local rule-based correction engine (the embedded 'TinyLLM')."""

    def __init__(self):
        self._spell_en = SpellChecker(language='en')
        self._spell_ru = SpellChecker(language='ru')

    def correct(self, text: str, context: str = "") -> Optional[str]:
        """Correct text following TinyLLM prompt rules.

        Returns corrected text or None if no correction needed/possible.
        """
        if not text or not text.strip():
            return None

        # Never correct all-caps
        if is_all_caps(text):
            return None

        # Try full phrase correction (handles multi-word input)
        words = text.split()
        if len(words) > 1:
            result = self._correct_phrase(words)
            if result and result != text:
                return result

        # Single word correction
        if len(words) == 1:
            result = self._correct_word(words[0], context)
            if result and result != words[0]:
                return result

        return None

    def _correct_phrase(self, words: list) -> Optional[str]:
        """Correct a multi-word phrase."""
        text = ' '.join(words)

        # 1. Try layout swap of entire phrase
        layout_result = self._try_layout_swap_phrase(text)
        if layout_result:
            # Also try spelling correction of the layout-mapped result
            spell_fixed = self._spell_correct_text(layout_result)
            return spell_fixed if spell_fixed else layout_result

        # 2. Try correcting each word individually
        corrected_words = []
        any_changed = False
        for w in words:
            fixed = self._correct_word(w, ' '.join(words))
            if fixed and fixed != w:
                corrected_words.append(fixed)
                any_changed = True
            else:
                corrected_words.append(w)

        if any_changed:
            return ' '.join(corrected_words)

        return None

    def _try_layout_swap_phrase(self, text: str) -> Optional[str]:
        """Try swapping layout for entire phrase if it looks like wrong layout."""
        mismatch = detect_layout_mismatch(text)
        if mismatch == 'en_meant_ru':
            mapped = map_en_to_ru(text)
            score = self._validity_score(mapped)
            if score >= 0.5:
                return mapped
        elif mismatch == 'ru_meant_en':
            mapped = map_ru_to_en(text)
            score = self._validity_score(mapped)
            if score >= 0.5:
                return mapped
        return None

    def _correct_word(self, word: str, context: str = "") -> Optional[str]:
        """Correct a single word."""
        if not word:
            return None

        clean = word.strip('.,;:!?()[]{}"\'/\\-=+@#$%^&*~`<>|')
        if not clean:
            return None

        # Already valid?
        if self._is_valid(clean):
            return None

        # Try layout swap
        layout_fixed = self._try_layout_swap_word(clean)
        if layout_fixed:
            return self._apply_casing(word, layout_fixed)

        # Try mixed layout fix
        mixed_fixed = self._try_mixed_fix(clean)
        if mixed_fixed:
            return self._apply_casing(word, mixed_fixed)

        # Try spell correction
        spell_fixed = self._spell_correct_word(clean)
        if spell_fixed and spell_fixed != clean.lower():
            return self._apply_casing(word, spell_fixed)

        # Try layout swap + spell correction
        combo_fixed = self._try_layout_then_spell(clean)
        if combo_fixed:
            return self._apply_casing(word, combo_fixed)

        return None

    def _try_layout_swap_word(self, word: str) -> Optional[str]:
        """Try mapping word through layout and check validity."""
        mismatch = detect_layout_mismatch(word)
        if mismatch == 'en_meant_ru':
            mapped = map_en_to_ru(word)
            if self._is_valid(mapped):
                return mapped
        elif mismatch == 'ru_meant_en':
            mapped = map_ru_to_en(word)
            if self._is_valid(mapped):
                return mapped
        return None

    def _try_mixed_fix(self, word: str) -> Optional[str]:
        """Fix mixed-layout characters."""
        mismatch = detect_layout_mismatch(word)
        if mismatch != 'mixed':
            return None

        alpha = [c for c in word if c.isalpha()]
        ru = sum(1 for c in alpha if c in RU_ALPHA or ('\u0400' <= c <= '\u04ff'))
        en = sum(1 for c in alpha if c.lower() in EN_ALPHA)

        target = 'ru' if ru > en else 'en'
        fixed = fix_mixed_layout(word, target=target)
        if fixed != word and self._is_valid(fixed):
            return fixed

        # Try spell-correcting the fixed version
        if fixed != word:
            spell_fixed = self._spell_correct_word(fixed)
            if spell_fixed and self._is_valid(spell_fixed):
                return spell_fixed

        return None

    def _try_layout_then_spell(self, word: str) -> Optional[str]:
        """Try layout swap then spell-correct the result."""
        mismatch = detect_layout_mismatch(word)
        if mismatch == 'en_meant_ru':
            mapped = map_en_to_ru(word)
            spell_fixed = self._spell_correct_word(mapped)
            if spell_fixed and self._is_valid(spell_fixed):
                return spell_fixed
        elif mismatch == 'ru_meant_en':
            mapped = map_ru_to_en(word)
            spell_fixed = self._spell_correct_word(mapped)
            if spell_fixed and self._is_valid(spell_fixed):
                return spell_fixed
        return None

    def _spell_correct_text(self, text: str) -> Optional[str]:
        """Spell-correct each word in text."""
        words = text.split()
        result_words = []
        any_changed = False

        for w in words:
            clean = w.strip('.,;:!?()[]{}"\'/\\-=+@#$%^&*~`<>|')
            if not clean or self._is_valid(clean):
                result_words.append(w)
                continue

            fixed = self._spell_correct_word(clean)
            if fixed and fixed != clean.lower():
                result_words.append(self._apply_casing(w, fixed))
                any_changed = True
            else:
                result_words.append(w)

        return ' '.join(result_words) if any_changed else text

    def _spell_correct_word(self, word: str) -> Optional[str]:
        """Find best spelling correction."""
        lower = word.lower()

        # Try Russian
        if self._looks_russian(word):
            candidates = self._spell_ru.candidates(lower)
            if candidates:
                best = self._pick_best(lower, candidates)
                if best and self._damerau_distance(lower, best) <= 3:
                    return best

        # Try English
        if self._looks_english(word):
            candidates = self._spell_en.candidates(lower)
            if candidates:
                best = self._pick_best(lower, candidates)
                if best and self._damerau_distance(lower, best) <= 3:
                    return best

        return None

    def _is_valid(self, word: str) -> bool:
        """Check if word is valid in any language."""
        lower = word.lower()
        if self._looks_english(word) and lower in self._spell_en:
            return True
        if self._looks_russian(word) and lower in self._spell_ru:
            return True
        return False

    def _validity_score(self, text: str) -> float:
        """Score how many words in text are valid (0-1)."""
        words = text.split()
        if not words:
            return 0.0
        clean_words = [w.strip('.,;:!?()[]{}"\'/\\-=+@#$%^&*~`<>|') for w in words]
        valid = sum(1 for w in clean_words if w and self._is_valid(w))
        return valid / len(words)

    @staticmethod
    def _looks_english(word: str) -> bool:
        alpha = [c for c in word if c.isalpha()]
        return bool(alpha) and all(c.lower() in EN_ALPHA for c in alpha)

    @staticmethod
    def _looks_russian(word: str) -> bool:
        alpha = [c for c in word if c.isalpha()]
        return bool(alpha) and all(
            c in RU_ALPHA or c.lower() in RU_ALPHA or ('\u0400' <= c <= '\u04ff')
            for c in alpha
        )

    @staticmethod
    def _pick_best(original: str, candidates: set) -> Optional[str]:
        """Pick best candidate by edit distance then length similarity."""
        scored = []
        for c in candidates:
            dist = TinyLLM._damerau_distance(original, c)
            len_diff = abs(len(original) - len(c))
            scored.append((dist, len_diff, c))
        scored.sort()
        return scored[0][2] if scored else None

    @staticmethod
    def _apply_casing(original: str, corrected: str) -> str:
        if original.isupper():
            return corrected.upper()
        if original and original[0].isupper():
            return corrected.capitalize()
        return corrected

    @staticmethod
    def _damerau_distance(a: str, b: str) -> int:
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
                    d[i - 1][j] + 1,
                    d[i][j - 1] + 1,
                    d[i - 1][j - 1] + cost,
                )
                if (i > 1 and j > 1 and
                        a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]):
                    d[i][j] = min(d[i][j], d[i - 2][j - 2] + cost)
        return d[la][lb]
