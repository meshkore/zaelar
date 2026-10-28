"""Node 2.599 — a queue edit (`add_results`, `remove`, `clear_list`) owes what the queue HOLDS now, read from the card.

`find-videos-on-a-topic-no-ai-slop` (2026-10-14): «Hecho.» over three videos never added (ES) and «Done.» over a queue
still holding the emoji video he had dropped (EN). The transport receipt read adds only, by count; now a removal owes
it too, and three rows or fewer are named — the reply can only claim what the card holds after the op.

Disarm: drop `REMOVES` from the receipt's condition → the removal tests go red.
"""
from __future__ import annotations

import pytest

from i18n import langs
from nucleo.turn import reply_receipts as RR


def _owed(said, ops, lang=None):
    out = RR.player_owed(said, ops, lang)
    return out[0].said if out else ""


async def _settled(said, ops, lang=None):
    out = await RR.player(said, ops, lang)
    return out[0].said if out else ""

A, B, C = ({"title": t} for t in ("How to Prune an Olive Tree", "Tutorial how to prune", "Podar los olivos"))


@pytest.fixture
def queue(monkeypatch):
    from widgets import store
    db = {"list": [], "pos": -1}
    monkeypatch.setattr(store, "load", lambda wid, *a, **k: dict(db) if wid == "youtube" else {})
    return db


def test_a_removal_names_what_is_left(queue):
    queue["list"] = [A, B]
    assert _owed("Done.", [("youtube", "remove")], lang=langs.spec("en")) == \
        "The queue now has 2: «How to Prune an Olive Tree» and «Tutorial how to prune»."


def test_an_emptied_queue_says_so(queue):
    assert _owed("Hecho.", [("youtube", "clear_list")], lang=langs.spec("es")) == "La cola se ha quedado vacía."


def test_three_added_rows_are_named_and_many_are_counted(queue):
    queue["list"] = [A, B, C]
    assert _owed("Hecho.", [("youtube", "add_results")], lang=langs.spec("es")) == \
        "La cola tiene ahora 3: «How to Prune an Olive Tree», «Tutorial how to prune» y «Podar los olivos»."
    queue["list"] = [A, B, C, A]
    assert _owed("Hecho.", [("youtube", "add_results")], lang=langs.spec("es")) == "La cola tiene ahora 4."
    assert _owed("Hecho, ya hay 4.", [("youtube", "add_results")], lang=langs.spec("es")) == ""
