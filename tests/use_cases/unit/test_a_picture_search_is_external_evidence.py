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
    assert "Google sin resultados → bing" in txt


def test_un_bloqueo_de_google_se_dice_con_su_nombre():
    """Una tarde entera de rondas degradó a Bing en silencio: el captcha de «tráfico inusual» se detectaba y
    el combinador lo PERDÍA (devolvía el resultado de Bing, cuyo `blocked` es False). Las fotos flojas de
    Bing se leyeron como defecto del producto. Un captcha y un vacío piden cosas distintas — esperar frente a
    reformular — y el juez tiene que poder cargar la calidad al bloqueo, no al producto."""
    from tests.use_cases.e2e.agent import judge as J
    mech = {"image_searches": [{"query": "Ferrari Amalfi", "ok": True, "count": 12, "source": "bing",
                                "sites": ["x.com"], "blocked": True, "degraded_from": "google",
                                "degraded_because": "blocked"}]}
    txt = J.mechanism_facts(mech)
    assert "BLOQUEADO por captcha" in txt and "no del producto" in txt


def test_el_ruido_de_visibilidad_de_pestañas_no_es_una_op_de_widget():
    """El juez de la ronda 7 colgó un [alta] entero de «los widgets 160 y 165 nunca se abrieron» — eran
    eventos `tab:visibility` del frontend con ids numéricos crudos, no widgets."""
    ops = V.widget_ops([{"cat": "widget", "label": "tab:visibility", "id": "160"},
                        {"cat": "widget", "label": "agent:state", "id": "124"},
                        {"cat": "widget", "label": "show", "id": "imagenes"}])
    assert "160" not in ops and "124" not in ops and "imagenes" in ops
    # La ronda GRABADA lo subió de ruido a inundación: el espectador conecta la sesión de voz y caen ~230
    # filas `agent:state` — el juez leyó «no hay show» con `imagenes: show×5` delante.


def test_el_juez_sabe_que_el_visor_pinta_la_fuente():
    """Ronda 8: entrega perfecta y 1/5 porque «el mecanismo no indica que la fuente estuviera asociada en la
    visualización» — lo indica el test de RENDER del widget (4.83). Un hecho del producto que el juez no
    recibe enunciado no existe para él (V2-346)."""
    from tests.use_cases.e2e.agent import judge as J
    txt = J.mechanism_facts({"widget_ops": {"imagenes": {"show": 1, "data": 1}}})
    assert "FUENTE" in txt and "4.83" in txt
    # …y sin el visor en juego, la línea no aparece (no es un descargo genérico):
    txt2 = J.mechanism_facts({"widget_ops": {"agenda": {"data": 1}}})
    assert "4.83" not in txt2
