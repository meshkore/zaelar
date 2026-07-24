#
# test_location_grounding.py — auditoría de memoria 2026-07-14 (hallazgos del auditor post-V2-038):
#   (1) supersede por SLOT que colapsa alias LEGACY inmediatamente (operator.location vs 'location'/'ubicacion'
#       crudos) → una sola píldora de ubicación vigente, el más reciente MANDA, cero contradicciones;
#   (2) los SLOTS DE FONDO namespaced (weather:soria del widget) quedan SUBORDINADOS a state.location: NO entran
#       al bloque pasivo del estado (que se pinta "dalo por sabido sin buscar") — así "¿qué tiempo hace hoy?" no
#       queda secuestrado por la ciudad equivocada — pero SIGUEN recuperables por consulta explícita.
# Determinista: sin red (embeddings hash) ni LLM (MEM_PROCESSOR=0). Ejecutar:
#   .venv/bin/pytest tests/unit/memory/test_location_grounding.py -q
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


# ── FIX #1 · supersede por SLOT colapsa por alias, inmediato ───────────────────────────────────────────────

def test_equivalent_keys_expands_aliases():
    keys = memslots.equivalent_keys("operator.location")
    assert "operator.location" in keys
    assert "location" in keys and "ubicacion" in keys and "city" in keys
    # un slot namespaced/desconocido no expande (solo él mismo)
    assert memslots.equivalent_keys("weather:soria") == ["weather:soria"]


def test_legacy_location_key_collapses_on_new_write(fresh_db):
    # píldora LEGACY con clave CRUDA 'location' (pre-normalización) + una 'ubicacion' → conviven hasta que...
    writer.insert_memory("El operador vive en Soria.", level="long", kind="profile", slot="location")
    writer.insert_memory("Ubicación registrada: Bilbao.", level="long", kind="profile", slot="ubicacion")
    # ...la mudanza con la clave CANÓNICA colapsa TODAS las variantes de golpe (el más reciente MANDA).
    writer.insert_memory("Vive en Valencia.", level="long", kind="profile", slot="operator.location")
    pills = _valid_location_pills()
    assert len(pills) == 1, f"esperaba 1 píldora de ubicación vigente, hay {len(pills)}: {pills}"
    assert "valencia" in pills[0][1].lower()
    assert pills[0][0] == "operator.location"       # clave canónica única


def test_repeated_same_fact_stays_single(fresh_db):
    # N ingestas del MISMO hecho canónico (fraseos distintos) → 1 sola píldora vigente (punto 3 del auditor)
    for txt in ("Vivo en Valencia.", "Mi ciudad es Valencia.", "Ahora vivo en Valencia."):
        writer.insert_memory(txt, level="long", kind="profile", slot="operator.location")
    pills = _valid_location_pills()
    assert len(pills) == 1, f"hubo duplicación por ingestas repetidas: {pills}"


# ── FIX #2 · slots de FONDO subordinados a state.location ──────────────────────────────────────────────────

def test_background_weather_slot_excluded_from_salient(fresh_db):
    memapi.set_state({"operator_name": "Ricart", "location": "Valencia"})
    writer.insert_memory("Tiempo en Soria ahora: 28.6°C, despejado.", level="mid", kind="note",
                         slot="weather:soria", importance=0.9, weight=1.0)   # alta saliencia a propósito
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
    # el dato NO se ha perdido: sigue vivo y consultable explícitamente por su slot
    n = memdb.get_db().query_one(
        "SELECT count(*) c FROM memories WHERE slot='weather:soria' AND valid=1")["c"]
    assert n == 1, "el slot de fondo debe seguir vivo (subordinado, no borrado)"


def test_operator_profile_slot_still_surfaces(fresh_db):
    # regresión inversa: un slot del OPERADOR (con '.') SÍ sigue en el bloque pasivo (no lo excluimos de más)
    memapi.set_state({"operator_name": "Ricart"})
    writer.insert_memory("Su objetivo es correr una maratón.", level="long", kind="fact",
                         slot="goal.current", importance=0.9, weight=1.0)
    blob = " ".join(m["text"].lower() for m in memapi.salient_long(limit=8))
    assert "maraton" in blob or "maratón" in blob, "un slot del operador (.) NO debe excluirse del pasivo"
