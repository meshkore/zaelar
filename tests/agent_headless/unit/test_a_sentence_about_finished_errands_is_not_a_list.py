"""A sentence about errands that just FINISHED is a conversation with them, not a new list (node 2.551).

three-tasks-at-once (ES, 2026-10-11 11:34, sandbox 113401-es). The report, the monitor hunt and the game had all
finished when he said «Oye, me has dicho que el monitor era de 27 o más, y ahora me sacas un LG de 24 y un Asus de
23,8... eso no me vale, jolín. ¿Dónde está el Fujitsu P27 aquel de 59 euros? … Y al juego, ya que está hecho, ¿le
puedes poner monedas? Y del informe, no me digas que no consta nada...». `about_errands_under_way` read only LIVE and
PARKED errands — none — so the list lane took it, answered «Entendido, me pides varias cosas. Me pongo con ellas y te
aviso cuando termine», and his ≥27" complaint and his question about the Fujitsu were never answered. Twice.
"""
from __future__ import annotations

import time
import types

import pytest

from nucleo import dispatch
from nucleo.dispatch import confirm as dc
from nucleo.batch import detect
from nucleo.flash import escalate
from nucleo.turn import errands_of_a_turn as E
from nucleo.workers import ended

HEARD = ("Oye, un momento. Me has dicho que el monitor era de 27 o más, y ahora me sacas un LG de 24 y un Asus de "
         "23,8... eso no me vale, jolín. ¿Y el Fujitsu P27 aquel de 59 euros? Ese era de 27. ¿Dónde está? No me lo "
         "pierdas. Y al juego, ya que está hecho, ¿le puedes poner monedas para ir cogiendo? Y del informe, no me "
         "digas que no consta nada... ¿lo estás haciendo o no?")
GOALS = {"1": "Elaborar un INFORME escrito sobre coches eléctricos para uso urbano",
         "3": E.listing_errand({"query": "monitor de segunda mano barato", "condition": "usado"}),
         "6": "Crear un widget nuevo: un juego de plataformas tipo Super Mario, jugable con teclado"}


@pytest.fixture
def all_finished(monkeypatch):
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(label="", title=""))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    monkeypatch.setattr(escalate, "_tasks", {})
    now = time.time()
    store = {tid: {"id": tid, "goal": g, "status": "done", "ok": True, "summary": "", "at": now - 60, "told": 0,
                   "sheet": "results::1ba6ee-3" if tid == "3" else "", "title": "", "kind": "", "error_class": ""}
             for tid, g in GOALS.items()}
    store["1"]["at"] = now - 380          # the report finished six minutes before: past the old five-minute window
    monkeypatch.setattr(ended, "_ENDED_SESSIONS", store)
    monkeypatch.setattr(ended, "_live_goals", lambda: set())


def test_the_measured_sentence_passes_the_shape_floor():
    assert detect.could_be_a_list(HEARD), "otherwise this test proves nothing about the list lane"


def test_a_sentence_about_finished_errands_is_not_a_new_list(all_finished):
    assert detect.about_errands_under_way(HEARD)


def test_with_no_errand_at_all_the_list_lane_is_unchanged(all_finished, monkeypatch):
    monkeypatch.setattr(ended, "_ENDED_SESSIONS", {})
    assert not detect.about_errands_under_way(HEARD)
