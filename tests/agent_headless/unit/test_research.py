"""Contract for the RESEARCH DIRECTOR (`nucleo/research.py`).

The bug this closes (operator, 2026-08-09): asking for “the best holiday” and receiving three results taken from the
first page of a search engine. The worker already knew how to browse and extract; what nobody told it was how BROADLY
to search or by what STANDARD to judge, so it imposed the minimum criterion that satisfied the literal phrase.

What is tested here is the DIRECTION, not the search: that the brief separates what disqualifies from what scores, that
it imposes a breadth floor even when the model asks for less, that the funnel reaches the worker prompt, and that
“keep searching” continues the same investigation instead of repeating it unchanged. Everything is deterministic: the
composer (one model call) is mocked—the contract around it is verified, not the model’s creativity.
"""
import asyncio
import json

import pytest

from memory import db as memdb
from nucleo import research


@pytest.fixture(autouse=True)
def _fresh_kv(tmp_path, monkeypatch):
    """Isolated KV: `remember_round` persists in REAL memory and must not pollute the operator’s memory."""
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


# ── 1) what is NOT a research task ─────────────────────────────────────────────────────────────────────────────
def test_a_plain_action_is_not_a_research_task():
    """“cancel my appointment” needs neither breadth nor a standard: without a brief, the worker runs as usual. If this
    returned a brief, every trivial action would pay for a pre-flight and a funnel that are beside the point."""
    assert research.parse(json.dumps({"research": False})) is None


def test_a_brief_without_a_goal_is_useless_and_refused():
    assert research.parse(_raw(goal="")) is None


def test_garbage_in_never_raises():
    for junk in ("", "no soy json", "{roto", "[]", None):
        assert research.parse(junk) is None


def test_fences_around_the_json_are_tolerated():
    assert research.parse("```json\n" + _raw() + "\n```") is not None


# ── 2) the BREADTH FLOOR: what keeps selection from becoming superficial again ─────────────────────────────────
def test_a_lowball_breadth_is_raised_to_the_floor():
    """If allowed to choose the number, the model’s bias is to ask for “10 candidates”—a superficial search under another
    name. Choosing “the best” from 8 is not choosing."""
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


# ── 3) the FUNNEL reaches the worker prompt ────────────────────────────────────────────────────────────────────
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
    """Anything the worker does not leave in `facts` will be unknown to the brain when the operator asks, and will have
    to be searched for again—the same work paid for twice."""
    block = research.to_prompt_block(research.parse(_raw()))
    assert "facts" in block and "images" in block


def test_prompt_block_requires_reporting_the_real_breadth():
    block = research.to_prompt_block(research.parse(_raw()))
    assert "agent_report considered" in block, "sin el nº de candidatos, «las 3 mejores» no es auditable"


def test_prompt_block_offers_to_keep_searching():
    assert "SEGUIR buscando" in research.to_prompt_block(research.parse(_raw()))


def test_assumed_data_must_be_disclosed_not_hidden():
    """Inventing a missing fact is fine (it does not block the search); hiding that you invented it is not."""
    block = research.to_prompt_block(research.parse(_raw()))
    assert "DATOS ASUMIDOS" in block and "MENCIÓNALOS" in block


def test_an_empty_brief_renders_nothing_rather_than_a_hollow_block():
    assert research.to_prompt_block({}) == ""
    assert research.to_prompt_block({"goal": ""}) == ""


# ── 4) ROUND 2: “these don’t work for me, keep searching” ─────────────────────────────────────────────────────
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


# ── 5) continuity by GOAL: the operator’s 2nd sentence does not mention the 1st ───────────────────────────────
def test_a_continuation_is_matched_fuzzily_not_word_for_word():
    """The sentence asking to continue is never the initial one. With exact matching, “keep searching” was read as a
    new search and returned the SAME round 1—in other words, what the operator had just rejected."""
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
    reg[gk]["ts"] -= research._ROUND_TTL + 60          # age it beyond the TTL
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


# ── 6) kill switch and fail-open: this must NEVER bring down an escalation ─────────────────────────────────────
def test_the_killswitch_turns_it_off_completely(monkeypatch):
    monkeypatch.setenv("ZAELAR_RESEARCH", "0")
    assert research.enabled() is False
    assert asyncio.run(research.compose("busca las mejores vacaciones")) is None


