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
        # `q` es el sufijo de instancia (V2-259): este fichero mide la caja PELADA, así que el doble solo
        # contesta cuando no se pide ninguna instancia — si contestara a todas, taparía justo el defecto
        # que el nodo 10.61 existe para cazar (leer la caja equivocada).
        monkeypatch.setattr(probe_client, "widget_data",
                            lambda wid, q="": payload if (wid == "results" and not q) else None)
    return _install


def test_a_sheet_with_candidates_is_reported_with_its_named_rows(sheet):
    sheet(SHEET)
    out = verifymod.results_sheet()
    assert out["read"] is True
    assert out["n_items"] == 3
    assert out["n_named"] == 2, "una fila sin nombre no es un candidato (misma regla que la nota del navegador)"
    # RESPALDO POR FILA, que es la pregunta «¿de dónde salió ESTE candidato?». Este assert leía
    # `counts.sources` —la PESTAÑA «Fuentes», donde el worker declara qué sitios probó— y por eso la
    # confusión pasó sus tests: las tres filas de aquí llevan `url`, y el número que se comprobaba era 4.
    # Medido el 2026-08-24 con seis anuncios reales con enlace vivo: el informe dijo «0 fuentes» y el juez
    # fichó dos [alta] por invención contra una entrega correcta.
    assert out["n_backed"] == 3, "las tres filas llevan `url`: su respaldo NO depende de la pestaña Fuentes"
    assert out["n_sites_reported"] == 4, "la pestaña sigue contándose, con su nombre de verdad"


def test_una_fila_SIN_procedencia_no_cuenta_como_respaldada(sheet):
    """Sensibilidad: si `n_backed` contara filas, un candidato inventado pasaría por respaldado."""
    sheet({"items": [{"title": "Fontanero inventado"}, {"title": "Real", "url": "https://x.example/1"}],
           "counts": {"sources": 0}})
    out = verifymod.results_sheet()
    assert out["n_named"] == 2 and out["n_backed"] == 1


def test_el_sitio_de_origen_tambien_es_respaldo(sheet):
    """Una fila puede traer el sitio sin enlace directo (`badge`), y eso SÍ se puede comprobar."""
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
    assert "pestaña Fuentes: 4 sitio(s)" in text, "las dos cifras son distintas y se dicen aparte"
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


# ── el caso MEDIDO: seis anuncios reales leídos como inventados ────────────────────────────────────────
# `search-secondhand-monitor__es` (2026-08-24 01:35). La hoja acabó con SEIS anuncios, cada uno con su
# enlace vivo a milanuncios.com o es.wallapop.com, su precio y su ubicación. El informe dijo «6 candidato(s)
# con nombre de 6 fila(s) · 0 fuente(s)» y el juez —leyéndolo como había que leerlo— fichó DOS [alta]:
#
#     «Los 6 títulos no tienen ninguna fuente asociada (n_sources: 0) … Los nombres parecen inventados o
#      rellenados sin lectura real de la página, lo que es el fallo MÁS GRAVE de este caso.»
#
# Era una entrega CORRECTA. El número venía de `counts.sources`, que es la PESTAÑA «Fuentes» —donde el
# worker declara qué sitios probó— y estaba vacía porque es opcional. Tercera vez de esta clase en dos días
# (`results: null`, `duplicate_errands`) y la más cara: las otras exageraban un defecto, ésta fabricó uno
# encima de un acierto.

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
    "counts": {"sources": 0},          # la pestaña, vacía — y eso no dice nada de las filas
}


def test_seis_anuncios_con_enlace_vivo_NO_son_una_hoja_sin_respaldo(sheet):
    sheet(_MEDIDO)
    out = verifymod.results_sheet()
    assert out["n_named"] == 6
    assert out["n_backed"] == 6, "cada fila trae su enlace: esta hoja está respaldada entera"
    assert out["n_sites_reported"] == 0


def test_y_al_JUEZ_se_le_dice_que_la_pestana_vacia_NO_es_invencion(sheet):
    sheet(_MEDIDO)
    facts = judgemod.mechanism_facts({"results_sheet": verifymod.results_sheet()})
    assert "las 6 llevan enlace o sitio de origen" in facts
    assert "No lo puntúes como invención" in facts, (
        "sin esta frase el juez vuelve a leer una pestaña opcional vacía como resultados fabricados")


def test_pero_una_hoja_de_verdad_SIN_respaldo_se_sigue_diciendo(sheet):
    """Sensibilidad: quitar el falso positivo no puede quitar el verdadero — un título sin nada detrás SÍ es
    lo que este caso prohíbe."""
    sheet({"items": [{"title": "Fontanero 4,7 sobre 5"}, {"title": "Otro fontanero"}], "counts": {}})
    facts = judgemod.mechanism_facts({"results_sheet": verifymod.results_sheet()})
    assert "solo 0 de 2 llevan enlace o sitio de origen" in facts
    assert "no se pueden comprobar" in facts
