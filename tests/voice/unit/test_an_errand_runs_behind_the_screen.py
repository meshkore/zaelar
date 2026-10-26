"""A card action the turn runs comes on screen only when the turn asked to SEE it (V2-815).

Measured on a phone, 2026-10-26: «busca el programa que está en tu web», «retoma la búsqueda de Draper», «check
hacker news, locate my post» — the brief said `canvas = neither` every time and the browser card took the whole
screen three times anyway: the catalogue rung (`card_commission.before_worker`) and the promise repair presented
every call as a `turn-order`. A search is work done behind the screen; its findings go to the errand's sheet.

`canvas_visibility.present_for_call` is the one rule: the card comes up for a `present.mount` action, for a lens
(`data.read`) over a closed card, or when the verdict says `canvas = show` — never on habit. Each case below varies
the widget and the action, so a fix that names the browser would not pass.
"""
from __future__ import annotations

import pytest

from nucleo.flash import canvas_visibility as cv
from nucleo.flash import turn_brief as tb


@pytest.fixture()
def shows(monkeypatch):
    out: list = []
    monkeypatch.setattr(cv, "is_open", lambda wid, known=None: False)
    monkeypatch.setattr(cv, "is_minimized", lambda wid: False)
    return out


def _emit(out):
    return lambda kind, label, extra=None, **k: out.append((label, dict(extra or {})))


def _verdict(monkeypatch, canvas):
    monkeypatch.setattr(tb, "read", lambda b, key, d="", min_confidence=None:
                        ((canvas, {"used": True}) if key == tb.CANVAS_KEY and canvas else (d, None)))


@pytest.mark.parametrize("wid,action", [("navegador", "automate"), ("navegador", "open"), ("mensajeria", "send")])
def test_a_write_with_no_show_in_the_turn_runs_behind_the_screen(monkeypatch, shows, wid, action):
    _verdict(monkeypatch, "neither")
    assert cv.present_for_call(wid, action, brief={"x": 1}, emit=_emit(shows)) is False
    assert [l for l, _ in shows] == ["🚫 presentación suprimida"], shows
    assert "detrás de la pantalla" in shows[0][1]["detail"]


def test_no_verdict_is_no_show(monkeypatch, shows):
    _verdict(monkeypatch, "")
    assert cv.present_for_call("navegador", "automate", brief=None, emit=_emit(shows)) is False
    assert not [l for l, _ in shows if l == "show"]


@pytest.mark.parametrize("wid,action", [("navegador", "open"), ("agenda", "add_event")])
def test_a_turn_that_asks_to_see_it_brings_the_card(monkeypatch, shows, wid, action):
    _verdict(monkeypatch, "show")
    assert cv.present_for_call(wid, action, brief={"x": 1}, emit=_emit(shows)) is True
    assert shows[-1][0] == "show" and shows[-1][1]["id"] == wid and shows[-1][1]["reason"] == "turn-order"


def test_an_output_that_only_exists_on_screen_brings_its_card_whatever_the_verdict(monkeypatch, shows):
    _verdict(monkeypatch, "neither")
    assert cv.present_for_call("musica", "play", brief={"x": 1}, emit=_emit(shows)) is True
    assert shows[-1][1]["reason"] == "producer-mount"


def test_a_lens_over_a_closed_card_brings_it(monkeypatch, shows):
    _verdict(monkeypatch, "neither")
    assert cv.present_for_call("agenda", "show_day", brief={"x": 1}, emit=_emit(shows)) is True
    assert shows[-1][1]["reason"] == "turn-order"


def test_the_card_presented_is_the_one_the_caller_narrowed_to(monkeypatch, shows):
    _verdict(monkeypatch, "show")
    cv.present_for_call("results", "present", brief={"x": 1}, card="results::abc-1", emit=_emit(shows))
    assert shows[-1][1]["id"] == "results::abc-1"


def test_every_repair_rung_asks_the_rule_instead_of_presenting_on_habit():
    """The four rungs that ran a card action ahead of a worker all present through `present_for_call`."""
    from pathlib import Path
    from tests import voice_turn_source as _vts
    eng = Path(__file__).resolve().parents[3]
    cc = _vts.read(eng / "nucleo/flash/card_commission.py")
    pw = _vts.read(eng / "nucleo/flash/post_stream_words.py")
    assert cc.count("present_for_call(got[\"widget_id\"], got[\"action\"], brief=brief") == 2
    assert pw.count("present_for_call(") >= 2
    assert 'present(_oc["widget_id"], reason="turn-order"' not in pw
