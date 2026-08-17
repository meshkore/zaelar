"""tests/memory/e2e/bot/runner.py — dos bugs reales del arnés de `scale_eval`, cazados repoblando el corpus
(V2-031, 2026-08-17) tras cerrar la inestabilidad del backend de embedding: la medición seguía sin ser fiable
por dos motivos completamente distintos, los dos en el setup del arnés, ninguno en el retriever.

1. `_setup_env()` nunca cargaba `.meshkore/credentials/zaelar.env` (solo `.env`) — `scale_eval.py` sí lo hacía
   (código gemelo, nunca espejado). `DEEPSEEK_API_KEY` solo vive en el credential store → sin resolver →
   `nucleo/provider_keys.py::key_for_endpoint` cae a su centinela `"local"` → DeepSeek 401ea cada llamada del
   CORAZÓN → heurística silenciosa. Reproducido en vivo invocando este runner por su propia CLI documentada.
2. Una BD fresca no fijaba `state.language` — hereda el default de producto `"en"` (85b4922, arranque
   idiomático 2026-08-14) y `mem_processor._render` lo lee para decidir en qué idioma destila. El corpus está
   escrito en español; sin este seed, `--fresh` escribía la memoria entera en inglés y el harness veía
   "write miss" en case tras caso porque el `want` español nunca casaba con texto en inglés.

Un tercer bug, distinto y más grave, se encontró después midiendo `scale_eval` ya con los dos anteriores
arreglados (V2-031, 2026-08-17, dimensión C — retención profunda): `_do_consolidate()` (BATCH_45, dim L,
"poda AGRESIVA keep=120") corría `memory.consolidate(limit=120)` DIRECTAMENTE sobre `zaelar.membot.db`, el
corpus COMPARTIDO y acumulativo, en el case ~382 de 579. Con cientos de hechos ya escritos por baterías
anteriores (BATCH_9 "tareas encargadas" entre ellas), `evict()` hacía HARD DELETE de todo lo no-pinned por
debajo del límite — daño colateral real, verificado en vivo: "Búscame vuelos a Tokio…" y otras 4 tareas
encargadas de BATCH_9 desaparecían SIN DEJAR RASTRO (ni siquiera `valid=0` — filas borradas de verdad). El
propio `keep` de la prueba (un pinned) sobrevivía siempre, así que nada en la aserción local delataba el
destrozo — solo `dimension C`, medida MUCHOS casos después contra el estado FINAL del corpus, lo veía como
"write miss". Fix: `_do_consolidate` ahora aísla la poda con snapshot-and-restore (checkpoint WAL → copia el
fichero → poda de verdad, la aserción sigue siendo real → restaura el snapshot). Orden crítico verificado en
vivo: la conexión SQLite debe CERRARSE antes de sobreescribir el fichero — hacerlo con la conexión abierta
dejaba el restore a medias (el `close()` posterior volcaba su propia caché encima).
"""
from __future__ import annotations

import asyncio

import pytest

from memory import api as memapi
from memory import db as memdb
from tests.memory.e2e.bot import runner
from tests.memory.e2e.bot import scale_eval


def test_setup_env_loads_credential_store(monkeypatch):
    calls: list[str] = []

    def _fake_load_dotenv(path, override=False):
        calls.append(str(path))
        return True

    monkeypatch.setattr("dotenv.load_dotenv", _fake_load_dotenv)
    runner._setup_env()
    assert any("credentials" in c and "zaelar.env" in c for c in calls), \
        f"_setup_env no cargó el credential store (solo .env): {calls}"


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def test_run_range_seeds_spanish_before_any_case(fresh_db, monkeypatch):
    monkeypatch.setattr("nucleo.mem_processor.enabled", lambda: False)  # heurística, cero red
    asyncio.run(runner.run_range(0, 1, fresh=True))
    assert memapi.state().get("language") == "es", \
        f"una BD fresca del bot debe nacer en español (corpus español), no en el default de producto: {memapi.state().get('language')!r}"


