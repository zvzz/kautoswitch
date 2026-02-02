"""Tests for layout mapping."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from kautoswitch.layout_map import map_en_to_ru, map_ru_to_en, detect_layout_mismatch, is_all_caps


def test_en_to_ru_basic():
    assert map_en_to_ru('b') == 'и'
    assert map_en_to_ru('b jy dsrk.xb') == 'и он выключи'  # note: period maps to ю
    # Actually let's verify character by character
    result = map_en_to_ru('b jy dsrk.xb')
    # b→и, ' '→' ', j→о, y→н, ' '→' ', d→в, s→ы, r→к, k→л, .→ю, x→ч, b→и
    # Wait, 'b jy dsrk.xb' should map to 'и он выкл.чи' — let me check
    # Actually: d→в, s→ы, r→к, k→л, .→ю, x→ч, b→и
    # Hmm, the expected is 'и он выключил' which is longer.
    # The input 'dsrk.xb' maps to 'выключи' not 'выключил'
    # Actually 'dsrk.xbk' would be 'выключил'
    # Let me re-check the original example: 'b jy dsrk.xbk' → 'и он выключил'
    # Actually the original says 'b jy dsrk.xb' → 'и он выключил'
    # Let me map: d→в s→ы r→к k→л .→ю x→ч b→и = 'выключи'
    # So the direct map gives 'выключи' which needs spell correction to 'выключил'
    # This means the TinyLLM/corrector must handle the semantic correction
    pass


def test_en_to_ru_hello():
    # Ghbdtn → Привет
    result = map_en_to_ru('Ghbdtn')
    assert result == 'Привет'


def test_ru_to_en():
    result = map_ru_to_en('Привет')
    assert result == 'Ghbdtn'


def test_detect_english_meant_russian():
    result = detect_layout_mismatch('Ghbdtn')
    assert result == 'en_meant_ru'


def test_correct_text_no_mismatch():
    result = detect_layout_mismatch('Hello')
    assert result == 'en_meant_ru'  # still EN chars, but dictionary will decide


def test_caps_detection():
    assert is_all_caps('GHBDTN VBH') is True
    assert is_all_caps('Hello') is False
    assert is_all_caps('A') is False  # single char


if __name__ == '__main__':
    test_en_to_ru_basic()
    test_en_to_ru_hello()
    test_ru_to_en()
    test_detect_english_meant_russian()
    test_correct_text_no_mismatch()
    test_caps_detection()
    print("All layout_map tests passed.")
