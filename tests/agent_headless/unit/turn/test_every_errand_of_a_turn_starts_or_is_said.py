"""Every errand a turn asks for either starts or is said not to have started (three-tasks-at-once, 2026-10-10).

Measured on both twins. «Tengo tres cosas: un informe, un monitor barato de segunda mano y un widget de un juego»:

  · ES (20261010-145227-es) turn 1 — the model called escalate(report), search_listings(monitor), escalate(game).
    Two errands started; the monitor never existed. The listing lane is skipped whenever the turn escalated
    («two workers running the same hunt is the plumber defect») — right for the SAME hunt, and it dropped a
    DIFFERENT one without a trace. The operator spent nineteen minutes hearing «sigo con el monitor».
  · EN (20261010-145237-en) turn 2 — «Cool. And make that one jump higher» answered the build question, and the
    model's escalate(monitor) of that same turn vanished: a resolved confirmation clears the turn's escalations,
    because «it answers what is parked, it opens nothing new». It must not reopen the PARKED errand; an
    unrelated one it ordered in the same breath is still an order.
  · and the cap (three per turn, the worker pool) dropped a fourth errand silently.

The rules live in ONE module both channels call (`nucleo/turn/errands_of_a_turn.py`): a listing hunt that is not
one of the turn's escalations rides as one more errand; what a yes/no resolved is taken out, the rest stays; what
the pool cannot take is NAMED back to him in his language.
"""
from __future__ import annotations

import asyncio
import types

import pytest

from nucleo.turn import errands_of_a_turn as E

REPORT_ES = ("Elaborar un informe completo sobre coches eléctricos para uso en ciudad: modelos disponibles, autonomía "
             "real en ciudad, precio, coste de recarga y mantenimiento.")
GAME_ES = ("Construir un widget de un juego de plataformas tipo Super Mario, jugable, para probar: personaje que corre "
           "y salta sobre plataformas.")
GAME_EN_1 = ("Build a small platform-style video game widget for the canvas, Super Mario style: a playable character "
             "that runs and jumps across platforms, with the operator able to try it on screen.")
GAME_EN_2 = ("Build a new canvas widget: a small platform-style video game, Super Mario style. A playable character "
             "that runs and jumps across platforms, in the classic retro side-scrolling style. The jump must be high.")
MONITOR_EN = ("Search for cheap used computer monitors for sale (second-hand marketplaces, real listings). Show the "
              "best options compared: price, size/resolution if given, condition and location/link.")


# ── the decisions ──────────────────────────────────────────────────────────────────────────────────────────────

def test_a_listing_hunt_beside_other_errands_rides_as_one_more():
    req = E.listing_rides({"query": "monitor de segunda mano", "price_max": 150, "condition": "usado"},
                          [REPORT_ES, GAME_ES])
    assert "monitor de segunda mano" in req and "150" in req


def test_a_listing_hunt_that_is_one_of_the_escalations_does_not_ride():
    assert E.listing_rides({"query": "cheap used monitor"}, [MONITOR_EN]) == ""
    assert E.listing_rides({"query": "cheap used monitor"}, []) == "", "alone, it is the fast lane's job"
    assert E.listing_rides(None, [REPORT_ES]) == ""


def test_an_answer_takes_out_the_errand_it_resolved_and_keeps_the_others():
    assert E.beside_an_answer(GAME_EN_1, [MONITOR_EN, GAME_EN_2]) == [MONITOR_EN]
    assert E.beside_an_answer("", [MONITOR_EN]) == [MONITOR_EN]


def test_what_the_pool_cannot_take_is_named():
    kept, dropped = E.within_the_pool(["a1 informe", "b2 monitor", "c3 juego", "d4 vuelo"])
    assert kept == ["a1 informe", "b2 monitor", "c3 juego"] and dropped == ["d4 vuelo"]
    line = E.not_started_line(["Buscar un vuelo a Lisboa para el viernes"])
    assert "vuelo a Lisboa" in line


def test_the_voice_cap_records_what_it_drops():
    from nucleo.flash import tool_executor_calls as TC
    req = {"v": None, "more": [], "surface": {}}
    for r in ("informe de coches", "monitor barato", "juego de plataformas", "vuelo a Lisboa"):
        TC._t_escalate_to_slowbrain(args={"request": r}, escalate_req=req, text="x")
    assert req["v"] == "informe de coches" and req["more"] == ["monitor barato", "juego de plataformas"]
    assert req.get("dropped") == ["vuelo a Lisboa"]


