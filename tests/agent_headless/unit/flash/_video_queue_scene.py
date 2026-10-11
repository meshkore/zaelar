"""The video queue of the 2026-10-11 regression sweep (video-queue use case, ES + EN), shared by nodes 2.450-2.452.

Titles verbatim from the two reports; the queue is written to a temporary widget store, never the operator's."""
from __future__ import annotations

import threading

import pytest

from widgets import store
from widgets.youtube import data as yt

#: The EN run's queue after «skip the first» and «drop the last one».
EN_QUEUE = ["🇦🇷 Diego Maradona’s Top 5 Goals | FIFA World Cup", "Los Goles Más Humillantes de Diego Maradona",
            "Maradona The Most Creative and \\", "Diego Maradona - 20 mejores goles"]
#: The ES run's queue at the reorder turn.
ES_QUEUE = ["Diego Maradona 👑 Prime Argentina Skills, Goals, Dribbling & Tricks", "Maradona The Most Creative and \\",
            "Diego Maradona - 20 mejores goles"]

EN_SAID = "actually move that one before the other... no wait, the third one before the second"
EN_CLAIM = ("Done — «Maradona The Most Creative and \\» is now ahead of «Los Goles Más Humillantes de Diego Maradona». "
            "By the way, since you're clearly into Maradona, what's your name?")
ES_SAID = "Vale. Ahora cambia el orden: el de skills ponlo antes que el de creative, que me apetece más regates."


@pytest.fixture
def queue(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))

    def _put(titles, pos=0):
        db = yt._load()
        db["list"] = [{"videoId": f"VID{i:08d}", "title": t, "channel": f"ch{i}"} for i, t in enumerate(titles)]
        db["pos"] = pos
        store.save(yt.WID, db)
    return _put


def titles() -> list[str]:
    return [it["title"] for it in yt._load()["list"]]


def brief(answers: dict, *, open_ids=("youtube",)) -> dict:
    """A brief handle in the real shape `jev.ask_many` returns (the builder of nodes 2.68/2.72)."""
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids),
            "result": {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}}
