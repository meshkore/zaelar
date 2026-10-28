"""«Cierra la música» answered with the player's PAUSE is the card's close, in both channels (V2-781, ES round 2026-10-11).

Turn 9: «Ah, vale, perfecto. Pues ahora cierra la música, que ya no la quiero» → the model called
`widget_data musica:pause`, the turn said «Hecho en Música», and the card stayed on the canvas two turns later. The
`play_music` branch already had the rule (`card_close.player_close`); the `widget_data` path only knew the SHORT close
order («Vale, ciérralo»). `card_close.data_close` is now the one door for both — the short close (unless the verdict
names this very action) and a player's stop/pause under a close verb that names its card — and both channels call it.
"""
from __future__ import annotations

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
    from nucleo.acts import named_target as NT
    NT._PARKED.clear()


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


def test_the_voice_turn_calls_the_one_door(screen):
    """The voice rail reaches `data_close` through the card door's licence (refactor2710-05 T-02): the short close is
    its `short-close` clause, read at the model's call, and it closes the card it names."""
    from nucleo.acts import card
    lic = card.licence({"brief": _brief(), "text": "Vale, ciérralo"}, "youtube", "mute", {}, at=card.CALL)
    assert (lic.verdict, lic.clause, lic.card) == (card.CLOSE, "short-close", "youtube")
    for door in ("nucleo/flash/tool_executor_widget_calls.py", "nucleo/acts/card.py"):
        assert "is_short_close_order" not in (ENGINE / door).read_text(encoding="utf-8"), \
            "the short close reaches the voice rail through `data_close` only"
