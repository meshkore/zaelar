"""V2-487 — un agente que contesta «me falta este campo» SÍ ha contestado.

Medido en vivo contra `roomrover` el 2026-08-29, los tres saltos seguidos:

    {"prompt": "hotel in New York City check-in 2026-09-10 …"}
      → 400 {"error": "parse_failed", "detail": "…Pass structured fields (city, checkin, checkout) instead."}
    {"city": "New York", "checkin": "2026-09-10", "checkout": "2026-09-12", "adults": 2}
      → 400 {"error": "missing_fields", "need": ["country_code"]}
    …con `country_code: "US"` → **200 con diez hoteles reales**, precio, nota y enlace de reserva, en 0,4 s.

`ask` aplastaba todo eso a «respondió 400» y `serve` lo volvía a aplastar a «los agentes de la red no
contestaron» — una diagnosis falsa que manda a abrir un Chromium contra Booking por un dato que estaba a un
campo de distancia. La forma la avisaba el propio docstring del módulo; estaba sabido y se tiraba igual.

Aquí NO se prueba ningún esquema de hoteles: no lo hay. Lo que se fija es el CONTRATO — el agente declara lo
que necesita, nosotros se lo transmitimos entero a quien tiene el encargo, y los campos que ese componga
viajan tal cual.
"""
import pytest

from nucleo import mesh_agents as m


AGENTE = {"agent_id": "roomrover", "endpoint": "https://roomrover.example"}


def _post_falso(respuestas):
    """Devuelve un `_post` de mentira que además ANOTA el cuerpo con el que se le llamó."""
    vistos = []

    def _post(url, body, timeout=None):
        vistos.append(dict(body))
        return respuestas[min(len(vistos) - 1, len(respuestas) - 1)]

    return _post, vistos


@pytest.fixture(autouse=True)
def _sin_red(monkeypatch):
    monkeypatch.setattr(m, "_skill_path", lambda endpoint: "/v1/search")


def test_lo_que_el_agente_PIDE_llega_a_quien_puede_darselo(monkeypatch):
    post, _ = _post_falso([(400, {"error": "missing_fields", "need": ["country_code"]})])
    monkeypatch.setattr(m, "_post", post)
    res = m.ask(AGENTE, "hotel en Nueva York")
    assert res["ok"] is False
    assert res["asks"] == {"error": "missing_fields", "need": ["country_code"]}, (
        "se pierde lo único accionable que traía la respuesta")


def test_serve_NO_dice_que_no_contestaron_cuando_si_contestaron(monkeypatch):
    post, _ = _post_falso([(400, {"error": "missing_fields", "need": ["country_code"]})])
    monkeypatch.setattr(m, "_post", post)
    monkeypatch.setattr(m, "find", lambda errand, limit=5: {"intent": "bookings.hotels", "agents": [AGENTE]})
    monkeypatch.setattr(m, "route_for", lambda intent: None)
    res = m.serve("hotel en Nueva York", "hotel en Nueva York")
    assert res["ok"] is False
    assert "no contestaron" not in res["reason"], (
        "«no contestaron» es falso y caro: manda el encargo al navegador teniendo la respuesta a un campo")
    assert res["agent_asks"] == {"error": "missing_fields", "need": ["country_code"]}
    assert "--field" in res["reason"], "no se dice POR DÓNDE se vuelve a preguntar"


def test_los_campos_viajan_SOLOS(monkeypatch):
    """Con `prompt` dentro, el agente interpreta el texto libre y **descarta los campos** — medido: el mismo
    cuerpo que devuelve diez hoteles sin `prompt` devuelve `parse_failed` con él."""
    post, vistos = _post_falso([(200, {"count": 10})])
    monkeypatch.setattr(m, "_post", post)
    m.ask(AGENTE, "hotel en Nueva York", {"city": "New York", "country_code": "US"})
    assert vistos[0] == {"city": "New York", "country_code": "US"}
    assert "prompt" not in vistos[0] and "query" not in vistos[0]


def test_sin_campos_sigue_yendo_el_TEXTO_LIBRE(monkeypatch):
    """El primer intento no cambia: el oráculo y los agentes esperan `prompt` (y `query` por compatibilidad),
    y ese camino es el que ya funcionaba."""
    post, vistos = _post_falso([(200, {"count": 10})])
    monkeypatch.setattr(m, "_post", post)
    m.ask(AGENTE, "entradas de teatro en Madrid")
    assert vistos[0] == {"prompt": "entradas de teatro en Madrid", "query": "entradas de teatro en Madrid"}


def test_un_402_sigue_sin_pagarse(monkeypatch):
    """Solo agentes gratis, aplicado en código. Tocar el camino de error no puede aflojar esto."""
    post, _ = _post_falso([(402, {"price": 1})])
    monkeypatch.setattr(m, "_post", post)
    res = m.ask(AGENTE, "hotel en Nueva York")
    assert res["payment_required"] is True and res["ok"] is False


def test_el_puente_convierte_field_en_campos():
    """`--field clave=valor`, repetible. Un número va como número: algunos agentes rechazan `adults: "2"`, y
    eso es la FORMA del valor, no su significado — el puente no sabe qué es «adults»."""
    from nucleo import mesh_cli
    visto = {}

    def _serve(errand, prompt, fields=None):
        visto.update({"errand": errand, "prompt": prompt, "fields": fields})
        return {"ok": True}

    import nucleo.mesh_agents as ma
    original, ma.serve = ma.serve, _serve
    try:
        assert mesh_cli.main(["serve", "hotel", "--field", "city=New York", "--field", "adults=2"]) == 0
    finally:
        ma.serve = original
    assert visto["fields"] == {"city": "New York", "adults": 2}


def test_un_field_mal_escrito_lo_dice_y_no_llama_a_nadie():
    from nucleo import mesh_cli
    import nucleo.mesh_agents as ma

    def _explota(*a, **k):
        raise AssertionError("no se puede salir a la red con un --field ilegible")

    original, ma.serve = ma.serve, _explota
    try:
        assert mesh_cli.main(["serve", "hotel", "--field", "ciudad-sin-igual"]) == 0
    finally:
        ma.serve = original
