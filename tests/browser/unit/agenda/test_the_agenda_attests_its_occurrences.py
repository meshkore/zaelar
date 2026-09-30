"""V2-776 L2 · The agenda attests OCCURRENCES, not only rows (node 4.234).

A series is ONE row in the store (V2-769) and the calendar draws its occurrences (`recur.expand`). A spec
«a meeting titled X on date Y» read through `rows` saw the row and not the day: «is there a review next
Tuesday?» was False over a weekly review that IS there. `occurrences` is the expanded view as a read-only
collection; `meetings` stays the row collection every write goes through.
"""
import datetime as _dt

import pytest


def _day(offset: int) -> str:
    return (_dt.date.today() + _dt.timedelta(days=offset)).isoformat()


@pytest.fixture
def ag(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data, gcal
    monkeypatch.setattr(gcal, "svc", lambda: None)
    db = data.load_db()
    # a weekly series starting today, and a plain appointment in three days
    db["meetings"] = [
        {"id": "m1", "title": "ZAELAR weekly review", "date": _day(0), "startTime": "09:00", "endTime": "09:30",
         "repeat": {"freq": "weekly", "days": [_dt.date.today().weekday()], "until": ""}},
        {"id": "m2", "title": "Catch up with Rowan", "date": _day(3), "startTime": "16:30", "endTime": "17:15"}]
    store.save(data.WIDGET_ID, db)
    return data


def test_a_series_is_one_row_and_several_occurrences(ag):
    from widgets import rows
    assert len(rows.select("agenda", "meetings", {"title~": "weekly review"})) == 1
    occ = rows.select("agenda", "occurrences", {"title~": "weekly review"})
    assert len(occ) >= 4 and any(o["date"] == _day(7) for o in occ)
    assert rows.ops_for("agenda", "occurrences") == ("list",)


def test_a_spec_on_a_day_reads_the_occurrence(ag):
    from nucleo import verify
    assert verify.check({"widget": "agenda", "collection": "occurrences", "where": {"title~": "review", "date": _day(7)}}) is True
    assert verify.check({"widget": "agenda", "collection": "occurrences", "where": {"title~": "Rowan", "date": _day(3)}}) is True
    assert verify.check({"widget": "agenda", "collection": "occurrences", "where": {"title~": "Rowan", "date": _day(4)}}) is False
