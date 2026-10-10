"""A close that names a card closes THAT card — by its name or by its place on the canvas (V2-781, second round).

Measured in `tres-tarjetas-y-el-video-por-alusion` (ES+EN, 2026-10-10), with the trailer (`youtube`), the music
(`musica`) and the agenda open:

  · EN «Close the music actually.» → the model called nothing («Done.»); canvas verdict `close` 0.99, screen verdict
    `youtube:close` 0.54. The text channel ran the promise repair before the canvas gesture and the repair took the
    screen verdict's card: `youtube:close` emptied the player, the music kept playing, no card left.
  · EN «Actually close the top one too.» → `youtube:close` again, by card mass, over an unsure verdict.
  · ES «cierra la música, que ya está bien de fondo» → `play_music {stop}` → «Pausado.», twice.

These drive the real decisions (the text channel's mirror, the shared `complete_canvas`, the text channel's
`name_the_action`) with the brief shape `jev.ask_many` hands over, and measure the neighbourhood: «close the
calendar», «close the video» (V2-753: the player's content, not a card name), «apaga la música» (= stop the audio),
«pausa la música y cierra la agenda» (two orders), a place on a canvas whose geometry is unknown (asked).
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from nucleo.flash import card_close as CC
from nucleo.flash import direct_action as DA

THREE = ["youtube", "musica", "agenda"]


def _brief(screen: str = "", screen_conf: float = 0.54, canvas: str = "close", canvas_conf: float = 0.99,
           open_ids=THREE) -> dict:
    ev = threading.Event()
    ev.set()
    res = {}
    if screen:
        res["screen_action"] = {"choice": screen, "confidence": screen_conf}
    if canvas:
        res["canvas"] = {"choice": canvas, "confidence": canvas_conf}
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids), "result": res}


@pytest.fixture
def screen(monkeypatch):
    """What is on the canvas — the instances the desktop reported, the normalised state, and its layout."""
    import server.voice_api as _va
    from memory import api as _memapi
    box = {"open": list(THREE), "layout": None}
    monkeypatch.setattr(_va, "open_instances", lambda: list(box["open"]))
    monkeypatch.setattr(_memapi, "state", lambda *a, **k: {"open_widgets": list(box["open"])})
    monkeypatch.setattr(_memapi, "kv_get", lambda k, *a, **kw: box["layout"] if k == "canvas_layout" else None)
    return box


def _layout(**tops) -> dict:
    return {"at": 1, "items": [{"id": w, "left": "40", "top": str(t)} for w, t in tops.items()]}


def _gesture(brief, text: str) -> list:
    tags = []
    DA.complete_canvas(brief, tag_emit=lambda a, x: tags.append((a, x.get("id"))), emit=lambda *a, **k: None,
                       operator_text=text)
    return tags


# ── the shared canvas gesture (voice `complete_canvas`, mirrored by the text channel) ─────────────────────────

def test_close_the_music_closes_the_music_over_a_verdict_naming_the_video(screen):
    assert _gesture(_brief("youtube:close"), "Nice, free Thursday. Close the music actually.") == [("close", "musica")]


def test_cierra_la_musica_closes_the_music_over_a_verdict_naming_the_video(screen):
    assert _gesture(_brief("youtube:close"), "Vale, cierra la música, que ya está bien de fondo.") == [("close", "musica")]


def test_close_the_calendar_and_close_youtube_close_the_card_they_name(screen):
    assert _gesture(_brief("youtube:close"), "close the calendar") == [("close", "agenda")]
    assert _gesture(_brief("youtube:close", 0.95), "close youtube") == [("close", "youtube")]


def test_close_the_video_keeps_the_verdicts_card(screen):
    """«video» is what the player HOLDS, not what the card is called: no other card is named, the verdict stands."""
    assert _gesture(_brief("youtube:close", 0.95), "close the video") == [("close", "youtube")]


def test_the_top_one_is_the_card_at_the_top_of_the_layout(screen):
    screen["open"] = ["youtube", "agenda"]
    screen["layout"] = _layout(youtube=420, agenda=40)
    assert _gesture(_brief("youtube:close", 0.36, open_ids=screen["open"]), "Actually close the top one too.") \
        == [("close", "agenda")]
    screen["layout"] = _layout(youtube=40, agenda=420)
    assert _gesture(_brief("", open_ids=screen["open"]), "cierra la de arriba") == [("close", "youtube")]


def test_a_place_reads_only_as_a_place():
    for text in ("all right, close it", "that's right", "close the first one", "put it on top of the list", "close it"):
        assert CC.place_named(text) == "", text
    assert CC.place_named("Actually close the top one too.") == "top"
    assert CC.place_named("quita la de la derecha") == "right"


# ── the text channel: the gesture runs BEFORE the promise repair, and an unknown place is asked ──────────────

class _Sess:
    window: list = []
    last_action = ""


class _Dialog:
    @staticmethod
    def sanitize_reply(s):
        return s


class _Speech:
    @staticmethod
    def sanitize(s, drop_metadata=False):
        return s


@pytest.fixture
def mirror(monkeypatch, screen):
    """The text channel's mirror block, with the two model passes replaced by recorders."""
    from nucleo.flash import act_repair, card_commission, reply_promise
    repaired = []

    async def _noop(*a, **k):
        return None

    async def _repair(operator_text, reply, wid, *a, **k):
        repaired.append(wid)
        return {"widget_id": wid or "youtube", "action": "close", "payload": {}}

    monkeypatch.setattr(reply_promise, "prefetch", _noop)
    monkeypatch.setattr(act_repair, "call_for_promise_or_order", _repair)
    monkeypatch.setattr(act_repair, "probe_call_for_promise", lambda *a, **k: _repair("", "", "youtube"))
    monkeypatch.setattr(card_commission, "named_or_catalogue", lambda brief, text, **k: "youtube")

    def run(text: str, brief, spoken: str = "Done."):
        from nucleo.flash import probe_mirrors as PM
        from nucleo.flash import router as R
        tool_calls, tags = [], []
        out = asyncio.run(PM.mirror_the_voice_backstops(
            _akp=None, _cw=None, _hw=False, _router=R, _rt=None, _sp=None, _tbrief=brief, action="chat",
            canvas_h=None, dialog=_Dialog, names=[], operator_text=text, sess=_Sess(), spec=None, speech=_Speech,
            spoken=spoken, tags=tags, text=text, tool_calls=tool_calls))
        return out, tool_calls, repaired
    return run


