"""V2-487 — an agent that answers “this field is missing” HAS answered.

Measured live against `roomrover` on 2026-08-29, the three consecutive hops:

    {"prompt": "hotel in New York City check-in 2026-09-10 …"}
      → 400 {"error": "parse_failed", "detail": "…Pass structured fields (city, checkin, checkout) instead."}
    {"city": "New York", "checkin": "2026-09-10", "checkout": "2026-09-12", "adults": 2}
      → 400 {"error": "missing_fields", "need": ["country_code"]}
    …with `country_code: "US"` → **200 with ten real hotels**, price, rating, and booking link, in 0.4 s.

`ask` flattened all of that to “returned 400” and `serve` flattened it again to “the network agents did not
answer” — a false diagnosis that sends us to open Chromium against Booking for data that was one field away.
The form was stated in the module’s own docstring; it was known and still discarded.

This does NOT test any hotel schema: there is none. What is fixed is the CONTRACT — the agent declares what it
needs, we transmit it in full to whoever has the task, and the fields that agent composes travel unchanged.
"""
import pytest

from nucleo import mesh_agents as m


AGENTE = {"agent_id": "roomrover", "endpoint": "https://roomrover.example"}


def _post_falso(respuestas):
    """Returns a fake `_post` that also RECORDS the body with which it was called."""
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
    """With `prompt` included, the agent interprets the free text and **discards the fields** — measured: the same
    body that returns ten hotels without `prompt` returns `parse_failed` with it."""
    post, vistos = _post_falso([(200, {"count": 10})])
    monkeypatch.setattr(m, "_post", post)
    m.ask(AGENTE, "hotel en Nueva York", {"city": "New York", "country_code": "US"})
    assert vistos[0] == {"city": "New York", "country_code": "US"}
    assert "prompt" not in vistos[0] and "query" not in vistos[0]


def test_sin_campos_sigue_yendo_el_TEXTO_LIBRE(monkeypatch):
    """The first attempt remains unchanged: the oracle and agents expect `prompt` (and `query` for compatibility),
    and that is the path that already worked."""
    post, vistos = _post_falso([(200, {"count": 10})])
    monkeypatch.setattr(m, "_post", post)
    m.ask(AGENTE, "entradas de teatro en Madrid")
    assert vistos[0] == {"prompt": "entradas de teatro en Madrid", "query": "entradas de teatro en Madrid"}


def test_un_402_sigue_sin_pagarse(monkeypatch):
    """Free agents only, enforced in code. Touching the error path must not loosen this."""
    post, _ = _post_falso([(402, {"price": 1})])
    monkeypatch.setattr(m, "_post", post)
    res = m.ask(AGENTE, "hotel en Nueva York")
    assert res["payment_required"] is True and res["ok"] is False


def test_el_puente_convierte_field_en_campos():
    """`--field key=value`, repeatable. A number is sent as a number: some agents reject `adults: "2"`, and
    that is the FORM of the value, not its meaning — the bridge does not know what “adults” is."""
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
