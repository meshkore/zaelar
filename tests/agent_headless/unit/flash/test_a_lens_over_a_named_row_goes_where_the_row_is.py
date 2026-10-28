"""A lens over a row his words name goes where the ROW is, never where a sentence put it (demo pass 140, R2).

«and when does anna's vacation start? show me in the calendar» — the model said «tomorrow, 20 October», the promise
repair turned that reply into `agenda:show_day {day: 2026-10-20}`, and the read of that empty day «corrected» the
answer into «her vacation hasn't started yet». The row «Anna vacation» (2026-12-20) was on file. A lens the card
declares `by_row` runs as the card's item view on the one row his words name; the day comes off the data.
"""

from widgets import refs, row_lens

ROWS = [{"id": t, "label": t, "field": "title", "hint": h} for t, h in [
    ("ZAELAR weekly review", "appointment 2026-10-20 09:00"), ("Product meeting", "appointment 2026-10-20 11:00"),
    ("Catch up with Rowan", "appointment 2026-10-20 16:30"), ("Call with accountant", "appointment 2026-10-22 10:00"),
    ("Anna vacation", "appointment 2026-12-20"), ("Viaje a Roma", "cita 2027-03-04"),
    ("Lunch with Laura", "appointment 2026-10-25 13:00"), ("Lunch with Lars", "appointment 2026-10-26 13:00")]]


def _lens(monkeypatch, said, action="show_day", payload=None, wid="agenda"):
    monkeypatch.setattr(refs, "_ref_index", lambda w: ROWS)
    return row_lens.retarget(wid, action, dict(payload or {"day": "2026-10-20"}), said)


def test_the_named_row_decides_the_day_not_the_sentence(monkeypatch):
    assert _lens(monkeypatch, "and when does anna's vacation start? show me in the calendar") == \
        ("open_meeting", {"title": "Anna vacation"})


def test_the_same_in_the_other_language(monkeypatch):
    assert _lens(monkeypatch, "¿cuándo es el viaje a Roma? enséñamelo en la agenda", payload={"day": "mañana"}) == \
        ("open_meeting", {"title": "Viaje a Roma"})


def test_a_day_with_no_row_named_stays_a_day(monkeypatch):
    for said in ("johnny show me what i've got tomorrow", "what's on my plate tomorrow", "show me the week"):
        assert _lens(monkeypatch, said, payload={"day": "tomorrow"}) == ("show_day", {"day": "tomorrow"}), said


def test_two_rows_his_words_could_mean_leave_the_lens_alone(monkeypatch):
    assert _lens(monkeypatch, "show me the lunch with la")[0] == "show_day"


def test_a_lens_that_declares_nothing_is_never_redirected(monkeypatch):
    # `find_free` answers a question of its own; `imagenes:show` takes a subject that may share a row's words.
    assert _lens(monkeypatch, "find me a free hour around the call with the accountant", "find_free",
                 {"date": "tomorrow"}) == ("find_free", {"date": "tomorrow"})
    assert _lens(monkeypatch, "show me anna vacation photos", "show", {"query": "anna vacation"}, wid="imagenes") == \
        ("show", {"query": "anna vacation"})
