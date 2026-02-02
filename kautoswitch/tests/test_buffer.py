"""Tests for text buffer."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from kautoswitch.buffer import TextBuffer


def test_word_completion():
    buf = TextBuffer()
    assert buf.add_char('h') is None
    assert buf.add_char('e') is None
    assert buf.add_char('l') is None
    assert buf.add_char('l') is None
    assert buf.add_char('o') is None
    result = buf.add_char(' ')
    assert result == 'hello'


def test_backspace():
    buf = TextBuffer()
    buf.add_char('h')
    buf.add_char('e')
    buf.handle_backspace()
    assert buf.get_current_word() == 'h'


def test_empty_word():
    buf = TextBuffer()
    result = buf.add_char(' ')
    assert result is None


def test_force_complete():
    buf = TextBuffer()
    buf.add_char('t')
    buf.add_char('e')
    buf.add_char('s')
    buf.add_char('t')
    word = buf.force_complete()
    assert word == 'test'
    assert buf.get_current_word() == ''


if __name__ == '__main__':
    test_word_completion()
    test_backspace()
    test_empty_word()
    test_force_complete()
    print("All buffer tests passed.")
