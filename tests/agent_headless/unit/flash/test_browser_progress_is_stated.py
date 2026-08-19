"""V2-145 (`book-hotel-night-known__es`) — the brain narrated what the browser «was doing» from the clock.

The mechanism report for that very task read `status=working url= events=[] n_search_events=0`: the task had
opened NOTHING. And zaelar said «lleva unos 2 minutos abierto en la página» and, six turns later, «todavía
interactuando». The elapsed time was true; everything else in those sentences was invented.

Measured before touching anything: the NAVEGADOR line of `live_state` carried the task's GOAL and nothing about
what it had done. So «¿cómo va?» had only the seconds to answer with, and seconds are not a description of an
activity. Same remedy as `silent_s` in V2-131, one layer down — the truth already existed in
`widgets/navegador/tasks.py` and simply never reached the prompt.

Second finding of the same run, and a self-inflicted one: the case scores «pararse en el muro DICIÉNDOLO» as the
top mark, and the hotel entry of the site catalog never mentioned that closing a booking needs an account and a
card. The two categories added later this week (`event_tickets`, `local_business`) did say it; the three that
predated them did not. Now every transactional category states its wall, and there is a test that keeps it that
way.
"""
from __future__ import annotations

import pytest

from nucleo.flash import prompt
from nucleo.flash import site_catalog as sc


def _nav_line(live: str) -> str:
    return next((l for l in live.splitlines() if l.startswith("NAVEGADOR")), "")


@pytest.fixture
def one_browser_task(monkeypatch):
    from widgets.navegador import tasks as nt

    def _install(url="", steps=0):
        monkeypatch.setattr(nt, "active_summaries",
                            lambda limit=3: [("t7", "reservar noche en el Hotel Palacio de la Merced")])
        monkeypatch.setattr(nt, "active_progress",
                            lambda limit=3: [{"id": "t7", "goal": "x", "url": url, "phase": "",
                                              "steps": steps, "awaiting_login": False}])
    return _install


def test_a_browser_task_with_no_report_says_THAT_and_not_that_nothing_happened(one_browser_task):
    """V2-152 corrects the wording V2-145 introduced here.

    An empty record is the absence of a REPORT, not the absence of work: measured on the `book-hotel` run, the
    worker was on Booking.com with the hotel name typed while this line told the operator nothing had been
    opened — so he stopped a task that was progressing. Saying «no news» keeps the honesty V2-145 was after;
    asserting «it has opened nothing» claims something about the world the record cannot support."""
    one_browser_task(url="", steps=0)
    line = _nav_line(prompt.live_state())
    assert "AÚN NO HA REPORTADO NINGÚN PASO" in line
    assert "NO HA ABIERTO NINGUNA PÁGINA" not in line


def test_and_it_never_pushes_the_operator_to_stop_a_silent_task(one_browser_task):
    """The measured harm was not the wording on its own: it was the abort it invited. «¿Paramos para revisar qué
    está pasando?» came straight after «sigo sin novedades», and the operator said yes."""
    one_browser_task(url="", steps=0)
    line = _nav_line(prompt.live_state())
    assert "sigue viva" in line
    assert "no significa que esté parada" in line


def test_a_browser_task_that_IS_working_says_where_and_how_far(one_browser_task):
    one_browser_task(url="https://www.booking.com/hotel/es/palacio", steps=4)
    line = _nav_line(prompt.live_state())
    assert "booking.com" in line
    assert "4 pasos dados" in line
    assert "AÚN NO HA REPORTADO" not in line


def test_and_the_clock_is_not_a_description_of_what_it_is_doing(one_browser_task):
    """«lleva 2 minutos» is true; «abierto en la página, interactuando» is the invention on top of it."""
    one_browser_task(url="", steps=0)
    line = _nav_line(prompt.live_state())
    assert "NO describas lo que estaría haciendo" in line
    assert "Los segundos que lleva NO son una descripción" in line


# ── the wall the case scores as the top mark ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("locale", ["es", "us"])
def test_every_transactional_category_says_what_closing_it_takes(locale):
    """Bringing real options and stopping at the wall DICIÉNDOLO is the maximum score for these cases; a
    category that never mentions the account or the card lets the worker stop without saying why."""
    missing = [name for name, entry in sc.SITE_CATALOG[locale].items()
               if name in sc.TRANSACTIONAL_CATEGORIES
               and not any(w in entry.note.lower() for w in ("cuenta", "account"))]
    assert missing == [], f"{locale}: {missing}"


@pytest.mark.parametrize("locale", ["es", "us"])
def test_and_every_transactional_category_has_a_destination(locale):
    for name in sc.TRANSACTIONAL_CATEGORIES:
        entry = sc.entry_for(name, locale)
        assert entry is not None and entry.url, f"{locale}/{name}"
