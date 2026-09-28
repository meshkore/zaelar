"""System notes ride along a turn in the system's internal language; they must not pull the reply into it (demo pass
2026-09-28, full26 C2: «Traída de Email hecha…» came with an English turn and the reply was entirely in Spanish, in
the middle of an English demo). The composed turn names the configured language right after the header."""
from voice import brain_notes


def test_the_composed_turn_names_the_configured_language(monkeypatch):
    from voice.engine.core import langs

    class _Spec:
        native, name = "English", "English"
    monkeypatch.setattr(langs, "current_language", lambda: _Spec())
    t = brain_notes.compose_turn("find me a free 45 minutes", ["[SISTEMA] Traída de Email hecha"])
    assert "ENTERA en English" in t
    assert brain_notes.operator_half(t) == "find me a free 45 minutes", "the header is still found verbatim"


def test_a_turn_with_no_notes_is_untouched():
    assert brain_notes.compose_turn("hello", []) == "hello"