def test_a_slow_composer_never_holds_the_task_hostage(monkeypatch):
    """A stuck provider must not prevent the task from starting: a worker without direction—as it ran before—is better
    than an escalation that never completes. What CHANGED on 2026-08-13 is HOW this is expressed: the failure is raised
    as `ComposerUnavailable` and handled by `dispatch`, instead of a `None` that was confused with “this is not a
    research task,” and that confusion took half the task’s budget away (see the class)."""
    monkeypatch.setenv("ZAELAR_RESEARCH", "1")

    class _Hung:
        async def complete(self, *a, **k):
            await asyncio.sleep(30)
            return _raw()

    # V2-225: `_spec` returns (spec, tier)—the tier is what is reported to the chain if the provider
    # dies. `None` = model fixed by the operator, which is not a chain selection.
    monkeypatch.setattr(research, "_spec", lambda: (object(), None))
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", lambda *a, **k: _Hung())
    with pytest.raises(research.ComposerUnavailable):
        asyncio.run(research.compose("busca las mejores vacaciones", timeout=0.2))


def test_a_broken_composer_fails_open(monkeypatch):
    monkeypatch.setenv("ZAELAR_RESEARCH", "1")

    class _Boom:
        async def complete(self, *a, **k):
            raise RuntimeError("429 sin cuota")

    # V2-225: `_spec` returns (spec, tier)—the tier is what is reported to the chain if the provider
    # dies. `None` = model fixed by the operator, which is not a chain selection.
    monkeypatch.setattr(research, "_spec", lambda: (object(), None))
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", lambda *a, **k: _Boom())
    with pytest.raises(research.ComposerUnavailable):
        asyncio.run(research.compose("busca las mejores vacaciones"))


def test_no_provider_means_no_brief_not_a_crash(monkeypatch):
    monkeypatch.setenv("ZAELAR_RESEARCH", "1")
    monkeypatch.setattr(research, "_spec", lambda: None)
    with pytest.raises(research.ComposerUnavailable):
        asyncio.run(research.compose("busca las mejores vacaciones"))


def test_a_good_composer_produces_a_directed_brief(monkeypatch):
    monkeypatch.setenv("ZAELAR_RESEARCH", "1")

    class _Ok:
        async def complete(self, *a, **k):
            return _raw()

    # V2-225: `_spec` returns (spec, tier)—the tier is what is reported to the chain if the provider
    # dies. `None` = model fixed by the operator, which is not a chain selection.
    monkeypatch.setattr(research, "_spec", lambda: (object(), None))
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", lambda *a, **k: _Ok())
    b = asyncio.run(research.compose("nos queremos ir de vacaciones a Baleares en agosto"))
    assert b["breadth"]["min_candidates"] >= research._MIN_CANDIDATES_FLOOR
    assert b["request"].startswith("nos queremos ir")     # the literal request travels with the brief
    assert b["round"] == 1


def test_the_composer_is_told_todays_date():
    """Without the real date, “August” or “the upcoming long weekend” cannot be anchored and the brief comes out with dates from another year."""
    msgs = research.build_messages("busca vuelos", today="FECHA/HORA REAL DE HOY: lunes 10 ago 2026")
    assert "2026" in msgs[1]["content"]
    assert msgs[0]["role"] == "system" and "DIRECTOR DE INVESTIGACIÓN" in msgs[0]["content"]


def test_the_composer_prompt_spans_domains_instead_of_specialising():
    """The component must direct a thesis, a book, or the choice of a software library just as well as a trip. EXAMPLES
    from several domains are good (they teach the shape of the problem); the failure would be to have examples from
    only one domain, because then this would be a travel search engine disguised as a generic mechanism. DIVERSITY is
    measured, not the absence of words."""
    sysmsg = research.build_messages("x")[0]["content"].lower()
    domains = {
        "compra/selección": ("alojamiento", "coche", "portátil", "proveedores"),
        "académico": ("estado del arte", "tema", "fuente"),
        "creativo": ("escribir",),
        "técnico": ("librería", "arquitectura"),
    }
    covered = [name for name, words in domains.items() if any(w in sysmsg for w in words)]
    assert len(covered) >= 3, f"el director solo contempla {covered}: se ha especializado en un dominio"
    # and do not fix the vocabulary to ONE specific case (the one that motivated the component)
    for leak in ("baleares", "ferry", "piscina", "hotel"):
        assert leak not in sysmsg, f"«{leak}» es el caso que motivó la pieza, no puede estar en el mecanismo"


