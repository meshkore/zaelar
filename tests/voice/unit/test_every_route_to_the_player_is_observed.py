"""Every route to the player is observed by the one door that plays (V2-833 F4).

The voice tool (`play_music`) wrote a `music` event; the card's own `play` — the route the act repair takes when the
model said «te pongo X» without calling the tool — wrote none. Measured on a sandbox bench, 2026-11-01: the repaired
turns played, and nothing in the record said where the song went or who named it. The event now comes from
`connectors.music.control`, the door every route crosses, so it cannot depend on which route asked.

Disarm: drop `_observe` from `control` → red.
"""
from __future__ import annotations

from connectors import music
from connectors.music.base import MusicResult


def _capture(monkeypatch):
    seen = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, **kw: seen.append((kind, kw)))
    return seen


def test_a_play_through_the_door_writes_one_music_event_with_its_facts(monkeypatch):
    seen = _capture(monkeypatch)
    res = MusicResult(ok=True, provider="youtube", action="play")
    res.extra = {"placed": "page", "identified_by": "spotify"}
    monkeypatch.setattr(music, "_play", lambda q, u, p="": res)
    music.control("play", query="We Will Rock You Queen")
    ev = [kw for k, kw in seen if k == "music"]
    assert len(ev) == 1, f"one act, one event — got {len(ev)}"
    x = ev[0]["extra"]
    assert ev[0]["text"] == "We Will Rock You Queen"
    assert (x["provider"], x["ok"], x["placed"], x["identified_by"]) == ("youtube", True, "page", "spotify")


def test_the_cards_play_crosses_the_same_door(monkeypatch):
    seen = _capture(monkeypatch)
    monkeypatch.setattr(music, "_play", lambda q, u, p="": MusicResult(ok=False, action="play", reason="no_track"))
    from widgets.musica import data
    data.apply_action("play", {"query": "Corazón partío Alejandro Sanz"})
    ev = [kw for k, kw in seen if k == "music"]
    assert ev and ev[0]["extra"]["reason"] == "no_track", "the card's play left no record of what happened"
