"""A message written FOR someone else goes in the session's language too (demo pass 105, 2026-10-04).

C5 «send rowan a telegram with the new time» in an English session: the model wrote «Oye Rowan, al final lo
movemos media hora más tarde…». The language lock spoke of the REPLY only; every tool description it reads is
Spanish, and the text it puts in a payload copied that. The lock now names those texts.
"""
from __future__ import annotations


def _lock(monkeypatch, code):
    from voice.engine.core import langs
    from nucleo.flash import prompt
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec(code))
    return prompt._lang_lock()


def test_the_english_lock_covers_what_he_sends(monkeypatch):
    lock = _lock(monkeypatch, "en")
    assert "mensajes" in lock and "English" in lock.split("mensajes", 1)[1][:200], lock


def test_the_spanish_lock_says_it_too(monkeypatch):
    assert "mensajes" in _lock(monkeypatch, "es")
