"""V2-794 — a request to PUT TOGETHER something for him is an errand, not a play of his description as a title.

Measured on a live session: «monta una lista de música para ambientar un cumpleaños, estaremos adultos de 45 a 50»
→ the model called the player's `play` with that sentence as its query, and «Cumpleaños Feliz» played. The brief's
escalate question — now worded so that a collection put together to fit what he describes is background work
(measured live: four domains at 0.88-0.98, every one-step play `handle_inline` at 1.00) — is the one paid reading
of the whole turn. A player's one-shot play over a SURE commission verdict becomes the errand; the
errand it starts opens no empty sheet when its end state is one of his own cards; a silent start says so.
Nothing here names a domain: the verdict, the player table and the manifests carry it.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from nucleo.acts import media as PC

LIST_ORDERS = {
    "es_songs": "Somos gente de 45 a 55, amantes del rock, poco reguetón, pop español y canciones de fiesta. Monta una lista.",
    "en_songs": "Build me a 30-song playlist for a road trip with my parents.",
    "es_video": "Hazme una lista de vídeos de recetas para una cena de seis.",
}


def _brief(answers: dict) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": ["musica"],
            "result": {k: {"choice": c, "confidence": p} for k, (c, p) in answers.items()}}


SURE = _brief({"escalate_or_inline": ("escalate", 0.94), "request_type": ("order", 0.95)})


@pytest.mark.parametrize("case", sorted(LIST_ORDERS))
def test_a_play_over_a_sure_commission_is_the_errand(case):
    assert PC.commissioned(SURE, {"action": "play", "query": LIST_ORDERS[case]})


@pytest.mark.parametrize("why,brief,args", [
    ("a one-step play reads inline", _brief({"escalate_or_inline": ("handle_inline", 1.0), "request_type": ("order", 1.0)}),
     {"action": "play", "query": "algo de Madonna"}),
    ("an unsure commission keeps the model's play", _brief({"escalate_or_inline": ("escalate", 0.7),
                                                             "request_type": ("order", 1.0)}),
     {"action": "play", "query": "música para una fiesta"}),
    ("a remark is no order", _brief({"escalate_or_inline": ("escalate", 0.95), "request_type": ("comment", 0.9)}),
     {"action": "play", "query": "x"}),
    ("a control is never a commission", SURE, {"action": "pause", "query": ""}),
    ("a queue is the model's own chaining", SURE, {"action": "queue", "query": "otra"}),
    ("a bare resume has nothing to put together", SURE, {"action": "play", "query": ""}),
    ("no brief, no verdict", None, {"action": "play", "query": "una lista"}),
])
def test_what_keeps_the_play(why, brief, args):
    assert not PC.commissioned(brief, args), why


def test_the_voice_turn_escalates_instead_of_playing(monkeypatch):
    from nucleo.flash import tool_executor_calls as tec
    music_req, esc, events = {"v": None}, {"v": None, "more": [], "surface": {}}, []
    tec._t_play_music(args={"action": "play", "query": LIST_ORDERS["es_songs"]}, music_req=music_req, _brief=SURE,
                      _apply_widget_data=lambda *a: None, acted={"widget": False}, clarify={"msg": ""},
                      emit=lambda *a, **k: events.append(a), text=LIST_ORDERS["es_songs"], esc=esc)
    assert music_req["v"] is None, "nothing is played"
    assert esc["v"] == LIST_ORDERS["es_songs"], "his words are the errand"
    assert esc.get("say"), "a silent start has its line"
    assert any("⚖️" in a[1] for a in events)


def test_the_voice_turn_still_plays_a_one_step_order():
    from nucleo.flash import tool_executor_calls as tec
    music_req, esc = {"v": None}, {"v": None, "more": [], "surface": {}}
    inline = _brief({"escalate_or_inline": ("handle_inline", 1.0), "request_type": ("order", 1.0)})
    tec._t_play_music(args={"action": "play", "query": "Madonna"}, music_req=music_req, _brief=inline,
                      _apply_widget_data=None, emit=None, text="pon algo de Madonna", esc=esc)
    assert music_req["v"] == {"query": "Madonna", "action": "play"} and esc["v"] is None


def test_a_silent_start_says_so_once_and_a_spoken_one_says_nothing_more():
    from nucleo.turn import promise_kept as pk
    said: list = []
    sp = SimpleNamespace(sanitize=lambda t, **k: t)
    assert pk.say_the_start({"say": "Me pongo con ello."}, "", send=said.append, speech=sp) == "Me pongo con ello."
    assert pk.say_the_start({"say": "Me pongo con ello."}, "Vale, te la monto.", send=said.append, speech=sp) == ""
    assert said == ["Me pongo con ello."]


@pytest.mark.parametrize("end,want", [
    ("musica:playlists", "widget"),        # a collection his own card declares: the errand fills it, no sheet
    ("documento:chars", ""),               # the document sheet IS a sheet surface
    ("results:empty", ""),
    ("musica:now_playing", ""),            # a scalar field, not rows of a declared collection
    ("none", ""),
])
def test_the_errand_opens_no_empty_sheet_when_it_fills_one_of_his_cards(end, want):
    from nucleo import surfaces
    assert surfaces.own_card(_brief({"end_state": (end, 0.8)})) == want