def test_the_text_channel_closes_the_music_instead_of_repairing_a_video_close(mirror):
    out, calls, repaired = mirror("Nice, free Thursday. Close the music actually.", _brief("youtube:close"))
    assert out["action"] == "canvas:close:musica", out
    assert not calls and not repaired, (calls, repaired)


def test_the_text_channel_asks_which_when_the_place_cannot_be_located(mirror, screen):
    screen["open"] = ["youtube", "agenda"]
    out, calls, repaired = mirror("Actually close the top one too.", _brief("youtube:close", 0.36,
                                                                             canvas_conf=1.0, open_ids=screen["open"]))
    assert out["action"] == "clarify", out
    assert "youtube" in out["spoken"] and "agenda" in out["spoken"] and "{" not in out["spoken"], out["spoken"]
    assert not calls and not repaired


def test_the_text_channel_closes_the_top_card_when_the_layout_places_it(mirror, screen):
    screen["open"] = ["youtube", "agenda"]
    screen["layout"] = _layout(youtube=420, agenda=40)
    out, calls, _ = mirror("Actually close the top one too.", _brief("youtube:close", 0.36, canvas_conf=1.0,
                                                                     open_ids=screen["open"]))
    assert out["action"] == "canvas:close:agenda", out
    assert not calls


def test_without_a_sure_canvas_close_the_repair_still_runs(mirror):
    """The neighbour that must not move: a promise over a card with no canvas gesture is still repaired."""
    out, calls, repaired = mirror("pause the trailer", _brief("youtube:pause", 0.97, canvas="neither"))
    assert out["action"] == "widget_data" and repaired == ["youtube"], (out, repaired)


# ── a player's stop dressed as «close the music» (the text channel's `play_music` branch) ────────────────────

def _decide(text: str, action: str = "stop", brief=None, open_ids=THREE):
    from nucleo.flash import probe_decide as PD
    from nucleo.flash import router_guards as RG
    calls = [{"name": "play_music", "args": {"action": action}}]
    tags: list = []
    blk = asyncio.run(PD.name_the_action(_hard=None, _router=RG, _tbrief=brief, _vault_gate=None, ingest=None,
                                         names=["play_music"], sess=_Sess(), tags=tags, text=text, tool_calls=calls))
    return blk, tags


@pytest.mark.parametrize("text", [
    "Vale, gracias. Oye, cierra la música, que ya está bien de fondo.",
    "No, la música — ciérrala, no la pauso. Y el tráiler si lo habías pausado antes ya está bien, la música fuera del todo.",
    "close the music",
])
def test_a_stop_of_the_music_his_words_close_is_the_cards_close(screen, text):
    blk, tags = _decide(text)
    assert blk["action"] == "canvas:close:musica" and not blk.get("music_req"), blk
    assert tags and tags[0]["action"] == "close" and tags[0]["extra"]["id"] == "musica", tags


@pytest.mark.parametrize("text", [
    "apaga la música",                         # stops the audio: the documented broad-verb rule
    "turn off the music",
    "pausa la música y cierra la agenda",     # two cards, two orders
    "stop the music",
    "no cierres la música, solo páusala",     # a negated close
])
def test_a_stop_that_is_not_a_card_close_stays_a_stop(screen, text):
    blk, tags = _decide(text, brief=_brief("musica:stop", 0.95, canvas="neither"))
    assert blk["action"] == "music" and blk["music_req"]["action"] == "stop", (text, blk)
    assert not tags


def test_the_voice_close_backstop_is_not_held_by_the_stop_it_replaces(screen):
    req = {"v": {"action": "stop", "query": ""}}
    assert CC.music_keeps_its_turn(req, "cierra la música") is False and req["v"] is None
    req = {"v": {"action": "stop", "query": ""}}
    assert CC.music_keeps_its_turn(req, "apaga la música") is True and req["v"]["action"] == "stop"
    assert CC.music_keeps_its_turn({"v": None}, "cierra la música") is False


def test_both_channels_call_the_one_helper():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[4]
    for rel, needle in (("nucleo/flash/probe_mirrors.py", "_card_close.complete_canvas_mirror"),
                        ("nucleo/flash/post_stream_lanes.py", "_card_close.music_keeps_its_turn"),
                        ("nucleo/flash/post_stream_lanes.py", "_card_close.verdict_unless_named"),
                        ("nucleo/flash/direct_action.py", "_ccl.verdict_unless_named"),
                        ("nucleo/flash/player_control.py", "_card_close.player_close")):
        assert needle in (root / rel).read_text(encoding="utf-8"), (rel, needle)
