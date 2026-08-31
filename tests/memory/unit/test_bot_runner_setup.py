"""tests/memory/e2e/bot/runner.py — two real bugs in the `scale_eval` harness, caught while repopulating the corpus
(V2-031, 2026-08-17) after resolving the embedding backend instability: the measurement was still unreliable
for two completely different reasons, both in the harness setup and neither in the retriever.

1. `_setup_env()` never loaded `.meshkore/credentials/zaelar.env` (only `.env`) — `scale_eval.py` did
   (twin code, never mirrored). `DEEPSEEK_API_KEY` exists only in the credential store → unresolved →
   `nucleo/provider_keys.py::key_for_endpoint` falls back to its `"local"` sentinel → DeepSeek returned 401 on every
   CORE call → silent heuristic fallback. Reproduced live by invoking this runner through its documented CLI.
2. A fresh database did not set `state.language` — it inherited the product default `"en"` (85b4922, language
   startup 2026-08-14), and `mem_processor._render` reads it to decide which language to distill into. The corpus is
   written in Spanish; without this seed, `--fresh` wrote the entire memory in English and the harness saw
   "write miss" case after case because the Spanish `want` never matched English text.

 A third, distinct, and more serious bug was found later while measuring `scale_eval` with the previous two
fixed (V2-031, 2026-08-17, dimension C — deep retention): `_do_consolidate()` (BATCH_45, dim L,
"AGGRESSIVE pruning keep=120") ran `memory.consolidate(limit=120)` DIRECTLY on `zaelar.membot.db`, the
SHARED and cumulative corpus, at case ~382 of 579. With hundreds of facts already written by previous batches
 (including BATCH_9 "tareas encargadas"), `evict()` performed a HARD DELETE of everything not pinned below
the limit — real collateral damage, verified live: "Búscame vuelos a Tokio…" and 4 other BATCH_9 commissioned
tasks disappeared WITHOUT A TRACE (not even `valid=0` — the rows were actually deleted). The test's own
`keep` item (a pinned one) always survived, so nothing in the local assertion revealed the destruction — only
`dimension C`, measured MANY cases later against the corpus's FINAL state, saw it as a "write miss". Fix:
`_do_consolidate` now isolates pruning with snapshot-and-restore (WAL checkpoint → copy the
file → actual pruning, the assertion remains real → restore the snapshot). Critical ordering verified live:
the SQLite connection must be CLOSED before overwriting the file — doing so with the connection open
left the restore incomplete (the subsequent `close()` flushed its own cache over it).
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
    monkeypatch.setattr("nucleo.mem_processor.enabled", lambda: False)  # heuristic, no network
    asyncio.run(runner.run_range(0, 1, fresh=True))
    assert memapi.state().get("language") == "es", \
        f"una BD fresca del bot debe nacer en español (corpus español), no en el default de producto: {memapi.state().get('language')!r}"


def test_do_consolidate_isolates_the_shared_corpus(fresh_db):
    """Reproduce real collateral damage: a fact UNRELATED to the consolidation test (equivalent to BATCH_9)
    must survive intact through aggressive pruning run for a DIFFERENT batch (BATCH_45)."""
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
    """The `keep`/pinned assertion remains REAL (not a no-op): under real pruning pressure, the
    report (`detail`, calculated WITHIN the isolated snapshot before restoration) must show that the number
    of valid entries genuinely dropped to the limit — if it evicted nothing, "pinned survives" would prove nothing."""
    for j in range(20):
        memapi.write_now(f"nota de relleno {j}: detalle rutinario e irrelevante", level="long", kind="event",
                         importance=0.3)
    memapi.write_now("Soy Bartolomé Quesadilla y es importante.", level="long", kind="profile",
                     importance=0.95, pinned=True)

    ok, detail = runner._do_consolidate(memapi, {"limit": 5, "keep": "quesadilla"})
    assert ok, detail
    assert "→5 válidos" in detail, f"la poda DENTRO del snapshot aislado debe ser real (bajar hasta el límite): {detail}"


def test_superseded_blob_excludes_legitimately_replaced_slot_values(fresh_db):
    """scale_eval._superseded_blob() must capture a slot value INVALIDATED by a LATER write to the
    same slot (real writer supersede) — not a value lost because of a bug, but the usual "latest wins" rule.
    Reproduces the real pattern (operator.car/job/hardware/name with up to 15 values in the corpus)."""
    memapi.write_now("Tiene un coche Toyota híbrido.", level="long", kind="fact", slot="operator.car")
    memapi.write_now("Tiene una moto como vehículo actual.", level="long", kind="fact", slot="operator.car")
    blob = scale_eval._superseded_blob()
    assert "toyota" in blob
    assert "moto" not in blob, "el valor VIGENTE no debe aparecer en el blob de superados"


def test_evaluate_excludes_superseded_queries_from_n(fresh_db, monkeypatch):
    """Una query cuyo `want` solo casa un valor de slot ya superado no debe contar como write_miss ni entrar
    en `n` — no es medible con justicia contra el estado final."""
    memapi.write_now("Tiene un coche Toyota híbrido.", level="long", kind="fact", slot="operator.car")
    memapi.write_now("Tiene una moto como vehículo actual.", level="long", kind="fact", slot="operator.car")

    def _fake_long_queries():
        return [{"q": "¿qué coche tengo?", "via": "long", "want": ["toyota"], "dim": "TEST"}]

    monkeypatch.setattr(scale_eval, "_long_queries", _fake_long_queries)
    monkeypatch.setattr("memory.retriever.search", lambda *a, **k: [])
    rep = scale_eval.evaluate()
    assert rep["n"] == 0, f"la query sobre un valor superado debe excluirse de n, no contar como miss: {rep}"
    assert rep["superseded_excluded"] == 1
    assert rep["write_miss"] == 0


def test_long_queries_excludes_stale_by_design_cases():
    """`scale_eval._long_queries()` measures against the corpus's FINAL STATE — a `want` that is correct only
    POSITIONALLY (a later batch supersedes the same slot for another purpose, e.g.
    reused operator.phone/operator.hardware) must be excluded, or the count reports a false miss."""
    qs = scale_eval._long_queries()
    assert all(not c.get("stale_by_design") for c in qs)
    phone = [c for c in qs if c.get("q") == "¿Cuál es mi número de teléfono?"]
    assert phone == [], "el case del teléfono marcado stale_by_design se coló en _long_queries()"
    dog_name = [c for c in qs if c.get("q") == "¿Cómo se llama mi perro?"]
    assert dog_name == [], "el case del NOMBRE del perro (Toby→Nala) marcado stale_by_design se coló"
    ssn = [c for c in qs if c.get("q") in
           ("¿cuál es mi número de la seguridad social?", "¿sigues teniendo mi número de la seguridad social?")]
    assert ssn == [], "los cases de la seguridad social (colisión con el forget genérico de dim N) se colaron"
    # V2-031 (2026-08-17): massive supersede chain for operator.car/operator.job (12/15 mutations each)
    # + the two vaulted cases (PIN, alarm code) — all must be excluded from _long_queries().
    chain_and_vault = [c for c in qs if c.get("q") in (
        "¿qué sabes de mi coche?", "¿qué coche tengo?", "¿en qué empresa trabajo?",
        "¿en qué trabajo ahora mismo?", "¿cuál es el PIN de mi tarjeta nueva?",
        "¿cuál es el código de la alarma de casa?",
    ) and c.get("want") and any(w in ("toyota", "ford", "deloitte", "profesor", "8890", "5903") for w in c["want"])]
    assert chain_and_vault == [], f"cases de cadena de slot / bóveda que se colaron: {chain_and_vault}"
