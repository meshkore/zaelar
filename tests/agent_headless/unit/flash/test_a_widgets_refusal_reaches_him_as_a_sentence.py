"""A widget's refusal reaches the operator as a sentence in the session's language — never its debug string.

Measured in `docs-single-recipe-not-a-list__us` (2026-10-10 22:08, English session): «Give me the carbonara
recipe.» → `documento:show {"query": "authentic Roman carbonara recipe"}` → refused for its empty body, and the
reply was «I'll get it on screen for you. I couldn't: no llegó ningún contenido para la hoja ('body' vacío)».
Two causes, both closed here:

  · the text channel built its failure from `message or error` — the `error` is written for the MODEL (V2-652),
    in Spanish, with field names in it — and the reply door could not see the Spanish inside the English half;
  · the correction pass that should have written the recipe into `body` was capped at 300 tokens, so its call
    came back truncated (invalid JSON, skipped) and the pass logged «no correction».

`nucleo/flash/refusal_line.py` is the one door: the widget's `say` (an i18n bundle key) or its cleaned `message`,
translated when it is in the other product language, else a plain generic line naming the card. Never `error`.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import refusal_line as RL
from nucleo.flash import widget_data_turn as WDT


def _lang(monkeypatch, code: str):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: code)
    try:
        from voice.engine.core import langs as vlangs
        monkeypatch.setattr(vlangs, "current_code", lambda: code)
        monkeypatch.setattr(vlangs, "current_language", lambda: langs.spec(code))
    except Exception:  # noqa: BLE001 — the voice table is the same table where it exists
        monkeypatch.setattr(langs, "current_language", lambda: langs.spec(code))


@pytest.fixture
def english(monkeypatch):
    _lang(monkeypatch, "en")


@pytest.fixture
def spanish(monkeypatch):
    _lang(monkeypatch, "es")


@pytest.fixture
def rail(monkeypatch):
    """The real widgets answer; the correction pass is offline (it would call a model)."""
    async def _brain_action(wid, act, payload):
        if wid == "documento":
            from widgets.documento import data as doc
            return doc.apply_action(act, payload)
        return {"ok": False, "error": "end_of_list", "message": "No hay más vídeos en la lista."}

    async def _no_fix(*a, **k):
        return None

    import widgets.server_api as _sa
    monkeypatch.setattr(_sa, "brain_action", _brain_action)
    from widgets import actions as _wa
    monkeypatch.setattr("nucleo.flash.frontend.action_mode", lambda wid, act: _wa.FAST)
    monkeypatch.setattr("nucleo.flash.act_repair.call_for_refusal", _no_fix)


def _show_with_only_a_query():
    return [{"name": "widget_data", "args": {"widget_id": "documento", "action": "show",
                                             "payload": {"query": "authentic Roman carbonara recipe"}}}]


def _says_spanish_or_debug(text: str) -> bool:
    return any(w in text for w in ("llegó", "hoja", "'body'", "vacío", "body"))


def test_the_empty_document_is_said_in_english_and_the_reason_stays_in_the_log(rail, english):
    parte = asyncio.run(WDT.execute(_show_with_only_a_query(), "Give me the carbonara recipe."))
    assert parte["executed"] == "widget_data_failed"
    assert not _says_spanish_or_debug(parte["message"]), parte["message"]
    assert "'body'" in parte["fallidas"][0]["error"]                           # kept for us, not said to him
    said = WDT.ensure_failure_named("I'll get it on screen for you.", parte)
    assert not _says_spanish_or_debug(said), said
    assert "the document came back empty" in said, said
    mute = WDT.spoken_for(parte, "Done.")
    assert mute.startswith("I couldn't:") and not _says_spanish_or_debug(mute), mute


def test_the_same_refusal_keeps_spanish_in_a_spanish_session(rail, spanish):
    parte = asyncio.run(WDT.execute(_show_with_only_a_query(), "Dame la receta de la carbonara."))
    assert parte["message"] == "el documento ha llegado vacío, sin nada que enseñar."
    assert WDT.spoken_for(parte, "Hecho.").startswith("No he podido:")


def test_a_refusal_with_only_an_internal_reason_is_a_plain_generic_line(english):
    line = asyncio.run(RL.said("results", {"ok": False, "error": "falta 'index' (1-based)"}))
    assert line == "the Results card didn't take it.", line


def test_the_results_refusal_reads_right_in_both_languages(monkeypatch):
    from widgets.results import data as R              # the widget's own door (its actions import back)
    res = R.apply_action("detail", {"title": "nothing like this"})
    _lang(monkeypatch, "en")
    assert RL.speakable("results", res) == "that result isn't on the sheet."
    _lang(monkeypatch, "es")
    assert RL.speakable("results", res) == "No encuentro ese resultado en la hoja."


def test_a_spanish_message_is_translated_for_an_english_session(english, monkeypatch):
    from nucleo.flash import outgoing_lang as ol

    async def _tr(text, lang):
        return "There are no more videos in the list."
    monkeypatch.setattr(ol, "_translate", _tr)
    res = {"ok": False, "error": "end_of_list", "message": "No hay más vídeos en la lista."}
    assert asyncio.run(RL.said("youtube", res)) == "There are no more videos in the list."


def test_a_spanish_message_that_cannot_be_translated_falls_back_to_the_generic_line(english):
    res = {"ok": False, "error": "end_of_list", "message": "No hay más vídeos en la lista."}
    assert asyncio.run(RL.said("youtube", res)) == "the YouTube card didn't take it."


def test_a_spanish_message_stays_whole_in_a_spanish_session(spanish):
    res = {"ok": False, "error": "end_of_list", "message": "No hay más vídeos en la lista."}
    assert asyncio.run(RL.said("youtube", res)) == "No hay más vídeos en la lista."


def test_the_correction_pass_has_room_to_write_a_document():
    from widgets import runtime
    assert RL.correction_budget(runtime.get("documento"), "show") >= 1200
    assert RL.correction_budget(runtime.get("results"), "detail") == 300


def test_the_documento_refusal_tells_the_model_to_write_the_body_itself():
    from widgets.documento import data as doc
    res = doc.apply_action("show", {"query": "carbonara"})
    assert res["ok"] is False and res["say"] == "widgets.documento.refusal_empty"
    assert "no busca" in res["error"] and "'body'" in res["error"]
