"""A control both open players declare is settled by the screen verdict only when it is SURE (V2-781, second round).

Measured in `tres-tarjetas-y-el-video-por-alusion` (2026-10-10), the trailer and the music both open: «Turn the
volume down a bit» read `musica:volume_down` at 0.54 (EN) and «bájale un poco el volumen» at 0.60 (ES). Both above
Jev's 0.5 floor, so `which_card` kept the model's `play_music` and the music went down in silence — «Done — turning
the music down.» The case calls it what it is: choosing in silence and getting it right is luck. Below
`player_control.PLAYER_SURE` the operator is asked which (`consent.ASK_WHICH`'s sentence).

And the neighbour that keeps it from becoming a nag: a player his words NAME («turn the music down», «baja el
vídeo») decides before any verdict, sure or not.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from nucleo.flash import player_control as PC

BOTH = ["youtube", "musica", "agenda"]


def _brief(choice: str, confidence: float, *, open_ids=BOTH) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids),
            "result": {"screen_action": {"choice": choice, "confidence": confidence}}}


@pytest.fixture(autouse=True)
def _open_cards(monkeypatch):
    from memory import api as _memapi
    monkeypatch.setattr(_memapi, "state", lambda *a, **k: {"open_widgets": list(BOTH)})


@pytest.mark.parametrize("conf", [0.54, 0.60, 0.79])
def test_an_unsure_verdict_between_two_players_asks_which(conf):
    plan = PC.plan("play_music", "volume_down", "", brief=_brief("musica:volume_down", conf),
                   operator_text="Thanks. Turn the volume down a bit.")
    assert plan["route"] == "ask", plan
    assert "youtube" in plan["ask"] and "musica" in plan["ask"], plan["ask"]


def test_a_sure_verdict_still_decides():
    assert PC.plan("play_music", "volume_down", "", brief=_brief("musica:volume_down", 0.9),
                   operator_text="turn it down a bit")["route"] == "keep"
    p = PC.plan("play_music", "volume_down", "", brief=_brief("youtube:volume_down", 0.9), operator_text="lower it")
    assert p["route"] == "card" and p["card"] == "youtube", p


@pytest.mark.parametrize("text,card", [
    ("turn the music down a bit", "musica"),
    ("bájale un poco a la música", "musica"),
    ("turn the video down a bit", "youtube"),
    ("pausa el vídeo", "youtube"),
])
def test_a_player_his_words_name_decides_over_an_unsure_verdict(text, card):
    act = "pause" if "pausa" in text else "volume_down"
    p = PC.plan("play_music", act, "", brief=_brief(f"musica:{act}", 0.54), operator_text=text)
    assert p["card"] == card and p["route"] == ("keep" if card == "musica" else "card"), (text, p)


def test_with_only_the_music_open_nothing_is_asked(monkeypatch):
    from memory import api as _memapi
    monkeypatch.setattr(_memapi, "state", lambda *a, **k: {"open_widgets": ["musica", "agenda"]})
    p = PC.plan("play_music", "volume_down", "", brief=_brief("musica:volume_down", 0.54, open_ids=["musica", "agenda"]),
                operator_text="turn the volume down a bit")
    assert p["route"] == "keep", p


class _Sess:
    window: list = []
    last_action = ""


def test_the_text_channel_says_the_question_instead_of_turning_the_music_down():
    from nucleo.flash import probe_decide as PD
    from nucleo.flash import router_guards as RG
    calls = [{"name": "play_music", "args": {"action": "volume_down"}}]
    blk = asyncio.run(PD.name_the_action(_hard=None, _router=RG, _tbrief=_brief("musica:volume_down", 0.54),
                                         _vault_gate=None, ingest=None, names=["play_music"], sess=_Sess(), tags=[],
                                         text="Thanks. Turn the volume down a bit.", tool_calls=calls))
    assert blk["action"] == "clarify" and not blk.get("music_req"), blk
    assert "youtube" in blk["spoken"] and "musica" in blk["spoken"], blk


def test_the_voice_asks_too():
    from nucleo.flash import tool_executor_calls as TXC
    music_req, applied, clarify, acted = {"v": None}, [], {"msg": ""}, {"widget": False}
    TXC._t_play_music(args={"action": "volume_down"}, music_req=music_req, _brief=_brief("musica:volume_down", 0.6),
                      _apply_widget_data=lambda w, a, p, ref="": applied.append((w, a)), acted=acted, clarify=clarify,
                      emit=lambda *a, **k: None, text="bájale un poco el volumen")
    assert music_req["v"] is None and not applied and "musica" in clarify["msg"], (music_req, applied, clarify)
