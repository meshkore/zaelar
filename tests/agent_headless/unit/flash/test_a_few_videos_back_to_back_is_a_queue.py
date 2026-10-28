"""«Put on a few videos, back to back» reaches the player as a QUEUE, and the queue is what a read answers (V2-781).

Measured in `la-cola-de-video-con-palabras-imprecisas__us` (2026-10-10 20:11), text channel:
  · turn 0 — «Put on a few Maradona videos, I want to watch them back to back.» The reply said «I'll line up a few
    Maradona videos for you and start the first one»; the ops were `load` alone. `play_video.action` had two
    values, ONE video (`play` → load) or SEVERAL TO CHOOSE FROM (`list` → search, nothing plays), so the request had
    no value of its own and the model took `play`. «The second one» then failed on turns 1, 2 and 4.
  · turn 11 — «just tell me what's in the queue right now» → «the queue just has one video», over a card holding two.
    `read_widget` read the player's digest — the search band and a playback notice («X could not play, Y was put in
    its place») — and never the queue rows, which the player publishes only through `ref_index`.
"""
import asyncio

import pytest

from nucleo.flash import router
from nucleo.flash import video_turn as VT


@pytest.fixture
def rail(monkeypatch):
    seen = {}

    async def _brain_action(wid, action, payload):
        seen.update({"wid": wid, "action": action, "payload": payload})
        return {"ok": True, "videoId": "AAAAAAAAAA1", "title": "Maradona best goals",
                "queued": ["Maradona best goals", "Maradona in Napoli", "Maradona 1986", "Maradona skills"],
                "count": 4}
    import widgets.server_api as _sa
    monkeypatch.setattr(_sa, "brain_action", _brain_action)
    return seen


def test_the_tool_offers_the_queue_and_both_channels_decide_it_once():
    pv = next(t for t in router.TOOLS if t["function"]["name"] == "play_video")["function"]
    assert "queue" in pv["parameters"]["properties"]["action"]["enum"]
    assert VT.normalize_action("queue") == "queue"
    assert VT.normalize_action("play") == "play" and VT.normalize_action(None) == "play"
    assert VT.normalize_action("list") == "list" and VT.normalize_action("search") == "list"
    assert VT.voice_dispatch("queue")[0] == "queue_search", "the voice provider must reach the same data-op"
    assert VT.voice_dispatch("play")[0] == "load", "a single «play X» still loads one video"
    assert router.decide("play_video", {"query": "x", "action": "queue"}).payload["action"] == "queue"


def test_a_failed_queue_is_said_as_a_failure(rail, monkeypatch):
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: "en", raising=False)
    said = VT.spoken_for({"executed": "play_video", "accion": "queue", "ok": False, "message": ""}, "Done.")
    assert said.startswith("I couldn't") and "Done." not in said


def test_the_queue_read_carries_the_queue_rows_beside_the_notice(monkeypatch, tmp_path):
    from widgets import store
    from widgets.youtube import data as yt
    from nucleo.flash import widget_read
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    db = yt._load()
    db["list"] = [{"videoId": "OOOOOOOOOO1", "title": "Opus - Live Is Life"},
                  {"videoId": "NNNNNNNNNN2", "title": "Maradona - Anubiis x Hades 66"}]
    db["videoId"], db["title"], db["pos"] = "NNNNNNNNNN2", "Maradona - Anubiis x Hades 66", 1
    db["blocked_notice"] = {"kind": "swapped", "from": "Opus - Live Is Life", "to": "Maradona - Anubiis x Hades 66"}
    store.save("youtube", db)
    block = widget_read.read("youtube")
    assert "AVISO DEL REPRODUCTOR" in block, "the notice still rides"
    assert "items ahora:" in block and block.count("Opus - Live Is Life") >= 2, \
        "the queue's rows ride beside the notice — the notice alone read as «one video left»"


def _typed_queue_turn(monkeypatch) -> dict:
    from tests.brain import harness as H
    with H.Isolated("en"):
        from nucleo.cli import turn
        monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: "en", raising=False)
        H.RecordedModel.load({"say": "I'll line up a few Maradona videos for you and start the first one.",
                              "tools": [{"name": "play_video",
                                         "args": {"query": "Maradona videos", "action": "queue"}}]})
        try:
            res = asyncio.run(turn.run_turn("Put on a few Maradona videos, I want to watch them back to back.",
                                            sid="test-video-queue-turn", ingest=False, execute=True))
        finally:
            turn.reset("test-video-queue-turn")
    return res


def test_a_typed_turn_asking_for_a_few_videos_builds_the_queue(rail, monkeypatch):
    """The whole turn (the voice turn, typed): nothing between the model's call and the widget may turn the queue
    into a load."""
    res = _typed_queue_turn(monkeypatch)
    assert res["ok"] is True, res
    assert rail.get("action") == "queue_search", f"the queue must reach the player, got {rail}"


@pytest.mark.xfail(reason="refactor2710-03: the mouth speaks the verdict", strict=True)
def test_the_typed_queue_turn_names_what_plays(rail, monkeypatch):
    """The promise to line them up is backed by what plays, said in the turn (V2-469). The voice turn's words stream
    before the player answers; saying what plays is the mouth saying the verdict — the 03's class."""
    res = _typed_queue_turn(monkeypatch)
    assert "Maradona best goals" in str(res.get("reply") or "")
