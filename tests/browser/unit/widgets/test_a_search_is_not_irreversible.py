"""V2-665 — a SEARCH is not irreversible, a confirmation never recites our tool prose, and a bare name is not
an errand.

Session e82f7fcb (2026-09-11). He asked for two things — «Ábreme el widget de vídeo» and «¿Me puedes poner el
vídeo del Apolo 11?» — and reported three symptoms: the chat column opened on its own, «mensajes que creo que
son de sistema» appeared in his interface, and the video never played.

All three are ONE cause. At 10:07:07 the model called `widget_data(youtube, search)` and `actions.classify`
answered CONFIRM, so:
  · `widgets/confirm.py` raised an irreversible-action gate → V2-518 puts confirmations in the chat, which is
    the column that opened;
  · the question was composed from the action's `desc`, which is written FOR THE MODEL — he read «Ojo, esto
    es permanente: "BUSCAR vídeos para elegir: pinta hasta n resultados NUMERADOS en el INICIO del widget
    (reemplaza la búsqueda anterior; NUNCA toca la cola ni el reproductor)". ¿Lo confirmo?»;
  · the overlay covered the card — and the video HAD loaded (`videoId 16AhQaStWxg`, «Apolo 11: cómo fue la
    llegada del hombre a la Luna»), dimmed under a modal.

Why CONFIRM: `_IRREVERSIBLE_RE` matched the word «manda» inside «…add_results los manda a la cola» — prose
describing a SIBLING action, in a `view: true` action that writes nothing at all.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from widgets import actions as A

ENG = pathlib.Path(__file__).resolve().parents[4]


def _manifest(wid: str) -> dict:
    return json.loads((ENG / "widgets" / wid / "manifest.json").read_text(encoding="utf-8"))


def _every_action():
    for mf in sorted((ENG / "widgets").glob("*/manifest.json")):
        man = json.loads(mf.read_text(encoding="utf-8"))
        for name, spec in (man.get("actions") or {}).items():
            if isinstance(spec, dict):
                yield mf.parent.name, str(name), spec


# ── the measured action ──────────────────────────────────────────────────────────────────────────────────
def test_searching_for_a_video_asks_nobody_for_permission():
    spec = _manifest("youtube")["actions"]["search"]
    assert spec.get("view") is True, "searching only changes what the card DISPLAYS"
    assert A.classify(spec, "search") == A.FAST, "this is the modal that covered his loaded video"


def test_a_verb_in_the_usage_guidance_no_longer_decides():
    """The word that fired was «manda», in a clause about `add_results`, not about `search`."""
    assert "manda" in _manifest("youtube")["actions"]["search"]["desc"], \
        "the prose that caused it is still there — the fix is that it no longer decides"
    assert not A._looks_irreversible("search", _manifest("youtube")["actions"]["search"]["desc"])
    # …and the action's OWN clause is still read in full
    assert A._looks_irreversible("pay", "Paga la reserva con la tarjeta guardada. Úsala cuando te lo pida.")
    assert A._own_clause("Borra todo. Úsala cuando el operador…") == "Borra todo"


def test_a_view_action_can_never_be_irreversible():
    """Structural, not a word list: `view` means it writes nothing the operator would have to undo."""
    assert A.classify({"view": True, "desc": "envía y publica y paga"}, "send") == A.FAST
    # …unless its author says otherwise IN WORDS: an explicit flag still wins over the exclusion
    assert A.classify({"view": True, "confirm": True, "desc": "x"}, "y") == A.CONFIRM


# ── the whole catalog, which is where the finding came from ──────────────────────────────────────────────
def test_every_confirmation_in_the_catalog_is_an_EXPLICIT_decision():
    """Measured the day this shipped: the heuristic's only two hits were false positives (`youtube:search`
    and `torrent:open`, both `view: true`, both on «manda»), and every true confirmation carries a flag.
    It stays as a backstop for a generated widget that forgot one — it must not be DECIDING anything here."""
    guessed = [f"{w}:{n}" for w, n, sp in _every_action()
               if A.classify(sp, n) == A.CONFIRM
               and sp.get("confirm") is not True and sp.get("irreversible") is not True]
    assert not guessed, f"the catalog is confirming by GUESS, not by declaration: {guessed}"


def test_no_confirmation_recites_prose_written_for_the_model():
    bare = [f"{w}:{n}" for w, n, sp in _every_action()
            if A.classify(sp, n) == A.CONFIRM and not str(sp.get("confirm_q") or "").strip()]
    assert not bare, f"these would read their `desc` out loud: {bare}"


@pytest.mark.parametrize("wid,act", [("youtube", "clear_history"), ("archivos", "delete_file"),
                                     ("mensajeria", "clear_signature"), ("torrent", "remove")])
def test_the_question_is_a_sentence_a_person_hears(wid, act):
    q = _manifest(wid)["actions"][act]["confirm_q"]
    assert q.endswith("?") or "?" in q, q
    for jargon in ("payload", "widget", "NUMERADOS", "`", "apply_action", "Úsala cuando"):
        assert jargon not in q, f"{wid}:{act} still speaks to the model: {q}"


def test_the_gate_refuses_a_confirmation_with_no_question_and_the_view_contradiction():
    """A rule each widget author has to remember is not a rule — `widgets/validator.py` enforces both."""
    from widgets import validator
    assert validator._validate_confirm_questions(
        {"actions": {"borrar": {"desc": "borra todo", "confirm": True}}}), "a bare confirmation must be refused"
    assert validator._validate_confirm_questions(
        {"actions": {"mirar": {"desc": "x", "view": True, "confirm": True}}}), "view+confirm contradict"
    assert validator._validate_confirm_questions(
        {"actions": {"borrar": {"desc": "borra todo", "confirm": True, "confirm_q": "¿Lo borro?"}}}) is None


# ── the trigger: a bare name is an address, not an errand ────────────────────────────────────────────────
@pytest.mark.parametrize("txt", ["Johnny.", "johnny", "Oye Johnny", "Johnny, por favor", "zaelar"])
def test_a_bare_call_by_name_is_a_summons(txt):
    from nucleo.flash.presence import is_summons
    assert is_summons(txt, "Johnny"), txt


@pytest.mark.parametrize("txt", ["Johnny, ponme el vídeo del Apolo 11", "Johnny ¿sigues ahí?",
                                 "johnny cierra todo", "", "   "])
def test_anything_after_the_name_is_a_real_turn(txt):
    from nucleo.flash.presence import is_summons
    assert not is_summons(txt, "Johnny"), txt


def test_both_channels_answer_a_summons_without_a_model():
    """Parallel implementations (V2-252/V2-539): the voice lane speaks it, the probe mirrors it."""
    import inspect

    from nucleo.flash import presence as _p
    from voice.engine.llm.providers import fast_lane as _fl
    assert "is_summons(text, _aname)" in inspect.getsource(_fl.presence), \
        "the voice lane must answer a summons in its own fast lane, never through the model"
    assert "is_summons(text, aname)" in inspect.getsource(_p.mirror), "the probe channel must mirror it"
