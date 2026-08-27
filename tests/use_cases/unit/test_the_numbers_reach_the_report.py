"""The numbers that decide WHOSE fault a defect is have to be in the file the fixing agent opens.

Until 2026-08-21 every one of them was pulled out by hand with a throwaway script and pasted into a
cluster message. That works while somebody is sitting there doing it, and does not survive a handover:
the .md report — the thing another agent actually reads — carried none of them.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent.report import _mechanism_numbers as M


def test_a_quiet_healthy_round_says_nothing():
    """No line without something to say: a report padded with zeroes stops being read."""
    assert M({}) == []
    assert M({"worker_health": {"spawned": 0}, "search_returns": {"queries": 0}}) == []


def test_a_relay_is_named_as_NOT_a_death():
    out = " ".join(M({"worker_health": {"spawned": 3, "ok": 1, "errored": 0, "relayed": 1,
                                        "still_running": 1}}))
    assert "NO es una muerte" in out
    assert "seguía(n) trabajando" in out


def test_the_shared_session_carries_its_own_contrast():
    out = " ".join(M({"worker_deaths": {"shared_sessions": {"c5ad1d9e": ["3", "4"]},
                                        "dead_resuming": 2, "resuming": 2,
                                        "dead_fresh": 0, "fresh": 3, "lifetimes_ms": {}}}))
    assert "COMPARTIDA" in out
    assert "2 de 2" in out and "0 de 3" in out, "the split IS the finding; a count of corpses is not"


def test_a_search_that_answered_and_never_arrived_is_flagged():
    out = " ".join(M({"search_returns": {"queries": 23, "returns": 22, "notes_from_search": 0}}))
    assert "NINGUNA se le empujó al cerebro" in out


def test_and_is_NOT_flagged_when_it_did_arrive():
    out = " ".join(M({"search_returns": {"queries": 5, "returns": 5, "notes_from_search": 5}}))
    assert "NINGUNA" not in out


def test_an_unsettled_round_warns_that_missing_may_mean_not_yet():
    out = " ".join(M({"quiescence": {"settled": False, "waited_s": 60.2, "pending_workers": 1}}))
    assert "todavía no" in out


def test_a_settled_round_says_nothing_about_it():
    assert M({"quiescence": {"settled": True, "waited_s": 6.0, "pending_workers": 0}}) == []


# ── V2-362: el RELOJ de la entrega, en el informe ───────────────────────────────────────────────────────
#
# `sheet_timing` se calcula desde V2-300 y se afinó en V2-355… y no se imprimía en ninguna parte. El juez lo
# recibe en el JSON, pero quien lee el informe —un humano, o el agente que va a arreglar el caso— no podía ver
# el número. Una medida sin lector es una decisión sin llamante: existe y no cambia nada. Se descubrió al
# intentar sacar la latencia de catorce rondas y encontrar la columna vacía en las catorce.
#
# Y es EL número de la queja del operador («una búsqueda se hace en un minuto, dos o tres máximo»): cuánto
# tarda el encargo en poner su primera fila delante. Con «eficiencia 2» en once de esas catorce rondas, ese
# dato es lo único que dice dónde apuntar.

def test_el_reloj_sale_con_su_numero_y_con_QUE_reloj_es():
    """El reloj FLOJO (primera escritura del worker, que puede ser su plan) y el ESTRICTO (el intake, que son
    candidatos de verdad) no miden lo mismo — confundirlos es lo que produjo los 130,8 s de «retención»
    inventados que V2-355 cortó. Un número sin su procedencia es el que nadie audita."""
    out = " ".join(M({"sheet_timing": {"sheet_ms": 1000.0, "sheet_named_ms": 71000.0,
                                       "delivery_lag_s": 12.8, "delivery_clock": "intake"}}))
    assert "primera fila de candidatos: 70.0s" in out
    assert "reloj: intake" in out
    assert "12.8s después de que existieran" in out


def test_una_hoja_que_se_abrio_y_nunca_recibio_nada_lo_DICE():
    """«No llegó» y «no medido» son cosas distintas: callar aquí deja la ronda sin explicación."""
    out = " ".join(M({"sheet_timing": {"sheet_ms": 1000.0}}))
    assert "NUNCA llegó" in out


def test_sin_medida_no_se_inventa_una_linea():
    assert M({}) == []
    assert M({"sheet_timing": {}}) == []


def test_el_retraso_de_CERO_se_imprime_y_no_se_confunde_con_ausente():
    """Un `delivery_lag_s` de 0 es una entrega inmediata —la mejor noticia posible— y un `None` es que no se
    midió. Un `if _lag:` los habría colapsado en silencio."""
    out = " ".join(M({"sheet_timing": {"sheet_ms": 1000.0, "sheet_named_ms": 5000.0, "delivery_lag_s": 0.0}}))
    assert "0.0s después de que existieran" in out
