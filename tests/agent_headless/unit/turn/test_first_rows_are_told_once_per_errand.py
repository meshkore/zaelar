"""The first-rows notice is said ONCE per errand: never repeated, never when a reply already named the rows, and two
appends a second apart schedule one check (node 2.679)."""
from __future__ import annotations

import pytest

from i18n import langs
from nucleo.turn import first_rows_notice as frn

ERRAND = {"id": "t7", "request": "Busco actividades para niños en Madrid", "secs": 120, "sheet": "cd34-t7"}
ROWS = [{"title": "Taller de cerámica infantil Arcilla", "price": "15 €", "url": "https://a.es/1"},
        {"title": "Granja escuela El Álamo", "url": "https://a.es/2"}]
NOW = 2_000_000.0


def _ev(t, role, text):
    return {"t_ms": t, "kind": "brain", "role": role, "text": text, "wall": "you" if role == "user" else "agent"}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    frn.forget()
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("es"))
    yield
    frn.forget()


def test_a_reply_that_already_named_a_row_closes_the_notice():
    events = [_ev(NOW - 60_000, "user", "avísame cuando tengas algo"),
              _ev(NOW - 50_000, "assistant", "Ya hay uno: la Granja escuela El Álamo, en la hoja.")]
    assert frn.decide("cd34-t7", {"items": ROWS}, errand=ERRAND, events=events, now_ms=NOW)[1] == "already said"
    assert frn.decide("cd34-t7", {"items": ROWS}, errand=ERRAND, events=events, now_ms=NOW)[1] == "already noticed"


def test_a_word_of_the_errand_itself_is_not_a_row_said():
    events = [_ev(NOW - 60_000, "user", "me dices cuando tengas actividades"),
              _ev(NOW - 50_000, "assistant", "Sigo buscando actividades para niños.")]
    assert frn.decide("cd34-t7", {"items": ROWS}, errand=ERRAND, events=events, now_ms=NOW)[1] == ""


def test_once_noticed_never_again(monkeypatch):
    frn._TOLD["t7"] = 1.0
    events = [_ev(NOW - 60_000, "user", "avísame")]
    assert frn.decide("cd34-t7", {"items": ROWS}, errand=ERRAND, events=events, now_ms=NOW)[1] == "already noticed"
    monkeypatch.setattr(frn, "_errand_of", lambda sheet: ERRAND)
    assert frn.landed("cd34-t7", ROWS) is False


def test_two_appends_schedule_one_check(monkeypatch):
    started = []
    monkeypatch.setattr(frn, "_errand_of", lambda sheet: ERRAND)

    class _T:
        def __init__(self, target=None, args=(), **kw):
            started.append(args)
            args[0].close()                    # the coroutine is not run here

        def start(self):
            pass

    monkeypatch.setattr(frn.threading, "Thread", _T)
    assert frn.landed("cd34-t7", ROWS) is True
    assert frn.landed("cd34-t7", ROWS) is False
    assert len(started) == 1


def test_the_default_sheet_belongs_to_no_errand(monkeypatch):
    monkeypatch.setattr(frn, "_errand_of", lambda sheet: ERRAND)
    assert frn.landed("", ROWS) is False
