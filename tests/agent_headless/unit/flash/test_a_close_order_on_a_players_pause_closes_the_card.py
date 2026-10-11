"""«Cierra la música» answered with the player's PAUSE is the card's close, in both channels (V2-781, ES round 2026-10-11).

Turn 9: «Ah, vale, perfecto. Pues ahora cierra la música, que ya no la quiero» → the model called
`widget_data musica:pause`, the turn said «Hecho en Música», and the card stayed on the canvas two turns later. The
`play_music` branch already had the rule (`card_close.player_close`); the `widget_data` path only knew the SHORT close
order («Vale, ciérralo»). `card_close.data_close` is now the one door for both — the short close (unless the verdict
names this very action) and a player's stop/pause under a close verb that names its card — and both channels call it.
"""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

from nucleo.flash import card_close as CC

ENGINE = Path(__file__).resolve().parents[4]
THREE = ["youtube", "musica", "agenda"]


def _brief(screen: str = "", conf: float = 0.5, open_ids=THREE) -> dict:
    ev = threading.Event()
    ev.set()
    res = {"screen_action": {"choice": screen, "confidence": conf}} if screen else {}
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids), "result": res}


@pytest.fixture
def screen(monkeypatch):
    import server.voice_api as _va
    from memory import api as _memapi
    monkeypatch.setattr(_va, "open_instances", lambda: list(THREE))
    monkeypatch.setattr(_memapi, "state", lambda *a, **k: {"open_widgets": list(THREE)})
    monkeypatch.setattr(_memapi, "kv_get", lambda k, *a, **kw: None)
    from nucleo.flash import named_target as NT
    NT._PARKED.clear()


class _Sess:
    window: list = []
    last_action = ""


@pytest.mark.parametrize("text", [
    "Ah, vale, perfecto. Pues ahora cierra la música, que ya no la quiero.",
    "close the music, I don't want it any more",
])
def test_a_pause_under_a_close_naming_the_card_is_its_close(screen, text):
    assert CC.data_close("musica", "pause", text, brief=_brief("musica:pause", 0.81))
    assert CC.data_close("musica", "stop", text)


@pytest.mark.parametrize("wid,action,text", [
    ("musica", "pause", "pausa la música un momento"),              # no close verb
    ("musica", "volume_down", "cierra la música, que ya no la quiero"),   # a volume is never a close
    ("youtube", "pause", "cierra la música, que ya no la quiero"),  # names the OTHER card
    ("musica", "pause", "pausa la música y cierra la agenda"),      # two cards, two orders
    ("agenda", "show_day", "cierra la música y dime qué tengo el jueves en la agenda"),   # not a player
])
def test_everything_else_stays_a_data_op(screen, wid, action, text):
    assert not CC.data_close(wid, action, text)


def test_the_short_close_order_keeps_its_rule(screen):
    assert CC.data_close("youtube", "mute", "Vale, ciérralo", brief=_brief())
    assert not CC.data_close("agenda", "close_meeting", "ya la puedes cerrar", brief=_brief("agenda:close_meeting", 0.99))


def test_the_text_channel_closes_the_card_and_the_receipt_says_so(screen):
    from nucleo.flash import probe_decide as PD
    from nucleo.flash import router_guards as RG
    from nucleo.flash import card_receipt as R
    text = "Ah, vale, perfecto. Pues ahora cierra la música, que ya no la quiero."
    calls = [{"name": "widget_data", "args": {"widget_id": "musica", "action": "pause", "payload": {}}}]
    blk = asyncio.run(PD.name_the_action(_hard=None, _router=RG, _tbrief=_brief("musica:pause", 0.81), _vault_gate=None,
                                         ingest=None, names=["widget_data"], sess=_Sess(), tags=[], text=text,
                                         tool_calls=calls))
    assert blk["action"] == "canvas:close:musica", blk
    acts = R.acts_of_probe_turn(blk["action"], [], calls)
    assert ("musica", R.CLOSE, "close") in acts, acts


def test_both_channels_call_the_one_door():
    probe = (ENGINE / "nucleo/flash/probe_decide.py").read_text(encoding="utf-8")
    assert "_card_close.data_close(_wid, _act, text, brief=_tbrief)" in probe
    voice = (ENGINE / "nucleo/flash/tool_executor_widget_calls.py").read_text(encoding="utf-8")
    assert "_txw._card_close.data_close(wid, action_name, text, brief=_brief)" in voice
    assert "is_short_close_order" not in voice, "the short close reaches the voice rail through `data_close` only"
