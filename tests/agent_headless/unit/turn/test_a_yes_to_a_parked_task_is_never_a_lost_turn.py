"""A yes (or a no) to a PARKED task speaks its verdict — it is never a lost turn (node 2.400).

V2-834 T01, use case `build-workout-tracker-widget` (sandbox, 2026-11-02): the card was parked on «¿Te la monto ya
con esos tres campos?»; he answered «sí, móntala ya con esos tres, porfa»; the task gate resolved the yes and the
worker started — and the turn said «Perdona, se me ha ido. ¿Me lo dices otra vez?». The model had written nothing
(the gate is the act), nothing marked the turn as handled, so the mute backstop read it as a lost turn.

Mechanism pinned here: when `confirm_gates.resolve_all` answers a parked task or click and the model said nothing,
the settle says the START line (`work_started`) for a yes and `confirm_cancelled` for a no — the same pair the
widget gate says — in the operator's language; words the model did write stand.
"""
from __future__ import annotations

import asyncio

import pytest

from i18n import langs
from nucleo.flash import post_stream_settle as S
from nucleo.turn import confirm_gates as gates


def _settle(monkeypatch, said, answered, spoken_text=""):
    monkeypatch.setattr(gates, "resolve_all", lambda text, brief=None: answered)
    out = []
    got = asyncio.run(S.settle_what_is_pending(
        _ans=None, _ask_waiting=False, _auth_pending=False, _brief=None, _dialog=None, _filler_audio=None,
        _langs=None, _prev_pending=False, _r=None, _resolve_confirm=lambda yes: None, _router=None, _shown_ids=set(),
        acted={"widget": None}, aside={"v": None}, brain=type("B", (), {"_window": [], "_last_spoken": ""})(),
        clarify={"msg": None}, confirm_state={"opened": None, "handled": False}, data_done={"v": False},
        emit=lambda *a, **k: None, escalate_req={"v": None}, had_pending_confirm=False, llm_metrics={},
        music_req={"v": None}, operator_text=said, search_req={"v": None}, send=out.append,
        speech=type("Sp", (), {"sanitize": staticmethod(lambda t, drop_metadata=False: t)}),
        spoken_text=spoken_text, style_fired={"v": None}, text=said, worker_acted={"v": None}))
    return got.get("spoken_text", spoken_text), out


@pytest.fixture(params=["es", "en"])
def lang(request, monkeypatch):
    spec = langs.LANGUAGES[request.param]
    monkeypatch.setattr(langs, "current_language", lambda: spec)
    return spec


@pytest.mark.parametrize("gate", ["task", "browser"])
def test_a_yes_is_said_as_a_start(monkeypatch, lang, gate):
    said, out = _settle(monkeypatch, "sí, móntala ya", gates.Answered(gate=gate, yes=True, result={"request": "x"}))
    assert lang.work_started and said == lang.work_started and out == [lang.work_started]


def test_a_no_is_said_as_nothing_touched(monkeypatch, lang):
    said, out = _settle(monkeypatch, "no, déjalo", gates.Answered(gate="task", yes=False, result={"request": "x"}))
    assert lang.confirm_cancelled and said == lang.confirm_cancelled and out == [lang.confirm_cancelled]


def test_the_models_own_words_stand(monkeypatch, lang):
    said, out = _settle(monkeypatch, "sí", gates.Answered(gate="task", yes=True, result={}), spoken_text="Vale, voy.")
    assert said == "Vale, voy." and out == []


def test_no_gate_answered_says_nothing_here(monkeypatch, lang):
    said, out = _settle(monkeypatch, "hola", gates.Answered())
    assert said == "" and out == []
