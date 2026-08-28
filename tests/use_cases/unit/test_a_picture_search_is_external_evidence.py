"""V2-463 — una búsqueda de imágenes ES el mundo exterior trayendo algo, y el juez la ve enunciada.

La ronda que lo fijó (2026-08-28, tercera corrida de `show-real-photo-of-a-new-car__es`): el producto entregó
12 fotos REALES de ferrari.com e instagram.com en el primer turno, tarjeta abierta, fuentes dichas — y el
juez la puntuó 2/5 como «alucinación visual» porque el lector de evidencia solo cuenta workers y tareas de
navegador: «cero evidencias externas». El instrumento acusaba al producto (la lección de
[[feedback_el_instrumento_acusa_al_producto]]) por mirar donde la evidencia no está.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import verify as V


def _ev(query: str, *, ok=True, count=12, source="google", sites=None, blocked=False, degraded=""):
    return {"kind": "brain", "cat": "flash", "label": "🖼️ fotos: búsqueda", "query": query, "ok": ok,
            "count": count, "source": source, "sites": sites or [], "blocked": blocked,
            "degraded_from": degraded}


# ── el lector ───────────────────────────────────────────────────────────────────────────────────────────
def test_lee_las_busquedas_con_su_query_y_su_resultado():
    rows = V.image_searches([_ev("Ferrari Amalfi", sites=["www.ferrari.com"]),
                             _ev("avísame cuando la tengas", ok=False, count=0)])
    assert len(rows) == 2
    assert rows[0]["query"] == "Ferrari Amalfi" and rows[0]["sites"] == ["www.ferrari.com"]
    assert rows[1]["ok"] is False, "la fallida también viaja: es justo la que hay que diagnosticar"


def test_la_degradacion_a_bing_viaja_con_la_fila():
    """Bing se midió y da el coche equivocado 9 de 10: quien lea la corrida tiene que saber QUÉ índice
    contestó, o unas fotos malas parecen un defecto del producto en vez de un buscador bloqueado."""
    rows = V.image_searches([_ev("Ferrari Amalfi coche fotos", source="bing", degraded="google")])
    assert rows[0]["source"] == "bing" and rows[0]["degraded_from"] == "google"


# ── la auditoría ────────────────────────────────────────────────────────────────────────────────────────
def test_una_busqueda_con_fotos_YA_es_evidencia_externa():
    """El defecto literal: `sin_evidencia_externa` con 12 fotos reales delante."""
    out = V.audit([_ev("Ferrari Amalfi")], expected_signals=["widget"])
    assert not [a for a in out["anomalies"] if a["clase"] == "sin_evidencia_externa"]


def test_una_busqueda_VACIA_no_compra_la_evidencia():
    """La mitad de sensibilidad: una búsqueda que no trajo nada no puede tapar que el mundo no trajo nada."""
    out = V.audit([_ev("x", ok=False, count=0)], expected_signals=["widget"])
    assert [a for a in out["anomalies"] if a["clase"] == "sin_evidencia_externa"]


# ── y el juez lo ve en PALABRAS ─────────────────────────────────────────────────────────────────────────
def test_el_juez_recibe_cada_busqueda_enunciada():
    from tests.use_cases.e2e.agent import judge as J
    mech = {"image_searches": V.image_searches([_ev("Ferrari Amalfi", sites=["www.ferrari.com"]),
                                                _ev("basura", ok=False, count=0, source="bing",
                                                    degraded="google")])}
    txt = J.mechanism_facts(mech)
    assert "Ferrari Amalfi" in txt and "www.ferrari.com" in txt
    assert "basura" in txt and "sin resultados" in txt
    assert "Google falló → bing" in txt
