"""A request the light path already WROTE is not an errand for a worker three turns later. Node 2.588.

Measured (what-does-my-week-look-like ES, report 20261014-005411): «Apúntame dos cosas: dentista el 24 de octubre…
y cena con Laura…» wrote both appointments via `widget_data` in turn 0. On «Perfecto, con eso me apaño. Gracias.»
the onboarding offer («Si quieres, otro día te cuento…») read as a promise, the backstop asked the window for its
request (`escalate_goal_from_window`, V2-132), found turn 0, and a Brain Worker spent two minutes re-writing two
appointments already in the calendar. Every landed data-op passes `write_outcome.remember` on both channels; a WRITE
notes its sentence there, and the lookback skips it.
"""
from __future__ import annotations

import pytest

from nucleo.flash import router_guards as RG
from nucleo.flash import served_writes as SW
from nucleo.circuit import compose as WO

ASKED = ("Apúntame dos cosas: dentista el 24 de octubre a las nueve y media, y cena con Laura dos días después a "
         "las nueve de la noche.")
WINDOW = [{"role": "user", "content": ASKED}, {"role": "assistant", "content": "Voy con las dos."},
          {"role": "user", "content": "Vale, ¿me confirmas cuando estén apuntadas?"},
          {"role": "assistant", "content": "Sí, ya están apuntadas las dos."}]


@pytest.fixture(autouse=True)
def _clean():
    WO.reset()
    yield
    WO.reset()


def test_the_measured_request_was_work_before_the_write():
    assert RG.escalate_goal_from_window(WINDOW, "Perfecto, con eso me apaño. Gracias.").startswith(ASKED)


def test_after_its_write_landed_there_is_nothing_to_start():
    WO.remember("agenda", "add_meeting", ASKED, {"ok": True})
    assert RG.escalate_goal_from_window(WINDOW, "Perfecto, con eso me apaño. Gracias.") == ""


def test_a_refused_write_or_a_view_does_not_count():
    WO.remember("agenda", "add_meeting", ASKED, {"ok": False, "error": "x"})
    WO.remember("agenda", "show_day", ASKED, {"ok": True})
    assert not SW.served(ASKED)
    assert RG.escalate_goal_from_window(WINDOW, "Perfecto, gracias.").startswith(ASKED)


def test_the_sentence_with_our_notes_glued_still_names_his():
    WO.remember("agenda", "add_meeting", ASKED + " [SISTEMA] nota del turno", {"ok": True})
    assert SW.served(ASKED)


def test_it_expires():
    SW.note("agenda", "add_meeting", ASKED, {"ok": True}, now=0.0)
    assert not SW.served(ASKED, now=SW.TTL_S + 1)