def test_the_voice_listing_lane_hands_a_different_hunt_to_the_escalations():
    from nucleo.flash import listing_turn as LT
    listing = {"v": {"query": "monitor de segunda mano", "price_max": None, "price_min": None, "condition": ""}}
    esc = {"v": REPORT_ES, "more": [GAME_ES], "surface": {}}
    assert LT.runs_alone(listing, {"v": None}, esc) is False
    assert len(esc["more"]) == 2 and "monitor de segunda mano" in esc["more"][-1]
    assert esc["surface"][esc["more"][-1]] == "lista"
    alone = {"v": None, "more": [], "surface": {}}
    assert LT.runs_alone(listing, {"v": None}, alone) is True and alone["more"] == []


def test_the_voice_answer_keeps_the_errands_beside_it():
    esc = {"v": GAME_EN_2, "more": [MONITOR_EN], "surface": {}}
    E.keep_beside_an_answer(esc, GAME_EN_1)
    assert esc["v"] == MONITOR_EN and esc["more"] == []
    esc = {"v": GAME_EN_2, "more": [], "surface": {}}
    E.keep_beside_an_answer(esc, GAME_EN_1)
    assert esc["v"] is None and esc["more"] == []


# ── the text channel, end to end through its executor ──────────────────────────────────────────────────────────

@pytest.fixture
def probe_exec(monkeypatch):
    from nucleo.flash import escalate as esc_mod, probe as P, probe_companions as PC
    from nucleo.turn import confirm_gates as G
    started: list = []
    monkeypatch.setattr(esc_mod, "escalate_to_slowbrain",
                        lambda req, context=None: started.append((req, (context or {}).get("surface"))) or len(started))

    async def _nothing(**kw):
        return None

    async def _no_companions(*a, **k):
        return None
    monkeypatch.setattr(P._probe_scheduling, "run_scheduling_backstops", _nothing)
    monkeypatch.setattr(PC, "run", _no_companions)
    answer = {"v": G.Answered()}
    monkeypatch.setattr(G, "resolve_all", lambda text, **k: answer["v"])

    def run(action, tool_calls, text):
        from nucleo.flash import probe_after as PA
        return asyncio.run(PA.execute_what_was_decided(
            _kind=None, _r=None, _res=None, _tbrief=None, _trace_id="t", _window_goal="", action=action, execute=True,
            images_req=None, music_req=None, operator_text=text, sess=types.SimpleNamespace(window=[]), spoken="",
            tags=[], text=text, tool_calls=tool_calls, video_req=None))
    return run, started, answer


def test_the_text_channel_starts_the_listing_hunt_beside_the_escalations(probe_exec):
    run, started, _ = probe_exec
    calls = [{"name": "escalate_to_slowbrain", "args": {"request": REPORT_ES, "surface": "informe"}},
             {"name": "search_listings", "args": {"query": "monitor de segunda mano"}},
             {"name": "escalate_to_slowbrain", "args": {"request": GAME_ES, "surface": "widget"}}]
    run("escalate", calls, "Oye, tengo tres cosas.")
    reqs = [r for r, _s in started]
    assert len(reqs) == 3 and any("monitor de segunda mano" in r for r in reqs), reqs
    assert dict(started)[next(r for r in reqs if "monitor" in r)] == "lista"


def test_the_text_channel_keeps_an_errand_beside_a_yes(probe_exec):
    from nucleo.turn import confirm_gates as G
    run, started, answer = probe_exec
    answer["v"] = G.Answered(gate="task", yes=True, result={"request": GAME_EN_1, "ok": True})
    calls = [{"name": "escalate_to_slowbrain", "args": {"request": MONITOR_EN, "surface": "lista"}},
             {"name": "escalate_to_slowbrain", "args": {"request": GAME_EN_2, "surface": "widget"}}]
    out = run("escalate", calls, "Cool. And make that one jump higher, okay?")
    assert out["action"] == "confirm_task"
    assert [r for r, _s in started] == [MONITOR_EN], "the yes relaunches the parked build; the monitor still starts"


def test_the_text_channel_names_what_the_pool_did_not_take(probe_exec):
    run, started, _ = probe_exec
    calls = [{"name": "escalate_to_slowbrain", "args": {"request": r}}
             for r in ("Informe de coches eléctricos", "Monitor barato usado", "Juego de plataformas",
                       "Vuelo a Lisboa el viernes")]
    out = run("escalate", calls, "cuatro cosas")
    assert len(started) == 3
    assert out["return_extra_exec"].get("not_started") == ["Vuelo a Lisboa el viernes"]


def test_the_words_it_owes_say_what_did_not_start():
    from nucleo.flash import probe_after as PA
    out = asyncio.run(PA.the_words_it_owes(
        _hw=True, _parts=None, _show_chose=None, action="escalate", images_req=None,
        return_extra_exec={"executed": "escalate", "not_started": ["Vuelo a Lisboa el viernes"]},
        sess=types.SimpleNamespace(window=[]), spoken="Voy con las cuatro.", tags=[], text="x", video_req=None))
    assert out["spoken"].startswith("Voy con las cuatro.") and "Vuelo a Lisboa" in out["spoken"]
