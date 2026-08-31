"""Tests for memory.compose_state() — the SHARED STATE used by both brains (V2-027).

Canonical location: tests/memory/unit/.

Contract: A (mission) + B (situational) + C (TIGHT synthesis of the short-term context), small and orderly, DIRECT READ
(no LLM or retriever). The mission comes from state.mission or, if it was not seeded, from the `mission_fallback` passed by
the caller (nucleo/flash) — this keeps the memory→voice dependency in the right direction.
"""
import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def test_compose_mission_and_situational(fresh_db):
    memapi.set_state({"operator_name": "Ricart", "treatment": "directo"})
    block, op, stats = memapi.compose_state(mission_fallback="Eres zaelar, asistente por voz.")
    assert op == "Ricart"
    assert "QUIÉN ERES" in block and "Eres zaelar" in block
    assert "QUIÉN TIENES DELANTE" in block and "Ricart" in block and "directo" in block
    assert stats["has_mission"] and stats["has_state"] and stats["op"] == "Ricart"


def test_compose_uses_seeded_mission_over_fallback(fresh_db):
    memapi.set_state({"mission": "MISIÓN SEMBRADA"})
    block, _op, _stats = memapi.compose_state(mission_fallback="fallback")
    assert "MISIÓN SEMBRADA" in block and "fallback" not in block


def test_compose_empty_with_no_fallback_is_blank(fresh_db):
    block, op, stats = memapi.compose_state(mission_fallback="")
    assert block == "" and op == ""
    assert not stats["has_mission"]


def test_compose_short_is_synthesized_not_full_dump(fresh_db):
    # Write many short-term lines; section C must TRIM them (not dump the 30 raw lines from before).
    for i in range(12):
        memapi.write_now(f"Operador: mensaje corto número {i} con algo de relleno para ocupar caracteres",
                         kind="conv", level="short", importance=0.2)
    block, _op, stats = memapi.compose_state(mission_fallback="m")
    assert "DE QUÉ ÍBAIS HABLANDO" in block
    assert stats["short_count"] <= 5              # aggressive cap (V2-027): at most the last 5
    assert block.count("· ") <= 12                 # does not dump all 12 lines


