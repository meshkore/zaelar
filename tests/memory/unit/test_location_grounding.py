#
# test_location_grounding.py — memory audit 2026-07-14 (post-V2-038 auditor findings):
#   (1) supersede by SLOT that immediately collapses LEGACY aliases (operator.location vs raw 'location'/'ubicacion'
#       keys) → a single current location pill, the most recent one WINS, zero contradictions;
#   (2) namespaced BACKGROUND SLOTS (weather:soria from the widget) remain SUBORDINATE to state.location: they do NOT enter
#       the passive state block (rendered as "take it as known without searching") — so "what's the weather today?" is not
#       hijacked by the wrong city — but they REMAIN retrievable through an explicit query.
# Deterministic: no network (hash embeddings) or LLM (MEM_PROCESSOR=0). Run:
#   .venv/bin/pytest tests/memory/unit/test_location_grounding.py -q
#
import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory import slots as memslots
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


def _valid_location_pills():
    rows = memdb.get_db().query(
        "SELECT id, slot, text FROM memories WHERE valid=1 AND slot LIKE '%location%'")
    return [(r["slot"], r["text"]) for r in rows]


# ── FIX #1 · supersede by SLOT collapses aliases immediately ───────────────────────────────────────────────

def test_equivalent_keys_expands_aliases():
    keys = memslots.equivalent_keys("operator.location")
    assert "operator.location" in keys
    assert "location" in keys and "ubicacion" in keys and "city" in keys
    # an unknown/namespaced slot does not expand (only itself)
    assert memslots.equivalent_keys("weather:soria") == ["weather:soria"]


def test_legacy_location_key_collapses_on_new_write(fresh_db):
    # LEGACY pill with raw key 'location' (pre-normalization) plus an 'ubicacion' → coexist until...
    writer.insert_memory("El operador vive en Soria.", level="long", kind="profile", slot="location")
    writer.insert_memory("Ubicación registrada: Bilbao.", level="long", kind="profile", slot="ubicacion")
    # ...the write with the CANONICAL key collapses ALL variants at once (the most recent one WINS).
    writer.insert_memory("Vive en Valencia.", level="long", kind="profile", slot="operator.location")
    pills = _valid_location_pills()
    assert len(pills) == 1, f"esperaba 1 píldora de ubicación vigente, hay {len(pills)}: {pills}"
    assert "valencia" in pills[0][1].lower()
    assert pills[0][0] == "operator.location"       # single canonical key


def test_repeated_same_fact_stays_single(fresh_db):
    # N ingestions of the SAME canonical fact (different phrasings) → 1 current pill (auditor point 3)
    for txt in ("Vivo en Valencia.", "Mi ciudad es Valencia.", "Ahora vivo en Valencia."):
        writer.insert_memory(txt, level="long", kind="profile", slot="operator.location")
    pills = _valid_location_pills()
    assert len(pills) == 1, f"hubo duplicación por ingestas repetidas: {pills}"


# ── FIX #2 · BACKGROUND slots subordinate to state.location ──────────────────────────────────────────────────

def test_background_weather_slot_excluded_from_salient(fresh_db):
    memapi.set_state({"operator_name": "Ricart", "location": "Valencia"})
    writer.insert_memory("Tiempo en Soria ahora: 28.6°C, despejado.", level="mid", kind="note",
                         slot="weather:soria", importance=0.9, weight=1.0)   # deliberately high salience
    blob = " ".join(m["text"].lower() for m in memapi.salient_long(limit=8))
    assert "soria" not in blob, "weather:soria NO debe entrar al bloque pasivo saliente"


def test_background_slot_not_in_composed_state_but_retrievable(fresh_db):
    memapi.set_state({"operator_name": "Ricart", "location": "Valencia"})
    writer.insert_memory("Tiempo en Soria ahora: 28.6°C, despejado.", level="mid", kind="note",
                         slot="weather:soria", importance=0.9, weight=1.0)
    block, _op, _st = memapi.compose_state(mission_fallback="misión")
    low = block.lower()
    assert "valencia" in low, "el bloque de estado DEBE mostrar la ciudad del operador"
    assert "soria" not in low, "el bloque de estado NO debe filtrar el weather de OTRA ciudad (secuestro)"
    # the data has NOT been lost: it remains live and explicitly queryable by its slot
    n = memdb.get_db().query_one(
        "SELECT count(*) c FROM memories WHERE slot='weather:soria' AND valid=1")["c"]
    assert n == 1, "el slot de fondo debe seguir vivo (subordinado, no borrado)"


def test_operator_profile_slot_still_surfaces(fresh_db):
    # inverse regression: an OPERATOR slot (with '.') still appears in the passive block (do not over-exclude it)
    memapi.set_state({"operator_name": "Ricart"})
    writer.insert_memory("Su objetivo es correr una maratón.", level="long", kind="fact",
                         slot="goal.current", importance=0.9, weight=1.0)
    blob = " ".join(m["text"].lower() for m in memapi.salient_long(limit=8))
    assert "maraton" in blob or "maratón" in blob, "un slot del operador (.) NO debe excluirse del pasivo"
