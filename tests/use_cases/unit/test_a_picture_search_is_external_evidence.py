"""V2-463 — an image search IS the outside world bringing something back, and the judge sees it stated.

The run that established it (2026-08-28, third run of `show-real-photo-of-a-new-car__es`): the product delivered
12 REAL photos from ferrari.com and instagram.com in the first turn, with the card open and sources stated — and the
judge scored it 2/5 as «visual hallucination» because the evidence reader only counts workers and browser tasks:
«zero external evidence». The instrument blamed the product (the lesson from
[[feedback_el_instrumento_acusa_al_producto]]) for looking where the evidence is not.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import verify as V


def _ev(query: str, *, ok=True, count=12, source="google", sites=None, blocked=False, degraded=""):
    return {"kind": "brain", "cat": "flash", "label": "🖼️ fotos: búsqueda", "query": query, "ok": ok,
            "count": count, "source": source, "sites": sites or [], "blocked": blocked,
            "degraded_from": degraded}


# ── the reader ───────────────────────────────────────────────────────────────────────────────────────────
def test_lee_las_busquedas_con_su_query_y_su_resultado():
    rows = V.image_searches([_ev("Ferrari Amalfi", sites=["www.ferrari.com"]),
                             _ev("avísame cuando la tengas", ok=False, count=0)])
    assert len(rows) == 2
    assert rows[0]["query"] == "Ferrari Amalfi" and rows[0]["sites"] == ["www.ferrari.com"]
    assert rows[1]["ok"] is False, "the failed one travels too: it is precisely the one that needs diagnosing"


def test_la_degradacion_a_bing_viaja_con_la_fila():
    """Bing was measured and gives the wrong car 9 times out of 10: whoever reads the run has to know WHICH index
    answered, or bad photos look like a product defect instead of a blocked search engine."""
    rows = V.image_searches([_ev("Ferrari Amalfi coche fotos", source="bing", degraded="google")])
    assert rows[0]["source"] == "bing" and rows[0]["degraded_from"] == "google"


# ── the audit ────────────────────────────────────────────────────────────────────────────────────────
def test_una_busqueda_con_fotos_YA_es_evidencia_externa():
    """The literal defect: `sin_evidencia_externa` with 12 real photos in front of it."""
    out = V.audit([_ev("Ferrari Amalfi")], expected_signals=["widget"])
    assert not [a for a in out["anomalies"] if a["clase"] == "sin_evidencia_externa"]


def test_una_busqueda_VACIA_no_compra_la_evidencia():
    """Half the sensitivity: a search that brought back nothing cannot conceal that the world brought back nothing."""
    out = V.audit([_ev("x", ok=False, count=0)], expected_signals=["widget"])
    assert [a for a in out["anomalies"] if a["clase"] == "sin_evidencia_externa"]


# ── and the judge sees it in WORDS ─────────────────────────────────────────────────────────────────────────
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
    """An entire afternoon of runs silently degraded to Bing: the «unusual traffic» captcha was detected and
    the combiner LOST it (it returned Bing's result, whose `blocked` is False). Bing's weak photos were read as a
    product defect. A captcha and an empty result call for different things — waiting versus reformulating — and
    the judge must be able to attribute quality to the block, not to the product."""
    from tests.use_cases.e2e.agent import judge as J
    mech = {"image_searches": [{"query": "Ferrari Amalfi", "ok": True, "count": 12, "source": "bing",
                                "sites": ["x.com"], "blocked": True, "degraded_from": "google",
                                "degraded_because": "blocked"}]}
    txt = J.mechanism_facts(mech)
    assert "BLOQUEADO por captcha" in txt and "no del producto" in txt


def test_el_ruido_de_visibilidad_de_pestañas_no_es_una_op_de_widget():
    """The judge for round 7 raised an entire [high] alert that «widgets 160 and 165 were never opened» — they were
    frontend `tab:visibility` events with raw numeric IDs, not widgets."""
    ops = V.widget_ops([{"cat": "widget", "label": "tab:visibility", "id": "160"},
                        {"cat": "widget", "label": "agent:state", "id": "124"},
                        {"cat": "widget", "label": "show", "id": "imagenes"}])
    assert "160" not in ops and "124" not in ops and "imagenes" in ops
    # The RECORDED round raised it from noise to a flood: the spectator connects the voice session and ~230
    # `agent:state` rows pour in — the judge read «there is no show» with `imagenes: show×5` in front of it.


def test_el_juez_sabe_que_el_visor_pinta_la_fuente():
    """Round 8: perfect delivery and 1/5 because «the mechanism does not indicate that the source was associated in
    the visualization» — the widget's RENDER test (4.83) indicates it. A product fact that the judge does not
    receive stated does not exist for it (V2-346)."""
    from tests.use_cases.e2e.agent import judge as J
    txt = J.mechanism_facts({"widget_ops": {"imagenes": {"show": 1, "data": 1}}})
    assert "FUENTE" in txt and "4.83" in txt
    # …and without the viewer in play, the line does not appear (it is not a generic disclaimer):
    txt2 = J.mechanism_facts({"widget_ops": {"agenda": {"data": 1}}})
    assert "4.83" not in txt2
