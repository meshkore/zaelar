"""A control call on one player, with the other player open, asks WHOSE player it is (V2-781, after V2-740).

Measured in `tres-tarjetas-y-el-video-por-alusion` (ES+EN, 2026-10-10): the Dune trailer on the YouTube card and
the music card both open and playing, «turn the volume down a bit» / «bájale un poco el volumen». The model called
`play_music {action: volume_down}` and the turn silently turned the MUSIC down («Volume at 55 percent»). Both
widgets declare the same control actions, so the name of the tool decides nothing.

The decision for this already existed (`frontend.which_card`, V2-740) and every `widget_data` call consults it —
`play_music` never did. These drive the REAL decision with the REAL brief shape, on both channels:
  · the verdict names THIS action on the other card → the order moves there, through that card's own rail;
  · the verdict names the model's own card, or the other player is not open → nothing changes;
  · no verdict → the operator is asked which one (`consent.ASK_WHICH`'s sentence, with both names).
A play WITH a query asks for content and is never a control.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from nucleo.flash import player_control as PC
from nucleo.flash import probe_decide as PD
from nucleo.flash import router_guards as RG

BOTH = ["youtube", "musica"]


def _brief(choice: str, confidence: float = 0.95, *, open_ids=BOTH) -> dict:
    """A brief handle exactly as `jev.ask_many` hands one over."""
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids),
            "result": {"screen_action": {"choice": choice, "confidence": confidence}}}


@pytest.fixture(autouse=True)
def _open_cards(monkeypatch):
    """What is on screen when the brief carries no open set (Jev off): both players."""
    from memory import api as _memapi
    monkeypatch.setattr(_memapi, "state", lambda *a, **k: {"open_widgets": list(BOTH)})


# ── the decision ──────────────────────────────────────────────────────────────────────────────────────────

def test_the_verdict_moves_a_music_control_to_the_video():
    plan = PC.plan("play_music", "volume_down", "", brief=_brief("youtube:volume_down"))
    assert plan["route"] == "card" and plan["card"] == "youtube", plan


def test_the_verdict_naming_the_music_keeps_it():
    assert PC.plan("play_music", "pause", "", brief=_brief("musica:pause"))["route"] == "keep"


def test_no_verdict_asks_which_player_with_both_names():
    plan = PC.plan("play_music", "volume_down", "", brief=None)
    assert plan["route"] == "ask", plan
    assert "youtube" in plan["ask"] and "musica" in plan["ask"] and "{" not in plan["ask"], plan["ask"]


def test_with_only_the_music_open_nothing_is_asked(monkeypatch):
    from memory import api as _memapi
    monkeypatch.setattr(_memapi, "state", lambda *a, **k: {"open_widgets": ["musica"]})
    assert PC.plan("play_music", "volume_down", "", brief=None)["route"] == "keep"
    assert PC.plan("play_music", "volume_down", "", brief=_brief("", open_ids=["musica"]))["route"] == "keep"


def test_a_play_with_a_query_is_not_a_control():
    assert PC.plan("play_music", "play", "lo-fi para estudiar", brief=None)["route"] == "keep"
    assert PC.plan("play_music", "volume_down", "", brief=_brief("musica:volume_down"))["route"] == "keep"


# ── the text channel (the one the use cases drive) ─────────────────────────────────────────────────────────

class _Sess:
    window: list = []
    last_action = ""


def _probe(calls, brief):
    return asyncio.run(PD.name_the_action(_hard=None, _router=RG, _tbrief=brief, _vault_gate=None, ingest=None,
                                          names=[c["name"] for c in calls], sess=_Sess(), tags=[],
                                          text="turn the volume down a bit", tool_calls=calls))


def test_the_probe_runs_the_moved_control_on_the_video_card():
    calls = [{"name": "play_music", "args": {"action": "volume_down"}}]
    blk = _probe(calls, _brief("youtube:volume_down"))
    assert blk["action"] == "widget_data", blk
    wd = [c["args"] for c in calls if c["name"] == "widget_data"]
    assert wd and wd[0]["widget_id"] == "youtube" and wd[0]["action"] == "volume_down", calls
    assert not blk.get("music_req"), "the music was going to be turned down as well"


def test_the_probe_asks_and_says_the_question_instead_of_the_models_claim():
    calls = [{"name": "play_music", "args": {"action": "volume_down"}}]
    blk = _probe(calls, None)
    assert blk["action"] == "clarify", blk
    assert "youtube" in blk.get("spoken", "") and "musica" in blk.get("spoken", ""), blk
    assert not blk.get("music_req"), "asking and acting at once"


def test_the_probe_keeps_an_unambiguous_music_control():
    calls = [{"name": "play_music", "args": {"action": "volume_down"}}]
    blk = _probe(calls, _brief("musica:volume_down"))
    assert blk["action"] == "music" and blk["music_req"]["action"] == "volume_down", blk


# ── the voice channel ──────────────────────────────────────────────────────────────────────────────────────

def _voice(args, brief, music_req=None):
    from nucleo.flash import tool_executor_calls as TXC
    music_req = music_req if music_req is not None else {"v": None}
    applied, clarify, acted = [], {"msg": ""}, {"widget": False}
    TXC._t_play_music(args=args, music_req=music_req, _brief=brief,
                      _apply_widget_data=lambda w, a, p, ref="": applied.append((w, a, p)),
                      acted=acted, clarify=clarify, emit=lambda *a, **k: None)
    return music_req, applied, clarify, acted


def test_the_voice_runs_the_moved_control_on_the_video_card():
    mr, applied, clarify, _ = _voice({"action": "volume_down"}, _brief("youtube:volume_down"))
    assert applied == [("youtube", "volume_down", {})], applied
    assert mr["v"] is None and not clarify["msg"]


def test_the_voice_asks_which_player():
    mr, applied, clarify, acted = _voice({"action": "pause"}, None)
    assert not applied and mr["v"] is None
    assert "youtube" in clarify["msg"] and "musica" in clarify["msg"] and acted["widget"], clarify


def test_the_voice_keeps_a_control_that_follows_a_play_of_the_same_turn():
    """«pon Queen y súbele el volumen»: the second call is about the music the first one just put on."""
    mr = {"v": {"action": "play", "query": "Queen"}}
    mr, applied, clarify, _ = _voice({"action": "volume_up"}, None, music_req=mr)
    assert not applied and not clarify["msg"] and mr.get("followup", {}).get("action") == "volume_up", mr


def test_both_channels_call_the_one_helper():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[4]
    for rel in ("nucleo/flash/probe_decide.py", "nucleo/flash/tool_executor_calls.py"):  # the one helper, both
        assert "_player_control." in (root / rel).read_text(encoding="utf-8"), rel
