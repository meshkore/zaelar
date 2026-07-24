"""Tests de memory.compose_state() — el ESTADO COMPARTIDO por los dos cerebros (V2-027).

Contrato: A (misión) + B (situacional) + C (síntesis TENSA del corto plazo), pequeño y ordenado, LECTURA DIRECTA
(sin LLM ni retriever). La misión sale de state.mission o, si no se sembró, del `mission_fallback` que pasa el
llamador (nucleo/flash) — así no se invierte la dependencia memoria→voz.
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
    # Escribe muchas líneas de corto plazo; la sección C debe RECORTAR (no volcar las 30 crudas de antes).
    for i in range(12):
        memapi.write_now(f"Operador: mensaje corto número {i} con algo de relleno para ocupar caracteres",
                         kind="conv", level="short", importance=0.2)
    block, _op, stats = memapi.compose_state(mission_fallback="m")
    assert "DE QUÉ ÍBAIS HABLANDO" in block
    assert stats["short_count"] <= 5              # cap agresivo (V2-027): a lo sumo las últimas 5
    assert block.count("· ") <= 12                 # no vuelca las 12 líneas


def test_compose_state_is_direct_no_retriever(fresh_db, monkeypatch):
    """compose_state NUNCA dispara el retriever (memory.query) — sería meter embeddings en la ruta cacheable."""
    calls = {"n": 0}
    real = memapi.query

    def _spy(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(memapi, "query", _spy)
    memapi.set_state({"operator_name": "Ana"})
    memapi.compose_state(mission_fallback="m")
    assert calls["n"] == 0


# ── USER RULES (V2-046 A1): reglas del operador en el ESTADO — persistentes, cap, dedup, render ────────────

def test_user_rules_render_and_empty_is_byte_identical(fresh_db):
    """Con rules vacío el bloque es BYTE-idéntico (ni una línea extra); con reglas, línea REGLAS DEL OPERADOR."""
    memapi.set_state({"operator_name": "Ricart"})
    before, _, _ = memapi.compose_state(mission_fallback="m")
    assert "REGLAS DEL OPERADOR" not in before
    memapi.add_user_rule("Sé más directo, responde en una frase")
    after, _, _ = memapi.compose_state(mission_fallback="m")
    assert "REGLAS DEL OPERADOR" in after and "Sé más directo" in after
    # quitarla devuelve el bloque original exacto
    _, gone = memapi.remove_user_rule("esa regla de ser directo")
    assert gone
    again, _, _ = memapi.compose_state(mission_fallback="m")
    assert again == before


def test_user_rules_dedup_and_cap(fresh_db):
    """Re-decir una regla no duplica (la sube a la más reciente); el cap deja fuera la más antigua."""
    memapi.add_user_rule("Responde solo sí o no")
    memapi.add_user_rule("responde solo si o no.")          # misma regla, otra grafía → dedup
    assert len(memapi.state()["rules"]) == 1
    for i in range(10):
        memapi.add_user_rule(f"Regla número {i}")
    rules = memapi.state()["rules"]
    assert len(rules) == 8                                   # cap
    assert "Regla número 9" in rules[-1]                     # la más reciente manda


def test_user_rules_remove_fuzzy_and_no_false_removal(fresh_db):
    """La retirada casa por referencia difusa; sin señal suficiente NO retira la regla equivocada."""
    memapi.add_user_rule("Cuando te pida una acción hazla sin responder")
    memapi.add_user_rule("Trátame de usted")
    _, gone = memapi.remove_user_rule("olvida lo de tratarme de usted")
    assert gone == "Trátame de usted"
    _, gone2 = memapi.remove_user_rule("olvida esa regla del parchís")   # no existe → no toca nada
    assert gone2 == "" and len(memapi.state()["rules"]) == 1
