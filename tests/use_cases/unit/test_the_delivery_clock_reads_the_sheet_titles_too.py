"""V2-469 · the delivery clock must match against the SHEET's titles, not only the pushed notes.

`delivery_lag_s` is the ONLY clock the judge is allowed to use for retention verdicts (rubric rule 2,
V2-300). It was computed by matching `offered.titles` — the titles pushed to the brain by note — against
zaelar's turns. Measured in `find-videos-on-a-topic-no-ai-slop` (2026-08-28 22:11): the worker wrote 4
named rows straight into the sheet and pushed NO note, so `offered.titles` was empty, no head ever
matched, and `delivery_lag_s` came out null — while zaelar named «Curso Completo para PODAR…» one turn
(62 s) after the rows landed. The judge, left with the ambiguous `after_last_turn_s: -252.7`, filed
[alta] «retuvo 4 minutos» over a delivery that took one turn.

A clock that only ticks on one of the delivery channels is a clock that mostly doesn't run — same shape
as V2-355's strict-clock lesson, one field over.
"""
from tests.use_cases.e2e.agent import verify as V

# The real round, verbatim: sheet titles as the worker wrote them, zaelar's naming turn as spoken.
SHEET_TITLES = ["Sanear un olivo en maceta", "Curso completo para podar un olivo",
                "Cómo PODAR un OLIVO paso a paso", "Poda del olivo paso a paso"]
NAMING_TURN = ('Voy sacando ya candidates con nombre y canal real: por ejemplo "Curso Completo para '
               'PODAR CORRECTAMENTE un OLIVO" (regla de oro del productor en YouTube) y el canal Jardinatis')
TRANSCRIPT = [
    {"who": "tester", "text": "¿Ya tienes los títulos o no?", "at": 100.0},
    {"who": "zaelar", "text": "Sigo con ello.", "at": 105.0},
    {"who": "zaelar", "text": NAMING_TURN, "at": 237.6},
]


def test_the_measured_round_gets_its_clock_back():
    """Offered empty (no note was pushed) + sheet titles present → the naming turn is found."""
    at = V.delivery_said_at(TRANSCRIPT, SHEET_TITLES)
    assert at == 237.6 * 1000.0


def test_a_title_only_in_the_notes_still_matches():
    """The note channel keeps working: the fix is a union, not a replacement."""
    tr = [{"who": "zaelar", "text": "Tienes el Fender Stratocaster por 300€.", "at": 50.0}]
    assert V.delivery_said_at(tr, ["Fender Stratocaster American"]) == 50000.0


def test_no_naming_means_no_clock_not_a_fabricated_one():
    """Nothing named → None. A made-up instant here would manufacture the very verdict this exists to kill."""
    tr = [{"who": "zaelar", "text": "Sigo con ello, te aviso.", "at": 50.0}]
    assert V.delivery_said_at(tr, SHEET_TITLES) is None


def test_tester_turns_never_tick_the_clock():
    """The tester quoting a title back is not zaelar delivering it."""
    tr = [{"who": "tester", "text": NAMING_TURN, "at": 60.0},
          {"who": "zaelar", "text": "Sigo con ello.", "at": 70.0}]
    assert V.delivery_said_at(tr, SHEET_TITLES) is None


def test_run_feeds_the_clock_both_sources():
    """Wiring guard: run.py must hand the clock the union of note titles and sheet titles."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/run.py").read_text(encoding="utf-8")
    assert "delivery_said_at" in src, "run.py no longer uses the extracted clock"
    seg = src.split("delivery_said_at", 1)[1][:400]
    assert "titles" in seg and "sh" in seg
