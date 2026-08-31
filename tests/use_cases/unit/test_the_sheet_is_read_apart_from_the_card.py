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
        # `q` is the instance suffix (V2-259): this file measures the BARE box, so the stub only
        # answers when no instance is requested — if it answered all of them, it would hide precisely the defect
        # that node 10.61 exists to catch (reading the wrong box).
        monkeypatch.setattr(probe_client, "widget_data",
                            lambda wid, q="": payload if (wid == "results" and not q) else None)
    return _install


def test_a_sheet_with_candidates_is_reported_with_its_named_rows(sheet):
    sheet(SHEET)
    out = verifymod.results_sheet()
    assert out["read"] is True
    assert out["n_items"] == 3
    assert out["n_named"] == 2, "a row without a name is not a candidate (same rule as the browser note)"
    # ROW-LEVEL BACKING, which is the question “where did THIS candidate come from?”. This assert read
    # `counts.sources` —the “Sources” TAB, where the worker declares which sites it tried—so the
    # confusion passed its tests: all three rows here have `url`, and the number being checked was 4.
    # Measured on 2026-08-24 with six real listings with a live link: the report said “0 sources” and the judge
    # flagged two [high] invention findings against a correct delivery.
    assert out["n_backed"] == 3, "all three rows have `url`: their backing does NOT depend on the Sources tab"
    assert out["n_sites_reported"] == 4, "the tab is still counted, under its actual name"


def test_una_fila_SIN_procedencia_no_cuenta_como_respaldada(sheet):
    """Sensitivity: if `n_backed` counted rows, an invented candidate would pass as backed."""
    sheet({"items": [{"title": "Fontanero inventado"}, {"title": "Real", "url": "https://x.example/1"}],
           "counts": {"sources": 0}})
    out = verifymod.results_sheet()
    assert out["n_named"] == 2 and out["n_backed"] == 1


def test_el_sitio_de_origen_tambien_es_respaldo(sheet):
    """A row can provide the site without a direct link (`badge`), and that CAN be verified."""
    sheet({"items": [{"title": "Monitor", "badge": "Wallapop"}], "counts": {}})
    assert verifymod.results_sheet()["n_backed"] == 1


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
    text = _report_text({"results_sheet": {"read": True, "n_items": 3, "n_named": 2, "n_backed": 3,
                                           "n_sites_reported": 4,
                                           "titles": ["fontanero24h O'Donnell", "Fontanero Centro Madrid"]}},
                        tmp_path)
    assert "hoja de resultados: 2 candidato(s) con nombre de 3 fila(s) · 3 con enlace/fuente" in text
    assert "pestaña Fuentes: 4 sitio(s)" in text, "the two figures are different and are stated separately"
    assert "fontanero24h O'Donnell" in text


def test_the_judge_is_told_the_sheet_may_have_filled_after_the_last_turn(sheet):
    facts = judgemod.mechanism_facts({"results_sheet": {"read": True, "n_items": 5, "n_named": 5,
                                                        "n_backed": 5, "n_sites_reported": 4,
                                                        "titles": ["A", "B"]}})
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


# ── MEASURED case: six real listings read as invented ────────────────────────────────────────
# `search-secondhand-monitor__es` (2026-08-24 01:35). The sheet ended with SIX listings, each with its
# live link to milanuncios.com or es.wallapop.com, its price, and its location. The report said “6 candidate(s)
# named out of 6 row(s) · 0 source(s)” and the judge —reading it as it should be read—flagged TWO [high]:
#
#     “The 6 titles have no associated source (n_sources: 0) … The names appear to be invented or
#      filled in without actually reading the page, which is the MOST SERIOUS failure in this case.”
#
# It was a CORRECT delivery. The number came from `counts.sources`, which is the “Sources” TAB —where the
# worker declares which sites it tried— and it was empty because it is optional. Third time of this kind in two days
# (`results: null`, `duplicate_errands`) and the costliest: the others exaggerated a defect; this one fabricated one
# on top of a success.

_MEDIDO = {
    "title": 'Monitores 27" de segunda mano por menos de 150 €',
    "items": [
        {"title": 'MSI PRO MP273A 27"', "price": "49 €", "badge": "Madrid",
         "url": "https://www.milanuncios.com/monitores-de-segunda-mano/monitor-msi-pro-mp273a-de-27-611313666.htm"},
        {"title": 'Monitor de 27"', "price": "50 €", "badge": "Wallapop",
         "url": "https://es.wallapop.com/item/monitor-de-27-1168096322"},
        {"title": "Samsung Monitor 27 HDTV", "price": "50 €", "badge": "Wallapop",
         "url": "https://es.wallapop.com/item/samsung-monitor-27-hdtv-1193979310"},
        {"title": "Monitor Philips 27'", "price": "50 €", "badge": "Wallapop",
         "url": "https://es.wallapop.com/item/monitor-philips-27-1276124104"},
        {"title": "Monitor Samsung 27 Negro", "price": "50 €", "badge": "Wallapop",
         "url": "https://es.wallapop.com/item/monitor-samsung-27-negro-1282222494"},
        {"title": "Monitor Xiaomi 27 Negro", "price": "50 €", "badge": "Wallapop",
         "url": "https://es.wallapop.com/item/monitor-xiaomi-27-negro-1291145854"},
    ],
    "counts": {"sources": 0},          # the tab, empty — and that says nothing about the rows
}


def test_seis_anuncios_con_enlace_vivo_NO_son_una_hoja_sin_respaldo(sheet):
    sheet(_MEDIDO)
    out = verifymod.results_sheet()
    assert out["n_named"] == 6
    assert out["n_backed"] == 6, "each row has its link: this entire sheet is backed"
    assert out["n_sites_reported"] == 0


def test_y_al_JUEZ_se_le_dice_que_la_pestana_vacia_NO_es_invencion(sheet):
    sheet(_MEDIDO)
    facts = judgemod.mechanism_facts({"results_sheet": verifymod.results_sheet()})
    assert "las 6 llevan enlace o sitio de origen" in facts
    assert "No lo puntúes como invención" in facts, (
        "without this phrase the judge again reads an empty optional tab as fabricated results")


def test_pero_una_hoja_de_verdad_SIN_respaldo_se_sigue_diciendo(sheet):
    """Sensitivity: removing the false positive cannot remove the true one — a title with nothing behind it IS
    what this case prohibits."""
    sheet({"items": [{"title": "Fontanero 4,7 sobre 5"}, {"title": "Otro fontanero"}], "counts": {}})
    facts = judgemod.mechanism_facts({"results_sheet": verifymod.results_sheet()})
    assert "solo 0 de 2 llevan enlace o sitio de origen" in facts
    assert "no se pueden comprobar" in facts
