"""V2-781 — «I couldn't: No encuentro ese vídeo en la lista.» in an English session.

Measured in `la-cola-de-video-con-palabras-imprecisas__us` (2026-10-10): two replies came half in Spanish, and the
gate flagged them. Two causes, one per half of the sentence:

  · the WIDGET's refusal is authored in Spanish (the manifests' language), and the reply door
    (`outgoing_lang.said_in_session_language`) could not tell — «No encuentro ese vídeo en la lista» carried one
    marker («la») and the door needs two, so it was left alone;
  · the text channel's own wrapper, when the model had spoken over a failed op, was a Spanish literal
    («No he podido: …») instead of the language table's `widget_data_failed`.

The door now knows the words a widget's refusal is made of, and the wrapper comes from the table.
"""
from __future__ import annotations

import pytest

from nucleo.flash import outgoing_lang as ol
from nucleo.flash import widget_data_turn as wdt


@pytest.fixture
def english(monkeypatch):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: "en")
    try:
        from voice.engine.core import langs as vlangs
        monkeypatch.setattr(vlangs, "current_code", lambda: "en")
        monkeypatch.setattr(vlangs, "current_language", lambda: langs.spec("en"))
    except Exception:
        pass


@pytest.mark.parametrize("said", [
    "I couldn't: No encuentro ese vídeo en la lista.",
    "No hay más vídeos en la lista.",
    "La lista está vacía, no hay nada que guardar.",
    "Dime qué vídeos busco.",
])
def test_a_widgets_spanish_refusal_reads_as_spanish(said, english):
    assert ol.foreign_to_session(said) is True


@pytest.mark.parametrize("said", [
    "I couldn't find that video in the list.",
    "There are no more videos in the queue.",
    "Done.",
])
def test_english_is_left_alone(said, english):
    assert ol.foreign_to_session(said) is False


def test_the_wrapper_over_a_spoken_failure_comes_from_the_language_table(english):
    out = wdt.ensure_failure_named("Skipping to the next one.",
                                   {"executed": "widget_data_failed", "message": "There are no more videos."})
    assert "No he podido" not in out
    assert "I couldn't: There are no more videos." in out