def test_compose_state_is_direct_no_retriever(fresh_db, monkeypatch):
    """compose_state NEVER triggers the retriever (memory.query) — that would put embeddings in the cacheable path."""
    calls = {"n": 0}
    real = memapi.query

    def _spy(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(memapi, "query", _spy)
    memapi.set_state({"operator_name": "Ana"})
    memapi.compose_state(mission_fallback="m")
    assert calls["n"] == 0


# ── USER RULES (V2-046 A1): operator rules in STATE — persistent, capped, deduplicated, rendered ────────────

def test_user_rules_render_and_empty_is_byte_identical(fresh_db):
    """With empty rules the block is BYTE-identical (not one extra line); with rules, add a REGLAS DEL OPERADOR line."""
    memapi.set_state({"operator_name": "Ricart"})
    before, _, _ = memapi.compose_state(mission_fallback="m")
    assert "REGLAS DEL OPERADOR" not in before
    memapi.add_user_rule("Sé más directo, responde en una frase")
    after, _, _ = memapi.compose_state(mission_fallback="m")
    assert "REGLAS DEL OPERADOR" in after and "Sé más directo" in after
    # removing it returns the exact original block
    _, gone = memapi.remove_user_rule("esa regla de ser directo")
    assert gone
    again, _, _ = memapi.compose_state(mission_fallback="m")
    assert again == before


def test_user_rules_dedup_and_cap(fresh_db):
    """Repeating a rule does not duplicate it (it moves it to the most recent position); the cap drops the oldest one."""
    memapi.add_user_rule("Responde solo sí o no")
    memapi.add_user_rule("responde solo si o no.")          # same rule, different spelling → dedup
    assert len(memapi.state()["rules"]) == 1
    for i in range(10):
        memapi.add_user_rule(f"Regla número {i}")
    rules = memapi.state()["rules"]
    assert len(rules) == 8                                   # cap
    assert "Regla número 9" in rules[-1]                     # the most recent one wins


def test_user_rules_remove_fuzzy_and_no_false_removal(fresh_db):
    """Removal matches by fuzzy reference; without a strong enough signal it does NOT remove the wrong rule."""
    memapi.add_user_rule("Cuando te pida una acción hazla sin responder")
    memapi.add_user_rule("Trátame de usted")
    _, gone = memapi.remove_user_rule("olvida lo de tratarme de usted")
    assert gone == "Trátame de usted"
    _, gone2 = memapi.remove_user_rule("olvida esa regla del parchís")   # it does not exist → changes nothing
    assert gone2 == "" and len(memapi.state()["rules"]) == 1


# ── An ERRAND is not a fact about the person (V2-337, 2026-08-26) ───────────────────────────────────────────
#
# Both were in the SAME list and under the SAME instruction — «take it as known without searching» — so «Vive en Madrid»
# and «Tarea pendiente para el asistente: buscarle un coche de segunda mano» were read as the same kind of data.
# Measured by the harness in `cheapest-monitor`: the agent started by talking about CARS, carrying over the errand from the
# previous case. And it is not a staging issue: in the operator's LIVE memory, **3 of the 5 slots were errands**
# (a flight to London, a plumber who ran out of quota, a worker test), displacing the person.
#
# The class was already present in the data and was being discarded: `mem_processor` explicitly states that a delegated task is
# `kind="result"`, and `salient_long` returns `kind`. Both directions are checked here because either one alone is
# trivially satisfied: sending everything to errands leaves the agent unable to know who its operator is, while sending
# nothing there is the measured failure.

def _pon(texto, kind, importancia=0.9):
    from memory import writer as memwriter
    return memwriter.insert_memory(texto, kind=kind, level="long", weight=0.9, importance=importancia)


def test_un_encargo_NO_se_presenta_bajo_dalo_por_sabido(fresh_db):
    _pon("Vive en Madrid, España.", "fact")
    _pon("Tarea pendiente para el asistente: buscarle un coche de segunda mano.", "result")

    bloque, _op, stats = memapi.compose_state()

    sabido = bloque.split("[Lo que sabes de él")[1].split("[Encargos")[0]
    assert "Vive en Madrid" in sabido
    assert "coche de segunda mano" not in sabido, (
        "un encargo sigue viajando como hecho permanente de la persona: es lo que hizo que el agente "
        "arrancara hablando de coches cuando le preguntaron por un monitor")
    assert stats["errand_count"] == 1 and stats["salient_count"] == 1


def test_un_HECHO_de_la_persona_NO_baja_a_la_lista_de_encargos(fresh_db):
    """The other direction. Without this, «errands do not belong with facts» is satisfied by sending EVERYTHING to errands —
    and the agent stops knowing where its operator lives, which is a worse and quieter failure."""
    for texto, kind in (("Vive en Madrid, España.", "fact"),
                        ("Prefiere trato directo.", "pref"),
                        ("Quiere comprar un monitor de 27 pulgadas.", "intent"),
                        ("El mes pasado viajó a Oporto.", "event")):
        _pon(texto, kind)

    bloque, _op, stats = memapi.compose_state()

    assert "[Encargos" not in bloque, f"sin un solo encargo no puede aparecer la sección: {bloque}"
    # `salient_count` is not fixed at 4: the writer creates CONCEPT NODES («viajes») that also enter the
    # salient profile, and hard-coding the number would measure the scaffolding instead of the contract. The claim is that
    # none of the four went to errands and that all remain visible.
    assert stats["errand_count"] == 0
    assert stats["salient_count"] >= 4
    for esperado in ("Vive en Madrid", "trato directo", "monitor de 27", "Oporto"):
        assert esperado in bloque


def test_el_encargo_sigue_VISIBLE_y_legible_como_pendiente(fresh_db):
    """The safety condition imposed by the harness itself: an unanswered errand must still read as pending.
    Hiding it would replace this failure with the opposite one — an agent that forgets what it was asked to do."""
    _pon("Tarea pendiente para el asistente: buscarle un coche de segunda mano.", "result")

    bloque, _op, _stats = memapi.compose_state()

    assert "coche de segunda mano" in bloque, "el encargo desapareció del prompt: eso es olvidarlo, no ordenarlo"
    cabecera = bloque.split("[Encargos")[1].split("]")[0]
    assert "NO son hechos sobre él" in cabecera, "la sección no dice de qué clase es lo que lleva"


def test_la_linea_de_encargos_no_ORDENA_ejecutarlos(fresh_db):
    """Doctrine from `workers/findings.py`: provide the data and name its class; the judgment stays in the
    brain. An instruction to «take care of this» is exactly what produced the measured defect."""
    _pon("Tarea pendiente para el asistente: buscarle un coche.", "result")

    cabecera = memapi.compose_state()[0].split("[Encargos")[1].split("]")[0].lower()

    assert "no empieces a trabajar" in cabecera
    assert "salvo que él lo saque" in cabecera, "without the exception, an errand that the operator DOES bring up is ignored"
