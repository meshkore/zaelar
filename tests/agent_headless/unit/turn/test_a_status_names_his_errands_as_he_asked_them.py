"""A status line names his errands as he asked them — never our wrapper, a mid-word cut or his own sentence (2.455).

three-tasks-at-once (ES, 2026-10-11 02:58), said to him twice:
  «Así va todo: Crear un widget nuevo para el canvas: un juego de plataformas tipo Sup: esperando a que me contestes
  algo; Find real marketplace listings for: monitor de ordenador usado (condit: mirando «results»»
and at t14 «Así va todo: Vale, avísame. Yo mientras le echo un ojo al informe ese, que al final: esperando…» — HIS
sentence as an errand's name. Three mechanisms:
  · `named_errand.spoken_name`: the errand's given name, else its label, else his ask (listing wrapper removed)
    clipped on a word; the same name in the status line and in «I've passed that on to …»;
  · a phase that quotes one of our card ids («mirando «results»») is not said;
  · a request DERIVED from his words by a backstop, on a turn whose reply asks him something, is neither parked nor
    started (`escalate.held`): what the question offers is not his sentence.
"""
from __future__ import annotations

import threading
import time
import types

import pytest

from nucleo import dispatch
from nucleo import dispatch_confirm as dc
from nucleo.flash import escalate as esc
from nucleo.flash import probe_after
from nucleo.turn import errands_of_a_turn as E
from nucleo.turn import named_errand

GAME = ("Crear un widget nuevo para el canvas: un juego de plataformas tipo Super Mario, jugable, para probar. Debe "
        "tener un personaje que salte")
MONITOR = E.listing_errand({"query": "monitor de ordenador usado", "condition": "usado"})


def _brief(**verdicts):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {k: {"choice": c, "confidence": 0.99, "probs": {c: 0.99}}
                                    for k, c in verdicts.items()}, "_call_id": "t", "turn_id": "t", "open_ids": []}


@pytest.fixture
def errands(monkeypatch):
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [
        {"id": "3", "request": MONITOR, "phase": "mirando «results»", "waiting_on": ""}])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(label="Investigando…", title="",
                                                                                  goal=MONITOR))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {"2": {"request": GAME, "kind": "code", "trusted": True,
                                                       "context": {}, "sheet": "", "ts": time.time(),
                                                       "question": "¿La hago?"}})


def test_the_status_line_says_his_asks(errands, monkeypatch):
    monkeypatch.setattr("i18n.langs.current_code", lambda: "es")    # a Spanish phase is said to a Spanish ear
    line = E.status_owed("¿Y el monitor cómo va? ¿Y el juego?", _brief(wants_words="tell", request_type="question"))
    assert "Find real marketplace" not in line and "(condit" not in line, line
    assert "monitor de ordenador usado" in line
    assert "tipo Sup:" not in line and "juego de plataformas" in line, "clipped on a word, never mid-word"
    assert "«results»" not in line, "our card id is not a phase"


def test_a_given_name_wins(errands, monkeypatch):
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(
        label="Investigando…", title="Monitores de segunda mano hasta 150 €", goal=MONITOR))
    assert named_errand.spoken_name(named_errand.known()[0]) == "Monitores de segunda mano hasta 150 €"
    assert probe_after._errand_names(["3"]) == ["Monitores de segunda mano hasta 150 €"]


def test_his_sentence_is_never_parked_as_an_errand(monkeypatch):
    published = []
    monkeypatch.setattr(esc, "_emit_bus", lambda topic, payload: published.append(topic))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    his = "Vale, avísame. Yo mientras le echo un ojo al informe ese, que al final corto sí lo has dejado."
    tid = esc.escalate_to_slowbrain(his, context={"src": "probe", "derived": True,
                                                  "asked": "Ya está en tu cesta. ¿Quieres que te abra el navegador?"})
    assert tid == 0 and published == ["escalate.held"] and not dc._PENDING_CONFIRM
    tid = esc.escalate_to_slowbrain("buscar vuelos a Roma",
                                    context={"src": "probe", "asked": "¿Quieres que te busque vuelos a Roma?"})
    assert published[-1] == "escalate.offered", "a model-written errand offered with a question is still parked"


def test_the_text_channel_marks_what_it_derived():
    import inspect
    src = inspect.getsource(probe_after.execute_what_was_decided)
    assert "derived=(operator_text, _window_goal)" in src
