"""The results SHEET is read as its own fact, and an unread sheet is never reported as an empty one.

Why this exists. The mechanism report used to learn "what the browser found" from ONE place: the browser
card's `results.items` (`GET /widgets/navegador/data?q=<task>`). V2-257 moves that boundary — the card becomes
a monitor and stops publishing findings, while the sheet becomes the single place they land, whichever browser
found them. On the day that ships, a report reading only the card prints `resultados=0` and a judge reading it
concludes "the browser found nothing", which is the false-defect class this harness has already paid for twice
(`results: null` read as proof of no extraction, V2-186; "not backed by navigation" over a case solved by
search, V2-189).

So the sheet is read too, apart, and `read` keeps "empty" apart from "nobody looked".
"""
from __future__ import annotations

import pytest

from tests.use_cases.e2e.agent import judge as judgemod
from tests.use_cases.e2e.agent import probe_client
from tests.use_cases.e2e.agent import report as reportmod
from tests.use_cases.e2e.agent import verify as verifymod


SHEET = {
    "title": "Fontaneros urgentes · Madrid centro",
    "items": [
        {"title": "fontanero24h O'Donnell", "url": "https://fontanero24h-odonnell.com/"},
        {"title": "Fontanero Centro Madrid", "url": "https://www.fontanerocentromadrid.com/"},
        {"title": "", "url": "https://ejemplo.example/paginacion"},   # a row with no name is not a candidate
    ],
    "counts": {"sources": 4},
}


@pytest.fixture
def sheet(monkeypatch):
    """Patch the ONE seam the reader uses, so the test exercises the real assembly and not a copy of it."""
    def _install(payload):
        monkeypatch.setattr(probe_client, "widget_data", lambda wid: payload if wid == "results" else None)
    return _install


def test_a_sheet_with_candidates_is_reported_with_its_named_rows(sheet):
    sheet(SHEET)
    out = verifymod.results_sheet()
    assert out["read"] is True
    assert out["n_items"] == 3
    assert out["n_named"] == 2, "una fila sin nombre no es un candidato (misma regla que la nota del navegador)"
    assert out["n_sources"] == 4


def test_an_unreadable_sheet_is_not_an_empty_one(sheet):
    sheet(None)
    out = verifymod.results_sheet()
    assert out["read"] is False and out["n_items"] == 0


def _report_text(mech: dict, tmp_path) -> str:
    """The REAL report, written to a throwaway dir and read back.

    Asserting on a helper would prove the helper works; the line lives inline in `build`, so the only way to
    know the operator sees it is to build a report and read it — and into `tmp_path`, never the live run dir.
    """
    out = reportmod.build([{"scenario": "x__es", "tier": 2, "channel": "probe",
                            "verdict": {"scores": {"resultado": 3}, "_judge_model": "test"},
                            "run": {"mechanism_report": mech, "transcript": []}}],
                          "20260821-000000", tmp_path)
    return out.read_text(encoding="utf-8")


def test_the_report_says_it_could_not_look_instead_of_printing_zero(tmp_path):
    assert "hoja de resultados: NO se pudo leer" in _report_text({"results_sheet": {"read": False}}, tmp_path)


def test_the_report_prints_the_named_candidates_the_sheet_ended_with(tmp_path):
    text = _report_text({"results_sheet": {"read": True, "n_items": 3, "n_named": 2, "n_sources": 4,
                                           "titles": ["fontanero24h O'Donnell", "Fontanero Centro Madrid"]}},
                        tmp_path)
    assert "hoja de resultados: 2 candidato(s) con nombre de 3 fila(s) · 4 fuente(s)" in text
    assert "fontanero24h O'Donnell" in text


def test_the_judge_is_told_the_sheet_may_have_filled_after_the_last_turn(sheet):
    facts = judgemod.mechanism_facts({"results_sheet": {"read": True, "n_items": 5, "n_named": 5,
                                                        "n_sources": 4, "titles": ["A", "B"]}})
    assert "HOJA de resultados" in facts
    # The measured failure of 2026-08-21 was not "found nothing" but "arrived 8 minutes late", and the judge
    # cannot tell those apart unless it is told the distinction exists.
    assert "tarde" in facts or "DESPUÉS" in facts


def test_the_judge_does_not_conclude_empty_when_the_sheet_was_not_read():
    facts = judgemod.mechanism_facts({"results_sheet": {"read": False}})
    assert "no se miró" in facts.lower()


def test_an_empty_sheet_that_WAS_read_is_still_reported_as_missing_delivery():
    """The counterweight: if this only ever excused the sheet, it would stop catching a real empty delivery."""
    facts = judgemod.mechanism_facts({"results_sheet": {"read": True, "n_items": 0, "n_named": 0}})
    assert "SIN candidatos" in facts


def test_widget_data_tells_a_failed_request_apart_from_an_empty_widget(monkeypatch):
    monkeypatch.setattr(probe_client, "_get", lambda p, timeout=20.0: {"error": "Connection refused"})
    assert probe_client.widget_data("results") is None
    monkeypatch.setattr(probe_client, "_get", lambda p, timeout=20.0: {"items": [], "title": "x"})
    assert probe_client.widget_data("results") == {"items": [], "title": "x"}
