"""V2-208 — one obligation, two rows in the agenda.

Measured on `remember-and-remind-deadline` (2026-08-20 14:39), read from the sandbox's own `state.json`:

    meetings = [«renovar el seguro del coche» 2026-08-27,
                «Renovar el seguro del coche» 2026-08-27]

The difference is an article and a capital letter. V2-194 fixed exactly this shape for the BACKSTOP
(`router_guards.already_in_agenda`, consulted before dispatching) and the model's OWN `add_meeting` had no such
guard: two turns, two data-ops, nobody comparing. So the guard belongs next to the WRITE, where every writer —
model, backstop, worker bridge, the card's own button — passes through it.

A duplicated reminder is heard once; a duplicated appointment is SEEN, and it stays there until somebody deletes
it by hand.
"""
import pytest

from widgets.agenda import data as agenda


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)


def _meetings():
    return agenda.load_db().get("meetings", [])


def _add(title, date="2026-08-27", start="17:00"):
    agenda.apply_action("add_meeting", {"title": title, "date": date, "startTime": start})


def test_the_measured_duplicate_lands_once():
    """THE case, verbatim from the run."""
    _add("renovar el seguro del coche")
    _add("Renovar el seguro del coche")
    assert len(_meetings()) == 1


def test_punctuation_and_accents_do_not_make_it_a_different_meeting():
    _add("Renovar el seguro del coche")
    _add("renovar seguro coche.")
    assert len(_meetings()) == 1


def test_the_same_title_at_a_DIFFERENT_hour_is_a_different_meeting():
    """Two viewings of the same flat are two meetings. This is why the hour is part of the key: a duplicate that
    is silently dropped is worse than one that is visible."""
    _add("visita piso", start="10:00")
    _add("visita piso", start="17:00")
    assert len(_meetings()) == 2


def test_the_same_title_on_a_DIFFERENT_day_is_a_different_meeting():
    _add("renovar el seguro del coche", date="2026-08-27")
    _add("renovar el seguro del coche", date="2026-09-27")
    assert len(_meetings()) == 2


def test_two_genuinely_different_meetings_both_land():
    _add("renovar el seguro del coche")
    _add("cena con Marta")
    assert len(_meetings()) == 2


def test_a_title_made_only_of_articles_never_matches_anything():
    """`_title_key` empties out on «el», «la»… and an empty key matching an empty key would collapse every
    junk-titled entry into one. Two bad entries are a symptom; one is a symptom we hid."""
    _add("el")
    _add("la")
    assert len(_meetings()) == 2


def test_a_title_contained_in_the_other_at_the_same_instant_is_the_same_meeting():
    """V2-473 round 6 (the PASS round's remaining [media]): «Llevar a los niños al dentista» and
    «Dentista niños», same day and hour, landed as two meetings with two reminders. At the SAME
    date+time, one title's meaningful tokens being a subset of the other's is the same commitment —
    nobody has two distinct appointments at the same instant whose names contain each other."""
    from widgets.agenda import data as ag
    a = {"title": "Llevar a los niños al dentista", "date": "2099-09-08", "startTime": "15:00"}
    b = {"title": "Dentista niños", "date": "2099-09-08", "startTime": "15:00"}
    assert ag._is_same_meeting(a, b) and ag._is_same_meeting(b, a)
    # different instant → two meetings, contained title or not
    c = {"title": "Dentista niños", "date": "2099-09-08", "startTime": "10:00"}
    assert not ag._is_same_meeting(a, c)
    # same instant but DISJOINT titles stays two meetings (a double-booked hour is the user's business)
    d = {"title": "Peluquería", "date": "2099-09-08", "startTime": "15:00"}
    assert not ag._is_same_meeting(a, d)