# ── 7) findings from the composer’s first REAL run (2026-08-09) ─────────────────────────────────────────────────
# The director was run against the operator’s literal request (a trip to the Balearic Islands) with the actual model.
# The brief was excellent where it mattered—real expert enrichments: “at age 11 many hotels already count a child as
# an adult for occupancy,” “1.80 m is the threshold for a tall vehicle on a ferry”—but it revealed two defects.
def test_a_descriptive_phrase_smuggled_as_a_role_becomes_a_badge():
    """What the actual model returned: instead of short roles, the DESCRIPTION of each component’s content. Placed
    unchanged in the card badge, it breaks it. The prompt asks for brevity; the cap guarantees it."""
    b = research.parse(_raw(deliverable={
        "widget": "results", "n_final": 3, "composite": True,
        "parts": ["Ruta de ferry (origen, destino, naviera, tipo rápido/convencional, horarios)",
                  "Tarifa de ferry para 4 pasajeros + vehículo (detallando cargos por altura)",
                  "Coste total combinado y razón por la que es la mejor opción"]}))
    roles = b["deliverable"]["parts"]
    assert all(len(r) <= research._MAX_ROLE_CHARS for r in roles)
    assert all(len(r.split()) <= research._MAX_ROLE_WORDS for r in roles)
    # and NEVER cut in the middle of a word: “Tarifa de ferry para 4 pasaj” is garbage on screen
    assert not any(r.endswith(("pasaj", "razó", "conven")) for r in roles), roles
    assert roles[0] == "Ruta de ferry"


def test_the_same_role_twice_is_not_a_composite_proposal():
    b = research.parse(_raw(deliverable={"widget": "results", "n_final": 3, "composite": True,
                                         "parts": ["Hotel", "hotel", "HOTEL", "Ferry"]}))
    assert b["deliverable"]["parts"] == ["Hotel", "Ferry"]


def test_the_composer_is_told_not_to_turn_a_search_into_a_booking():
    """REAL defect from the first run: the goal came out as “Find and BOOK the best deal…” when the operator only asked
    to search. A worker with “book” in its goal may actually book—a commitment of money, irreversible because of one
    word nobody said. Research means finding and proposing; acting is the operator’s decision after seeing the proposals."""
    sysmsg = research.build_messages("busca vacaciones")[0]["content"].lower()
    assert "no reservar" in sysmsg or "nunca añadas" in sysmsg
    for forbidden in ("reservar", "comprar", "pagar"):
        assert forbidden in sysmsg, f"el director tiene que nombrar «{forbidden}» para prohibirlo explícitamente"


def test_the_worker_is_told_not_to_commit_anything():
    """Defense in depth for the above: even if “book” slipped into the goal, the block the worker READS forbids it from
    committing money or sending anything. Research ends in proposing; acting is the operator’s decision."""
    block = research.to_prompt_block(research.parse(_raw()))
    assert "NO COMPROMETAS NADA" in block
    for forbidden in ("reserves", "compres", "pagues"):
        assert forbidden in block


# ── 8) the brief is SEEN on screen, not merely obeyed (2026-08-12) ─────────────────────────────────────────────
# The criteria being used for the search could previously only be ASKED about (“what did you understand?”), so they
# could not be checked at a glance or corrected by looking at them. They are now seeded in the CRITERIA tab of the
# results sheet, from PRE-FLIGHT—not by the worker: if this depended on the executor remembering to write them, they
# would be missing precisely in the searches that go worst.
def test_the_brief_becomes_the_criteria_tab():
    crit = research.to_criteria(research.parse(_raw()))
    assert crit["goal"].startswith("Tres propuestas")
    assert crit["hard"] and crit["soft"] and crit["quality_bar"] and crit["enrichments"]
    assert crit["min_candidates"] == 40 and crit["n_final"] == 3
    assert crit["domain"] == "viaje familiar en ferry"


def test_criteria_of_a_second_round_carry_the_rejection_as_a_change():
    """What the operator said when rejecting the previous round is their CORRECTION: it belongs in the tab, where they
    can see it, not only in the worker prompt."""
    nxt = research.expand(research.parse(_raw()), note="ninguno tiene parking cubierto")
    crit = research.to_criteria(nxt)
    assert "ninguno tiene parking cubierto" in crit["changes"]
    assert crit["goal"] == research.to_criteria(research.parse(_raw()))["goal"], \
        "la ronda 2 conserva el objetivo — es lo que impide que «sigue buscando» vacíe la hoja"


def test_nothing_to_show_is_not_a_crash():
    assert research.to_criteria({}) == {} and research.to_criteria(None) == {}


def test_the_worker_is_told_to_report_its_sources():
    """The missing piece for being able to AUDIT a search: until now, a website that kept us out (login, limit of 50,
    blocking) and a website with no results looked identical—“I found nothing”—so the operator could not know whether
    it was worth entering manually."""
    block = research.to_prompt_block(research.parse(_raw()))
    assert "FUENTES" in block and "results sources" in block
    for status in ("partial", "auth", "blocked"):
        assert status in block
    assert "results progress" in block, "y el avance: sin él el sumario no puede decir cuántos ha explorado"


