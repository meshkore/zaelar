"""Contrato del DIRECTOR DE INVESTIGACIÓN (`nucleo/research.py`).

El fallo que cierra (operador, 2026-08-09): pedir «las mejores vacaciones» y recibir tres resultados sacados de la
primera página de un buscador. El worker ya sabía navegar y extraer; lo que nadie le decía era cuán ANCHO buscar ni
con qué BAREMO juzgar, así que se autoimponía el criterio mínimo que satisfacía la frase literal.

Lo que se prueba aquí es la DIRECCIÓN, no la búsqueda: que el brief separe lo que descalifica de lo que puntúa, que
imponga un suelo de amplitud aunque el modelo pida menos, que el embudo llegue al prompt del worker, y que «sigue
buscando» continúe la misma investigación en vez de repetirla igual. Todo determinista: el compositor (una llamada a
un modelo) va mockeado — lo que se verifica es el contrato alrededor, no la creatividad del modelo.
"""
import asyncio
import json

import pytest

from memory import db as memdb
from nucleo import research


@pytest.fixture(autouse=True)
def _fresh_kv(tmp_path, monkeypatch):
    """KV aislado: `remember_round` persiste en la memoria REAL y no puede ensuciar la del operador."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _raw(**over):
    base = {
        "research": True,
        "goal": "Tres propuestas de vacaciones en Baleares del 17 al 23 de agosto para 2 adultos y 2 niños",
        "domain": "viaje familiar en ferry",
        "hard": ["17-23 agosto", "2 adultos + 2 niños (9 y 11)", "coche 4x4 ≤5 m largo / 1,80 m alto",
                 "todos en la MISMA habitación", "≤2.000€ por 4 noches"],
        "soft": ["ferry rápido", "desayuno incluido", "gran piscina o complejo acuático"],
        "assumed": ["hora de viaje indiferente → se elige la más cómoda"],
        "enrichments": ["viajan con su propio coche → el hotel necesita parking"],
        "breadth": {"min_candidates": 40, "angles": ["agregador de hoteles", "web directa del hotel",
                                                     "web del operador de ferry"]},
        "quality_bar": ["nota ≥8 con al menos 100 opiniones", "confirmar en las FOTOS que la piscina es grande"],
        "deliverable": {"widget": "results", "n_final": 3, "composite": True,
                        "parts": ["Hotel", "Ferry", "Restaurante"]},
    }
    base.update(over)
    return json.dumps(base, ensure_ascii=False)


# ── 1) qué NO es una investigación ────────────────────────────────────────────────────────────────────────────
def test_a_plain_action_is_not_a_research_task():
    """«cancela mi cita» no necesita amplitud ni baremo: sin brief el worker sale como siempre. Si esto devolviera
    un brief, cada acción trivial pagaría un pre-vuelo y un embudo que no vienen a cuento."""
    assert research.parse(json.dumps({"research": False})) is None


def test_a_brief_without_a_goal_is_useless_and_refused():
    assert research.parse(_raw(goal="")) is None


def test_garbage_in_never_raises():
    for junk in ("", "no soy json", "{roto", "[]", None):
        assert research.parse(junk) is None


def test_fences_around_the_json_are_tolerated():
    assert research.parse("```json\n" + _raw() + "\n```") is not None


# ── 2) el SUELO DE AMPLITUD: lo que impide que la selección vuelva a ser superficial ──────────────────────────
def test_a_lowball_breadth_is_raised_to_the_floor():
    """El sesgo del modelo, si le dejas el número, es pedir «10 candidatos» — la búsqueda superficial con otro
    nombre. Elegir «el mejor» entre 8 no es elegir."""
    b = research.parse(_raw(breadth={"min_candidates": 8, "angles": ["uno"]}))
    assert b["breadth"]["min_candidates"] == research._MIN_CANDIDATES_FLOOR


def test_a_missing_breadth_still_gets_the_floor():
    b = research.parse(_raw(breadth={}))
    assert b["breadth"]["min_candidates"] >= research._MIN_CANDIDATES_FLOOR


def test_an_absurd_breadth_is_capped():
    b = research.parse(_raw(breadth={"min_candidates": 99999}))
    assert b["breadth"]["min_candidates"] == research._MIN_CANDIDATES_CAP


def test_lists_are_bounded_so_the_worker_can_actually_honour_them():
    b = research.parse(_raw(hard=[f"criterio {i}" for i in range(50)]))
    assert len(b["hard"]) == research._MAX_LIST


# ── 3) el EMBUDO llega al prompt del worker ───────────────────────────────────────────────────────────────────
def test_prompt_block_orders_the_funnel_gather_before_discard():
    block = research.to_prompt_block(research.parse(_raw()))
    assert "EMBUDO OBLIGATORIO" in block
    gather = block.index("REÚNE al menos 40")
    verify = block.index("VERIFICA A FONDO")
    assert gather < verify, "reunir ancho va ANTES de verificar finalistas; al revés es otra vez el top-3"


def test_prompt_block_keeps_hard_and_soft_apart():
    block = research.to_prompt_block(research.parse(_raw()))
    hard = block.index("CRITERIOS DUROS")
    soft = block.index("CRITERIOS BLANDOS")
    assert hard < soft
    assert "descalificado" in block[hard:soft], "un duro tiene que decir que DESCALIFICA"
    assert "no descalifican" in block[soft:], "un blando tiene que decir que NO descalifica"


def test_prompt_block_asks_for_composite_proposals_not_separate_lists():
    block = research.to_prompt_block(research.parse(_raw()))
    assert "PROPUESTAS COMPLETAS" in block
    assert "Hotel + Ferry + Restaurante" in block


def test_prompt_block_demands_facts_so_followups_are_answerable():
    """Lo que el worker no deje en `facts` no lo sabrá el cerebro cuando el operador pregunte, y habrá que buscarlo
    otra vez — el mismo trabajo pagado dos veces."""
    block = research.to_prompt_block(research.parse(_raw()))
    assert "facts" in block and "images" in block


def test_prompt_block_requires_reporting_the_real_breadth():
    block = research.to_prompt_block(research.parse(_raw()))
    assert "agent_report considered" in block, "sin el nº de candidatos, «las 3 mejores» no es auditable"


def test_prompt_block_offers_to_keep_searching():
    assert "SEGUIR buscando" in research.to_prompt_block(research.parse(_raw()))


def test_assumed_data_must_be_disclosed_not_hidden():
    """Inventar un dato que falta está bien (no bloquea la búsqueda); ocultar que lo has inventado, no."""
    block = research.to_prompt_block(research.parse(_raw()))
    assert "DATOS ASUMIDOS" in block and "MENCIÓNALOS" in block


def test_an_empty_brief_renders_nothing_rather_than_a_hollow_block():
    assert research.to_prompt_block({}) == ""
    assert research.to_prompt_block({"goal": ""}) == ""


# ── 4) RONDA 2: «esos no me valen, sigue buscando» ────────────────────────────────────────────────────────────
def test_expand_raises_breadth_and_keeps_the_agreed_criteria():
    b = research.parse(_raw())
    nxt = research.expand(b, note="esos no me valen, algo más barato")
    assert nxt["round"] == 2
    assert nxt["breadth"]["min_candidates"] > b["breadth"]["min_candidates"]
    assert nxt["hard"] == b["hard"], "reabrir los criterios sería OTRA búsqueda, no la continuación de esta"
    assert "esos no me valen, algo más barato" in nxt["feedback"][0]


def test_expand_does_not_mutate_the_previous_round():
    b = research.parse(_raw())
    before = json.dumps(b, sort_keys=True)
    research.expand(b, note="más")
    assert json.dumps(b, sort_keys=True) == before


def test_the_rejection_reason_reaches_the_worker():
    nxt = research.expand(research.parse(_raw()), note="quiero piscina climatizada")
    assert "quiero piscina climatizada" in research.to_prompt_block(nxt)
    assert "ronda 2" in research.to_prompt_block(nxt)


# ── 5) continuidad por OBJETIVO: la 2ª frase del operador no menciona la 1ª ───────────────────────────────────
def test_a_continuation_is_matched_fuzzily_not_word_for_word():
    """La frase con la que se pide continuar nunca es la inicial. Con casado exacto, «sigue buscando» se leía como
    búsqueda nueva y devolvía la MISMA ronda 1 — es decir, lo que el operador acababa de rechazar."""
    from nucleo.dispatch import _goal_key
    b = research.parse(_raw())
    research.remember_round(_goal_key("busca vacaciones en Baleares en ferry con hotel con piscina"), b)
    found = research.previous_round(_goal_key(
        "busca vacaciones en Baleares en ferry con hotel con piscina, esos no me valen"))
    assert found is not None and found["goal"] == b["goal"]


def test_an_unrelated_request_does_not_inherit_someone_elses_criteria():
    from nucleo.dispatch import _goal_key
    research.remember_round(_goal_key("busca vacaciones en Baleares con ferry y piscina"), research.parse(_raw()))
    assert research.previous_round(_goal_key("pon música de jazz")) is None


def test_a_stale_round_is_a_new_search_again():
    from nucleo.dispatch import _goal_key
    gk = _goal_key("busca vacaciones en Baleares con ferry y piscina")
    research.remember_round(gk, research.parse(_raw()))
    from memory import api as memory
    reg = memory.kv_get(research._KV_ROUND)
    reg[gk]["ts"] -= research._ROUND_TTL + 60          # envejecerla más allá del TTL
    memory.kv_set(research._KV_ROUND, reg)
    assert research.previous_round(gk) is None


def test_the_round_registry_is_bounded():
    from nucleo.dispatch import _goal_key
    for i in range(research._ROUND_MAX + 15):
        research.remember_round(_goal_key(f"busca cosa distinta número {i} con detalle"), research.parse(_raw()))
    from memory import api as memory
    assert len(memory.kv_get(research._KV_ROUND) or {}) <= research._ROUND_MAX


def test_a_brief_survives_a_restart_so_a_resumed_task_keeps_its_criteria():
    b = research.parse(_raw())
    research.save("task-77", b)
    assert research.load("task-77")["hard"] == b["hard"]
    assert research.load("no-existe") is None


# ── 6) kill-switch y fail-open: esto NUNCA puede tumbar una escalada ─────────────────────────────────────────
def test_the_killswitch_turns_it_off_completely(monkeypatch):
    monkeypatch.setenv("ZAELAR_RESEARCH", "0")
    assert research.enabled() is False
    assert asyncio.run(research.compose("busca las mejores vacaciones")) is None


def test_a_slow_composer_never_holds_the_task_hostage(monkeypatch):
    """Un proveedor atascado no puede impedir que la tarea arranque: mejor un worker sin dirigir —como salía antes—
    que una escalada que no sale."""
    monkeypatch.setenv("ZAELAR_RESEARCH", "1")

    class _Hung:
        async def complete(self, *a, **k):
            await asyncio.sleep(30)
            return _raw()

    monkeypatch.setattr(research, "_spec", lambda: object())
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", lambda *a, **k: _Hung())
    assert asyncio.run(research.compose("busca las mejores vacaciones", timeout=0.2)) is None


def test_a_broken_composer_fails_open(monkeypatch):
    monkeypatch.setenv("ZAELAR_RESEARCH", "1")

    class _Boom:
        async def complete(self, *a, **k):
            raise RuntimeError("429 sin cuota")

    monkeypatch.setattr(research, "_spec", lambda: object())
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", lambda *a, **k: _Boom())
    assert asyncio.run(research.compose("busca las mejores vacaciones")) is None


def test_no_provider_means_no_brief_not_a_crash(monkeypatch):
    monkeypatch.setenv("ZAELAR_RESEARCH", "1")
    monkeypatch.setattr(research, "_spec", lambda: None)
    assert asyncio.run(research.compose("busca las mejores vacaciones")) is None


def test_a_good_composer_produces_a_directed_brief(monkeypatch):
    monkeypatch.setenv("ZAELAR_RESEARCH", "1")

    class _Ok:
        async def complete(self, *a, **k):
            return _raw()

    monkeypatch.setattr(research, "_spec", lambda: object())
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", lambda *a, **k: _Ok())
    b = asyncio.run(research.compose("nos queremos ir de vacaciones a Baleares en agosto"))
    assert b["breadth"]["min_candidates"] >= research._MIN_CANDIDATES_FLOOR
    assert b["request"].startswith("nos queremos ir")     # la petición literal viaja con el brief
    assert b["round"] == 1


def test_the_composer_is_told_todays_date():
    """Sin la fecha real, «agosto» o «el puente que viene» no se pueden anclar y el brief sale con fechas de otro año."""
    msgs = research.build_messages("busca vuelos", today="FECHA/HORA REAL DE HOY: lunes 10 ago 2026")
    assert "2026" in msgs[1]["content"]
    assert msgs[0]["role"] == "system" and "DIRECTOR DE INVESTIGACIÓN" in msgs[0]["content"]


def test_the_composer_prompt_spans_domains_instead_of_specialising():
    """La pieza tiene que dirigir igual de bien una tesis, un libro o la elección de una librería de software que un
    viaje. Los EJEMPLOS de varios dominios son buenos (enseñan la forma del problema); lo que sería un fallo es que
    solo hubiera ejemplos de un dominio, porque entonces esto es un buscador de viajes disfrazado de mecanismo
    genérico. Se mide la DIVERSIDAD, no la ausencia de palabras."""
    sysmsg = research.build_messages("x")[0]["content"].lower()
    domains = {
        "compra/selección": ("alojamiento", "coche", "portátil", "proveedores"),
        "académico": ("estado del arte", "tema", "fuente"),
        "creativo": ("escribir",),
        "técnico": ("librería", "arquitectura"),
    }
    covered = [name for name, words in domains.items() if any(w in sysmsg for w in words)]
    assert len(covered) >= 3, f"el director solo contempla {covered}: se ha especializado en un dominio"
    # y nada de fijar el vocabulario de UN caso concreto (el que motivó la pieza)
    for leak in ("baleares", "ferry", "piscina", "hotel"):
        assert leak not in sysmsg, f"«{leak}» es el caso que motivó la pieza, no puede estar en el mecanismo"
