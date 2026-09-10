"""V2-652 — a missing hour is a FACT, never a slot for a default.

Measured live (session 7f77e2cc, 2026-09-10): the promise backstop wrote «la cita con la agencia
tributaria» with title+date and NO hour, `add_meeting` filled its `default="17:00"`, and the operator read
the invented afternoon slot as us copying his spoken «hoy tengo reunión a las cinco». His explicit «a las
once y media» then landed as a SECOND row (dedup keys on date+hour, and 17:00 ≠ 11:30) — «dos ítems» on his
screen, followed by «Quítalo inmediatamente».

The rules this file pins:
  · a write with no hour creates an ALL-DAY entry — 17:00 is never invented;
  · a TIMED add settles an existing all-day twin of the same day IN PLACE (one row, the dictated hour);
  · an all-day add over an already-timed twin adds nothing;
  · V2-473's refusal (no real field at all) still stands, now with a speakable `message`.
"""
import pytest

from widgets.agenda import data as agenda


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)


def _meetings():
    return agenda.load_db().get("meetings", [])


def test_a_write_with_no_hour_is_all_day_not_five_pm():
    """THE measured shape: the backstop's title+date write must not wear an invented afternoon."""
    agenda.apply_action("add_meeting",
                        {"title": "la cita con la agencia tributaria", "date": "2026-09-11"})
    ms = _meetings()
    assert len(ms) == 1
    assert ms[0].get("allDay") is True
    assert not ms[0].get("startTime"), "no hour was given, so no hour may exist"


def test_a_timed_add_settles_the_all_day_twin_instead_of_standing_beside_it():
    """The session's exact sequence: backstop first (no hour), the operator's 11:30 next → ONE row."""
    agenda.apply_action("add_meeting",
                        {"title": "la cita con la agencia tributaria", "date": "2026-09-11"})
    agenda.apply_action("add_meeting",
                        {"title": "Cita Agencia Tributaria", "date": "2026-09-11",
                         "startTime": "11:30"})
    ms = _meetings()
    assert len(ms) == 1, f"expected the twin settled in place, got {ms!r}"
    assert ms[0].get("startTime") == "11:30"
    assert not ms[0].get("allDay")


def test_an_all_day_add_over_an_already_timed_twin_adds_nothing():
    """The same pair in the OTHER order — the backstop may fire after the explicit add too."""
    agenda.apply_action("add_meeting",
                        {"title": "Cita Agencia Tributaria", "date": "2026-09-11",
                         "startTime": "11:30"})
    agenda.apply_action("add_meeting",
                        {"title": "la cita con la agencia tributaria", "date": "2026-09-11"})
    ms = _meetings()
    assert len(ms) == 1
    assert ms[0].get("startTime") == "11:30"


def test_two_hourless_twins_land_once():
    agenda.apply_action("add_meeting", {"title": "cita agencia tributaria", "date": "2026-09-11"})
    agenda.apply_action("add_meeting", {"title": "la cita con la agencia tributaria",
                                        "date": "2026-09-11"})
    assert len(_meetings()) == 1


def test_a_different_day_is_never_merged():
    """The counterweight: settlement is same-day only — an hour-less entry on Friday says nothing about
    the timed one on Saturday."""
    agenda.apply_action("add_meeting", {"title": "cita agencia tributaria", "date": "2026-09-11"})
    agenda.apply_action("add_meeting", {"title": "cita agencia tributaria", "date": "2026-09-12",
                                        "startTime": "11:30"})
    assert len(_meetings()) == 2


def test_a_disjoint_title_the_same_day_stays_its_own_meeting():
    """A double-booked day is the user's business, not ours to merge (V2-473 round 6's own boundary)."""
    agenda.apply_action("add_meeting", {"title": "cita agencia tributaria", "date": "2026-09-11"})
    agenda.apply_action("add_meeting", {"title": "dentista", "date": "2026-09-11",
                                        "startTime": "11:30"})
    assert len(_meetings()) == 2


def test_the_empty_refusal_still_stands_and_carries_a_speakable_message():
    """V2-473's gate, untouched — and the F1 half: `error` coaches the model, `message` is what the
    operator may hear, free of tool vocabulary."""
    res = agenda.apply_action("add_meeting", {})
    assert res.get("ok") is False
    assert "add_meeting" in res.get("error", "")
    msg = res.get("message", "")
    assert msg and "add_meeting" not in msg and "YYYY" not in msg
    assert not _meetings()