# ── 8) HOW MANY and in WHAT ORDER they are delivered (operator request 2026-08-12) ────────────────────────────
# “By default we should search for ten results, and if the user asks for three or twenty, modify that base criterion”;
# and “order the ten best from one to ten.” Previously the default was 3 and the cap 10—which made “give me twenty”
# literally inexpressible in the brief.
def test_by_default_ten_are_delivered_not_three():
    b = research.parse(_raw(deliverable={"widget": "results"}))
    assert b["deliverable"]["n_final"] == 10


def test_the_number_the_operator_asks_for_wins_over_the_default():
    for asked in (3, 5, 20):
        b = research.parse(_raw(deliverable={"widget": "results", "n_final": asked}))
        assert b["deliverable"]["n_final"] == asked, f"pidió {asked}"


def test_twenty_is_expressible_and_absurd_numbers_are_capped():
    assert research.parse(_raw(deliverable={"n_final": 20}))["deliverable"]["n_final"] == 20
    assert research.parse(_raw(deliverable={"n_final": 500}))["deliverable"]["n_final"] == research._N_FINAL_CAP
    assert research.parse(_raw(deliverable={"n_final": 0}))["deliverable"]["n_final"] == 10, \
        "0 es «no lo dijo», no «no entregues nada»"


def test_the_delivery_is_ranked_and_the_order_is_the_ranking():
    """An unordered list forces the operator to repeat the comparison the worker already made. The brief must say that
    the order IS the ranking and that each option includes its score WITH its reason."""
    block = research.to_prompt_block(research.parse(_raw(deliverable={"widget": "results", "n_final": 10})))
    assert "ORDENADAS DE MEJOR A PEOR" in block
    assert "nº1" in block and "nº10" in block
    assert "score" in block and "why" in block, "una nota sin porqué no se puede discutir"


def test_declining_is_not_an_outage_and_keeps_the_normal_budget(monkeypatch):
    """The other half of the contract: if the composer ANSWERS that this does not require breadth or a standard, that is
    its decision and not a failure—it returns `None` and the task runs with its proper budget. Without this distinction,
    every conversation would have inherited a research task’s budget."""
    monkeypatch.setenv("ZAELAR_RESEARCH", "1")

    class _No:
        async def complete(self, *a, **k):
            return '{"research": false, "why": "es una pregunta, no una selección"}'

    # V2-225: `_spec` returns (spec, tier)—the tier is what is reported to the chain if the provider
    # dies. `None` = model fixed by the operator, which is not a chain selection.
    monkeypatch.setattr(research, "_spec", lambda: (object(), None))
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", lambda *a, **k: _No())
    assert asyncio.run(research.compose("¿qué hora es?")) is None


def test_an_unreadable_answer_is_an_outage_not_a_decline(monkeypatch):
    """A composer that answers with something unreadable has NOT decided that this is not a research task: it has
    failed. Treating it as its rejection is exactly what took time away from the task."""
    monkeypatch.setenv("ZAELAR_RESEARCH", "1")

    class _Garbage:
        async def complete(self, *a, **k):
            return "claro, te preparo un brief… (y aquí se cortó)"

    # V2-225: `_spec` returns (spec, tier)—the tier is what is reported to the chain if the provider
    # dies. `None` = model fixed by the operator, which is not a chain selection.
    monkeypatch.setattr(research, "_spec", lambda: (object(), None))
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", lambda *a, **k: _Garbage())
    with pytest.raises(research.ComposerUnavailable):
        asyncio.run(research.compose("busca las mejores vacaciones"))


# ── V2-538: what an ITEM is — the worker was dumping portal landing pages as candidates ──────────────────────
def test_the_brief_teaches_that_a_portal_page_is_never_an_item():
    """Measured live (2026-09-01): a catamaran search filled the sheet with portal landing pages, a dealer's
    name and an over-budget boat. The funnel must state — before the 'fill as you go' block invites early
    presents — that an item is ONE concrete candidate and a portal/category page belongs in `sources`."""
    from nucleo.research_prompts import to_prompt_block
    block = to_prompt_block({"goal": "catamaranes de segunda mano por menos de 200.000", "hard": ["<200k"]})
    assert "QUÉ ES UN ITEM" in block
    assert "NO son items" in block
    assert "lista VACÍA" in block
    # The definition must come BEFORE the block that tells it to present early: the early present is
    # exactly where the junk entered.
    assert block.index("QUÉ ES UN ITEM") < block.index("LA HOJA SE LLENA MIENTRAS TRABAJAS")
