"""V2-781 — the same appointment, said twice in two wordings, is ONE row.

Measured on `demo-initialization__us` (2026-10-10 20:11): the INIT names Pixel's vet visit twice on purpose (the pet
section, then the calendar section). The agenda came out with «Veterinario de Pixel» AND «Pixel — veterinarian»,
both 2026-11-20 16:00-17:00, each with its own notice. The same-meeting rule compared words exactly, so a
translation read as two disjoint titles. At the same instant, a cognate wording or a shared proper noun over the
same full slot is the same commitment.
"""
import pytest

from widgets.agenda import data as agenda


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)


def _meetings():
    return agenda.load_db().get("meetings", [])


def _add(title, date="2099-11-20", start="16:00", end="17:00"):
    p = {"title": title, "date": date, "startTime": start}
    if end:
        p["endTime"] = end
    agenda.apply_action("add_meeting", p)


def test_the_measured_vet_visit_lands_once_with_one_notice():
    """THE case, verbatim from the run."""
    _add("Veterinario de Pixel")
    _add("Pixel — veterinarian")
    rows = _meetings()
    assert len(rows) == 1, [m.get("title") for m in rows]
    assert sum(1 for m in rows if m.get("reminder_id")) <= 1


def test_a_cognate_wording_is_the_same_meeting_even_without_an_end():
    a = {"title": "Dentista de los niños", "date": "2099-09-08", "startTime": "15:00"}
    c = {"title": "Dentist", "date": "2099-09-08", "startTime": "15:00"}
    assert agenda._is_same_meeting(c, a) and agenda._is_same_meeting(a, c)
    p = {"title": "Producto: revisión", "date": "2099-09-08", "startTime": "15:00"}
    assert agenda._is_same_meeting(p, {"title": "Product revision", "date": "2099-09-08", "startTime": "15:00"})
    # short words never stretch: «call»/«calle» are not one word
    assert not agenda._is_same_meeting({"title": "Call", "date": "x", "startTime": "1"},
                                       {"title": "Calle", "date": "x", "startTime": "1"})


def test_a_shared_name_over_the_same_full_slot_is_the_same_meeting():
    _add("Peluquería de Pixel")
    _add("Pixel grooming")
    assert len(_meetings()) == 1


def test_a_shared_name_at_a_different_hour_is_two_meetings():
    _add("Veterinario de Pixel", start="10:00", end="11:00")
    _add("Pixel — veterinarian", start="16:00", end="17:00")
    assert len(_meetings()) == 2


def test_a_shared_name_without_the_same_end_is_not_merged():
    """The proper-noun widening needs the FULL slot: two rows that only share a start are not proven one."""
    a = {"title": "Lunch with Laura", "date": "2099-10-15", "startTime": "13:00", "endTime": "14:00"}
    b = {"title": "Call with Laura", "date": "2099-10-15", "startTime": "13:00"}
    assert not agenda._is_same_meeting(a, b)


def test_two_different_meetings_in_one_slot_both_land():
    """A double-booked slot with nothing in common stays the user's business."""
    _add("ZAELAR weekly review")
    _add("Meshcore architecture")
    assert len(_meetings()) == 2


def test_an_opening_capital_alone_is_not_a_name():
    """«Product meeting» and «Pixel grooming»: a title's first word is capitalised by grammar, not by name."""
    a = {"title": "Shopping list", "date": "2099-10-15", "startTime": "13:00", "endTime": "14:00"}
    b = {"title": "Shopping with Laura", "date": "2099-10-15", "startTime": "13:00", "endTime": "14:00"}
    c = {"title": "Gym session", "date": "2099-10-15", "startTime": "13:00", "endTime": "14:00"}
    d = {"title": "Gym with Laura", "date": "2099-10-15", "startTime": "13:00", "endTime": "14:00"}
    assert agenda._is_same_meeting(b, d), "«Laura» is a name in both"
    assert not agenda._is_same_meeting(a, c)
