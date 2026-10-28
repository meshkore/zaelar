"""A series with one day moved off it is still ONE reference: ending or removing it is never «which one?»
(refactor2710-99, use cases agenda-everyday-edits and its __us twin).

«This Tuesday the piano is at five» detaches that day (V2-770): the series skips it and a single appointment with
the SAME title holds the new hour. Afterwards «from December on there's no more piano» and «get rid of the piano
completely, the whole series» both came back as «Which one exactly?» (two «Abril's piano lesson»), glued to the
model's «Ending the piano series…», and the series was never cut.

The index named every appointment by its title (`field: title`, `id: title`), so the two rows were two candidates
with the SAME id — a reference that fills the same value whichever is picked. Which row the order touches is the
agenda's own decision (`from` / `whole` / `date` on the series), never the reference's. One title, one reference.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    from widgets import store
    from widgets.agenda import data as ad
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    monkeypatch.setattr(ad, "_today", lambda: "2026-11-02")
    ad.apply_action("add_meeting", {"title": "Abril's piano lesson", "date": "2026-11-03", "startTime": "17:00",
                                    "endTime": "18:00", "repeat": "weekly", "days": "tuesday", "until": "2027-01-31"})
    ad.apply_action("move_meeting", {"title": "Abril's piano lesson", "date": "2026-11-10", "newTime": "17:30"})
    return ad


def _piano_rows(ad) -> list[dict]:
    return [m for m in ad.load_db().get("meetings", []) if m.get("title") == "Abril's piano lesson"]


def test_the_moved_day_left_two_rows_with_one_title(agenda):
    rows = _piano_rows(agenda)
    assert len(rows) == 2 and sum(isinstance(m.get("repeat"), dict) for m in rows) == 1, rows


@pytest.mark.parametrize("action,ref,payload", [
    ("cancel_meeting", "the piano", {"whole": True}),
    ("cancel_meeting", "", {"title": "piano", "from": "2026-12-01"}),
    ("update_meeting", "piano", {"until": "2026-11-30"}),
    ("cancel_meeting", "", {"title": "Abril's piano lesson", "whole": True}),
])
def test_ending_or_removing_the_series_is_not_a_question(agenda, action, ref, payload):
    from widgets import refs
    res = refs.resolve("agenda", action, ref, dict(payload), order="from December on there's no more piano")
    assert res.ok, f"«which one?» over one series: {res.candidates}"


def test_cutting_the_series_cuts_the_series_not_the_moved_day(agenda):
    agenda.apply_action("update_meeting", {"title": "Abril's piano lesson", "until": "2026-11-30"})
    series = [m for m in _piano_rows(agenda) if isinstance(m.get("repeat"), dict)]
    assert [m["repeat"].get("until") for m in series] == ["2026-11-30"], _piano_rows(agenda)


def test_removing_the_whole_series_leaves_no_piano(agenda):
    agenda.apply_action("cancel_meeting", {"title": "Abril's piano lesson", "whole": True})
    assert _piano_rows(agenda) == []


def test_the_index_names_each_title_once(agenda):
    from widgets.agenda import index
    titles = [r["id"] for r in index.ref_index() if r.get("field") == "title"]
    assert titles.count("Abril's piano lesson") == 1, titles
