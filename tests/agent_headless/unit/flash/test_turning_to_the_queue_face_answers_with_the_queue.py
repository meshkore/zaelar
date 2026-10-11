"""Turning the video card to its queue answers with the queue, never with the face's name (2026-10-11, ES 2 and 7).

`build-a-video-playlist-from-links` (ES): «¿qué hay en la lista?» and «revisa la cola» ran `show_tab {tab: cola}` over
a two-video list. The op answered `{"ok": true, "tab": "cola"}`, the text channel composed the reply from that answer
(`widget_data_turn.answer_in_words`), and the reply was «la pestaña de la cola aparece vacía» — the add HAD persisted
(the store's own history shows both rows a second after it). A face that lists the queue answers with it, and a
bare face name is an ack, not an answer.

Disarm: with `tab_answer.result` returning {} the first test goes red; with "tab" taken out of
`data_ops._ACK_KEYS` the second goes red.
"""
from __future__ import annotations

from nucleo.flash import data_ops
from widgets.youtube import data as _data  # noqa: F401 — the package loads through `data` (it imports `actions`)
from widgets.youtube import actions as A

RICK = {"videoId": "dQw4w9WgXcQ", "title": "Rick Astley - Never Gonna Give You Up", "channel": "Rick Astley"}
PSY = {"videoId": "9bZkp7q19f0", "title": "PSY - GANGNAM STYLE M/V", "channel": "officialpsy"}


def test_the_queue_face_answers_with_every_row_and_marks_the_refused_one(monkeypatch):
    monkeypatch.setattr(A._d.store, "save", lambda *a, **k: None)
    db = {"list": [RICK, PSY], "pos": 0, "blocked_videos": [{"videoId": PSY["videoId"]}]}
    r = A._a_show_tab("show_tab", {"tab": "cola"}, db)
    q = r["result"]["queue"]
    assert r["result"]["total"] == 2 and [x["title"] for x in q] == [RICK["title"], PSY["title"]]
    assert q[0].get("current") is True and "cannot_play_here" in q[1] and "cannot_play_here" not in q[0]
    assert data_ops.answer_of(r) == {"result": r["result"]}


def test_a_face_that_shows_no_queue_answers_nothing():
    assert data_ops.answer_of({"ok": True, "tab": "subs"}) == {}