def test_do_consolidate_isolates_the_shared_corpus(fresh_db):
    """Reproduce el daño colateral real: un hecho AJENO al test de consolidación (equivalente a BATCH_9)
    debe sobrevivir intacto a una poda agresiva ejecutada para una batería DISTINTA (BATCH_45)."""
    unrelated = memapi.write_now("Búscame vuelos a Tokio para agosto, los más baratos que encuentres.",
                                 level="long", kind="event", importance=0.55)
    for j in range(20):
        memapi.write_now(f"nota de relleno {j}: detalle rutinario e irrelevante", level="long", kind="event",
                         importance=0.3)
    memapi.write_now("Soy Bartolomé Quesadilla y es importante.", level="long", kind="profile",
                     importance=0.95, pinned=True)
    before_total = memdb.get_db().query_one("SELECT count(*) c FROM memories WHERE valid=1")["c"]
    assert before_total > 5, "hace falta presión real de poda (más filas que el límite) para que la prueba signifique algo"

    ok, detail = runner._do_consolidate(memapi, {"limit": 5, "keep": "quesadilla"})
    assert ok, detail

    db = memdb.get_db()
    after_total = db.query_one("SELECT count(*) c FROM memories WHERE valid=1")["c"]
    assert after_total == before_total, \
        f"el corpus compartido debe quedar EXACTAMENTE como estaba antes de la poda aislada ({before_total}), no {after_total}"
    row = db.query_one("SELECT valid FROM memories WHERE id=?", (unrelated,))
    assert row is not None and row["valid"] == 1, "el hecho AJENO a este test (BATCH_9-like) no puede desaparecer"


def test_do_consolidate_still_evicts_for_real_inside_the_isolated_snapshot(fresh_db):
    """La aserción de `keep`/pinned sigue siendo REAL (no un no-op): con presión real de poda, el propio
    informe (`detail`, calculado DENTRO del snapshot aislado antes de restaurar) debe mostrar que el número
    de válidos bajó de verdad hasta el límite — si no evictara nada, "pinned sobrevive" no probaría nada."""
    for j in range(20):
        memapi.write_now(f"nota de relleno {j}: detalle rutinario e irrelevante", level="long", kind="event",
                         importance=0.3)
    memapi.write_now("Soy Bartolomé Quesadilla y es importante.", level="long", kind="profile",
                     importance=0.95, pinned=True)

    ok, detail = runner._do_consolidate(memapi, {"limit": 5, "keep": "quesadilla"})
    assert ok, detail
    assert "→5 válidos" in detail, f"la poda DENTRO del snapshot aislado debe ser real (bajar hasta el límite): {detail}"


def test_long_queries_excludes_stale_by_design_cases():
    """`scale_eval._long_queries()` mide contra el ESTADO FINAL del corpus — un `want` correcto solo
    POSICIONALMENTE (una batería posterior supersede el mismo slot con otro propósito, p. ej.
    operator.phone/operator.hardware reutilizados) debe quedar fuera, o el número reporta un falso miss."""
    qs = scale_eval._long_queries()
    assert all(not c.get("stale_by_design") for c in qs)
    phone = [c for c in qs if c.get("q") == "¿Cuál es mi número de teléfono?"]
    assert phone == [], "el case del teléfono marcado stale_by_design se coló en _long_queries()"
    dog_name = [c for c in qs if c.get("q") == "¿Cómo se llama mi perro?"]
    assert dog_name == [], "el case del NOMBRE del perro (Toby→Nala) marcado stale_by_design se coló"
    ssn = [c for c in qs if c.get("q") in
           ("¿cuál es mi número de la seguridad social?", "¿sigues teniendo mi número de la seguridad social?")]
    assert ssn == [], "los cases de la seguridad social (colisión con el forget genérico de dim N) se colaron"
    # V2-031 (2026-08-17): cadena de supersede masiva de operator.car/operator.job (12/15 mutaciones cada uno)
    # + los dos cases vaulteados (PIN, código de alarma) — todos deben quedar fuera de _long_queries().
    chain_and_vault = [c for c in qs if c.get("q") in (
        "¿qué sabes de mi coche?", "¿qué coche tengo?", "¿en qué empresa trabajo?",
        "¿en qué trabajo ahora mismo?", "¿cuál es el PIN de mi tarjeta nueva?",
        "¿cuál es el código de la alarma de casa?",
    ) and c.get("want") and any(w in ("toyota", "ford", "deloitte", "profesor", "8890", "5903") for w in c["want"])]
    assert chain_and_vault == [], f"cases de cadena de slot / bóveda que se colaron: {chain_and_vault}"
