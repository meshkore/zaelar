"""«No encontró» y «encontró y no lo entregó» son dos fallos distintos, y solo uno era verdad.

Three rounds of `hotel-under-15-days` all scored 2/5 with three different stories underneath: one where the
worker probed its own CLI and never searched, one where it navigated Booking with perfect parameters and
extracted «Exe Sevilla Macarena, 65 €» with a URL — which the conversation never mentioned — and one where it
spent the round asking permission to clear a Booking filter. Same number, three mechanisms. Reading three
streams by hand was the only way that got noticed, and the judge had been writing "se quedó en cero resultados"
about the round that found a real hotel.

So the report carries what the browser extracted and whether any of it was SAID. The gap between those two is
the defect the case is about.
"""
from __future__ import annotations

import json
import sqlite3

from tests.use_cases.e2e.agent import judge as J, verify as V

_AD = {"title": "Experiencia Premium en el Teatro Flamenco Sevilla", "price": "€ 25", "url": "https://b/x"}
_HOTEL = {"title": "Exe Sevilla Macarena", "price": "65 €", "url": "https://g/y"}


def _db(tmp_path, rows):
    p = tmp_path / "sandbox.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_ms INTEGER, topic TEXT, "
                "kind TEXT, label TEXT, payload TEXT)")
    for ts, label, payload in rows:
        con.execute("INSERT INTO events (ts_ms, topic, kind, label, payload) VALUES (?,?,?,?,?)",
                    (int(ts), "observer", "navegador", label, json.dumps(payload)))
    con.commit()
    con.close()
    return p


def test_it_keeps_ALL_the_results_not_just_the_first(tmp_path):
    """The first Booking extraction came back as an ad and the real hotel arrived later. Keeping only the first
    would report the junk as "what the worker found" and hide that it eventually got there."""
    db = _db(tmp_path, [(1000, "navigate", {"text": "https://booking"}),
                        (2000, "🧭 resultados", {"text": json.dumps([_AD])}),
                        (3000, "🧭 resultados", {"text": json.dumps([_HOTEL])})])
    o = V.worker_outcome(db)
    assert o["navigations"] == 1 and o["extractions"] == 2 and o["n_found"] == 2
    assert [f["title"] for f in o["found"]] == [_AD["title"], _HOTEL["title"]]


def test_delivered_is_TRUE_when_the_hotel_was_said(tmp_path):
    found = [_AD, _HOTEL]
    tr = [{"who": "zaelar", "text": "Te propongo el Exe Sevilla Macarena por 65 € la noche."}]
    assert V.was_delivered(found, tr) is True


def test_delivered_is_FALSE_when_the_turn_said_it_was_still_waiting(tmp_path):
    """The measured case: found at 19:45:29, and at 19:45:45 the turn said "sigo pendiente"."""
    assert V.was_delivered([_HOTEL], [{"who": "zaelar", "text": "Sigo pendiente y te aviso."}]) is False


def test_nothing_found_is_NOT_the_same_as_nothing_delivered(tmp_path):
    """`None` keeps the two apart: a round that extracted nothing cannot be accused of hiding a result."""
    assert V.was_delivered([], [{"who": "zaelar", "text": "x"}]) is None
    assert V.was_delivered(None, []) is None


def test_only_ZAELAR_counts_as_having_said_it():
    """Sensitivity: the tester's own turns are in the transcript too, and a driver that pasted the results once
    already made a round look delivered when nothing was."""
    tr = [{"who": "tester", "text": "he visto el Exe Sevilla Macarena por ahí"}]
    assert V.was_delivered([_HOTEL], tr) is False


def test_the_judge_is_told_it_was_HANDED_the_result_and_did_not_say_it():
    """The accusation now rests on what the NOTE carried, because that is what the turn could act on."""
    txt = J.mechanism_facts({"worker_outcome": {"found": [_HOTEL], "n_found": 1, "delivered": False,
                                                "navigations": 2, "extractions": 2},
                             "offered": {"notes": 1, "n_offered": 1, "titles": ["Exe Sevilla Macarena"]}})
    assert "SE LO DIMOS Y NO LO DIJO" in txt
    assert "Exe Sevilla Macarena" in txt
    assert "fallo de conducta" in txt


def test_and_the_SAME_scrape_is_NOT_a_behaviour_defect_when_the_note_carried_no_name():
    """Sensitivity, and the reason this split exists: on 2026-08-20 the browser scraped three real 99 EUR
    monitors while the note carried three nameless category links. Scoring that as withholding blames a turn
    that described its input accurately."""
    txt = J.mechanism_facts({"worker_outcome": {"found": [_HOTEL], "n_found": 1, "delivered": False,
                                                "navigations": 2, "extractions": 2},
                             "offered": {"notes": 2, "n_offered": 3, "titles": ["799€", "200€", "200€"]}})
    assert "NO ES CULPA DE ZAELAR" in txt
    assert "DIJO LA VERDAD sobre lo que recibió" in txt
    assert "SE LO DIMOS Y NO LO DIJO" not in txt


def test_an_UNMEASURED_note_exonerates_nobody():
    """No `offered` key means the reading did not run. Absence of measurement is not evidence of an empty note."""
    txt = J.mechanism_facts({"worker_outcome": {"found": [_HOTEL], "n_found": 1, "delivered": False,
                                                "navigations": 2, "extractions": 2}})
    assert "NO ES CULPA DE ZAELAR" not in txt


def test_and_told_when_the_extraction_itself_came_back_empty():
    """A different defect with a different owner: nothing to hide, the extractor brought nothing."""
    txt = J.mechanism_facts({"worker_outcome": {"found": [], "n_found": 0, "delivered": None,
                                                "navigations": 3, "extractions": 2}})
    assert "navegó 3 vez/veces" in txt
    assert "fallo del mecanismo de extracción" in txt


def test_and_credits_a_result_that_WAS_delivered():
    txt = J.mechanism_facts({"worker_outcome": {"found": [_HOTEL], "n_found": 1, "delivered": True,
                                                "navigations": 1, "extractions": 1}})
    assert "lo ENTREGÓ" in txt
