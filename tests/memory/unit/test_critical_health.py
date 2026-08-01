#
# test_critical_health.py — auditoría de memoria 2026-07-14 (hallazgo de SEGURIDAD del corpus v3):
#   una ALERGIA/intolerancia es un hecho médico ADITIVO y CRÍTICO. Dos fallos cerrados:
#   (A) el CORAZÓN la mis-asignaba al slot SINGULAR operator.diet → una DIETA declarada después la BORRABA
#       (supersede por slot). Guard del writer: alergia + slot de identidad → se retira el slot (queda aditiva),
#       pinned + importancia alta, meta.critical='health'.
#   (B) bajo densidad, la alergia se enterraba fuera del cap de salient_long. compose_state la surface SIEMPRE en
#       una línea CRÍTICO propia (critical_facts), independiente del ranking.
# Determinista: sin red (embeddings hash) ni LLM. Ejecutar:
#   .venv/bin/pytest tests/unit/memory/test_critical_health.py -q
#
import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory import writer


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("MEM_PROCESSOR", "0")
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


def _alive(substr):
    return memdb.get_db().query_one(
        "SELECT count(*) c FROM memories WHERE valid=1 AND lower(text) LIKE ?", (f"%{substr}%",))["c"]


# ── FIX A · una dieta NO borra una alergia ─────────────────────────────────────────────────────────────────

def test_allergy_never_takes_singular_diet_slot(fresh_db):
    mid = writer.insert_memory("Es alérgica a la penicilina.", level="long", kind="pref", slot="operator.diet")
    row = memdb.get_db().query_one("SELECT slot, pinned, meta FROM memories WHERE id=?", (mid,))
    assert row["slot"] is None, "la alergia NO debe conservar un slot singular (la borraría un dato posterior)"
    assert row["pinned"] == 1
    assert "critical" in (row["meta"] or ""), "la alergia debe marcarse meta.critical='health'"


def test_diet_statement_does_not_erase_allergy(fresh_db):
    writer.insert_memory("Es alérgica a la penicilina.", level="long", kind="pref", slot="operator.diet")
    writer.insert_memory("Es vegetariana.", level="long", kind="pref", slot="operator.diet")   # dieta REAL
    assert _alive("penicilina") == 1, "la dieta declarada NO puede borrar la alergia crítica"
    assert _alive("vegetariana") == 1, "la dieta sí se guarda"


def test_multiple_allergies_coexist(fresh_db):
    writer.insert_memory("Soy alérgica a la penicilina.", level="long", kind="pref", slot="operator.diet")
    writer.insert_memory("Soy alérgica a los frutos secos.", level="long", kind="fact", slot="diet")
    writer.insert_memory("Soy intolerante a la lactosa.", level="long", kind="fact")
    assert _alive("penicilina") == 1 and _alive("frutos secos") == 1 and _alive("lactosa") == 1


def test_real_diet_supersede_still_works(fresh_db):
    # regresión inversa: una DIETA (no alergia) con slot SÍ debe superseder normalmente (no rompemos el mecanismo)
    writer.insert_memory("Es vegetariana.", level="long", kind="pref", slot="operator.diet")
    writer.insert_memory("Ahora es vegana.", level="long", kind="pref", slot="operator.diet")
    assert _alive("vegetariana") == 0 and _alive("vegana") == 1, "una dieta sí supersede a otra dieta"


# ── FIX B · la alergia se surface SIEMPRE, incluso bajo densidad ───────────────────────────────────────────

def test_critical_fact_surfaces_under_density(fresh_db):
    memapi.set_state({"operator_name": "Amaia", "location": "Logroño"})
    writer.insert_memory("Es alérgica a la penicilina.", level="long", kind="pref", slot="operator.diet")
    for j in range(130):   # densidad: entierra la alergia bajo ruido de mayor recencia
        writer.insert_memory(f"Mensaje {j} sobre la escalada y el manuscrito.",
                             level="long", kind="msg", importance=0.6, weight=0.7)
    block, _op, _st = memapi.compose_state(mission_fallback="m")
    low = block.lower()
    assert "penicilina" in low, "la alergia debe surfacearse en el estado aunque esté enterrada bajo densidad"
    assert "crítico" in low, "debe ir en la línea CRÍTICO propia"
    # y NO se duplica en el bloque de perfil saliente
    assert not any("penicilina" in (m["text"] or "").lower() for m in memapi.salient_long(limit=8)), \
        "los críticos van SOLO en su línea, no también en salient_long (sin dup)"


def test_critical_facts_reader(fresh_db):
    writer.insert_memory("Es alérgica a la penicilina.", level="long", kind="pref")
    writer.insert_memory("Lleva marcapasos.", level="long", kind="fact")
    facts = memapi.critical_facts()
    joined = " ".join(facts).lower()
    assert "penicilina" in joined and "marcapasos" in joined
