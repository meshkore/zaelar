"""Tests de memory/consolidator.py (V2-002 · T49) — decay, eviction (pinned intocable), dedup, promoción."""
import time

import pytest

from memory import consolidator as memcons
from memory import db as memdb
from memory import embeddings as mememb
from memory import writer as memwriter


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


def test_decay_lowers_weight_of_stale(fresh_db):
    now = int(time.time())
    mid = memwriter.insert_memory("dato viejo", weight=0.8)
    memdb.get_db().execute("UPDATE memories SET last_access=? WHERE id=?", (now - 10 * 86400, mid))
    # Decay por VENTANA (2026-07-20): Δt = now − max(last_access, último ciclo) → sembramos el marcador 10 días
    # atrás para que la ventana cubra toda la inactividad (sin marcador, el primer decay solo inicializa).
    memcons._kv_set("decay_last_run", str(now - 10 * 86400))
    memcons.decay(now=now, lam=0.1)  # λ alto para ver el efecto: factor ≈ e^-1
    w = memdb.get_db().query_one("SELECT weight FROM memories WHERE id=?", (mid,))["weight"]
    assert w < 0.8 and w == pytest.approx(0.8 * 2.718281828 ** -1, rel=0.02)


def test_access_resets_decay(fresh_db):
    now = int(time.time())
    stale = memwriter.insert_memory("viejo", weight=0.8)
    fresh = memwriter.insert_memory("reciente", weight=0.8)
    memdb.get_db().execute("UPDATE memories SET last_access=? WHERE id=?", (now - 20 * 86400, stale))
    memdb.get_db().execute("UPDATE memories SET last_access=? WHERE id=?", (now, fresh))
    memcons._kv_set("decay_last_run", str(now - 20 * 86400))
    memcons.decay(now=now, lam=0.1)
    ws = memdb.get_db().query_one("SELECT weight FROM memories WHERE id=?", (stale,))["weight"]
    wf = memdb.get_db().query_one("SELECT weight FROM memories WHERE id=?", (fresh,))["weight"]
    assert wf > ws  # el reciente (acceso reciente) decae mucho menos


def test_evict_only_over_limit(fresh_db):
    for i in range(3):
        memwriter.insert_memory(f"m{i}", weight=0.5)
    assert memcons.evict(limit=10) == 0  # bajo el límite → no borra nada
    assert memcons.count() == 3


def test_evict_removes_lowest_weight(fresh_db):
    a = memwriter.insert_memory("bajo", weight=0.1)
    b = memwriter.insert_memory("alto", weight=0.9)
    removed = memcons.evict(limit=1)
    assert removed == 1
    ids = {r["id"] for r in memdb.get_db().query("SELECT id FROM memories")}
    assert a not in ids and b in ids  # se fue el de menor peso


def test_pinned_never_evicted(fresh_db):
    pin = memwriter.insert_memory("clave del ledger", weight=0.01, pinned=True)  # peso ínfimo pero pinned
    for i in range(3):
        memwriter.insert_memory(f"relleno{i}", weight=0.9)
    memcons.evict(limit=1)  # fuerza mucho olvido
    ids = {r["id"] for r in memdb.get_db().query("SELECT id FROM memories")}
    assert pin in ids  # el pinned SIEMPRE sobrevive
    # y solo queda el pinned si todo lo demás era borrable
    assert memcons.count() == 1


# V2-103 (2026-08-16): el único test previo de eviction usaba 1-4 filas hechas a mano — nunca probó el ORDEN de
# sacrificio a un volumen realista (cientos/miles de filas, pesos/salience/pinned mezclados), que es donde una
# regresión en el `ORDER BY` o en el criterio de salience (`_SALIENT_IMPORTANCE`) sería invisible en un fixture
# tan pequeño pero real a escala de producción.
def test_evict_at_scale_preserves_salient_and_pinned_order(fresh_db):
    import random
    rnd = random.Random(42)
    pinned_ids = set()
    salient_ids = set()   # importante O con slot O kind profile/pref — protegido HASTA el final
    trivia_ids = set()    # el resto — se sacrifica primero

    for i in range(20):
        mid = memwriter.insert_memory(f"pin-{i}", weight=rnd.uniform(0.0, 1.0), pinned=True)
        pinned_ids.add(mid)
    for i in range(300):
        mid = memwriter.insert_memory(f"saliente-{i}", weight=rnd.uniform(0.0, 1.0),
                                      importance=rnd.uniform(0.5, 1.0), kind="fact")
        salient_ids.add(mid)
    for i in range(600):
        mid = memwriter.insert_memory(f"trivia-{i}", weight=rnd.uniform(0.0, 1.0),
                                      importance=rnd.uniform(0.0, 0.49), kind="msg")
        trivia_ids.add(mid)

    total = memcons.count()
    assert total == 920

    # baja el límite hasta que solo quepa la trivia + una parte de lo saliente (nunca lo pinned)
    removed = memcons.evict(limit=250)
    assert removed == total - 250
    remaining = {r["id"] for r in memdb.get_db().query("SELECT id FROM memories")}
    assert memcons.count() == 250

    assert pinned_ids <= remaining, "ningún pinned puede desaparecer, a cualquier escala"
    # con 600 filas de trivia y solo 250 huecos, TODA la trivia debe haberse ido antes de tocar lo saliente
    survivors_are_trivia = remaining & trivia_ids
    assert not survivors_are_trivia, "la trivia se sacrifica ENTERA antes de tocar una sola fila saliente"
    # de lo saliente (300) + pinned (20) = 320 candidatos "protegidos" para 250 huecos → se sacrificaron 70
    # salientes de menor peso, nunca los pinned
    survivors_salient = remaining & salient_ids
    assert len(survivors_salient) == 250 - len(pinned_ids)


def test_dedup_merges_identical_text(fresh_db):
    a = memwriter.insert_memory("El Operador  se llama Ricart", weight=0.5)
    b = memwriter.insert_memory("el operador se llama ricart", weight=0.8)  # mismo normalizado
    c = memwriter.insert_memory("otra cosa", weight=0.5)
    removed = memcons.dedup()
    assert removed == 1
    ids = {r["id"] for r in memdb.get_db().query("SELECT id FROM memories")}
    assert b in ids and c in ids and a not in ids  # conserva el de mayor peso (b)


def test_promote_by_age(fresh_db):
    now = int(time.time())
    old = memwriter.insert_memory("viejo corto", level="short")
    memdb.get_db().execute("UPDATE memories SET created=? WHERE id=?", (now - 5 * 86400, old))
    young = memwriter.insert_memory("corto reciente", level="short")
    rep = memcons.promote(now=now)
    assert rep["short_to_mid"] == 1
    assert memdb.get_db().query_one("SELECT level FROM memories WHERE id=?", (old,))["level"] == "mid"
    assert memdb.get_db().query_one("SELECT level FROM memories WHERE id=?", (young,))["level"] == "short"


def test_consolidate_reports(fresh_db):
    memwriter.insert_memory("uno", weight=0.5)
    memwriter.insert_memory("dos", weight=0.5)
    rep = memcons.consolidate(limit=1000)
    assert set(rep) == {
        "healed_slots", "promoted", "deduped", "decayed", "expired", "pruned", "evicted", "workers_pruned", "count"
    }
    # NONE, no 0 (auditoría 2026-08-23). La limpieza del ledger de workers pasó a INYECTARSE, y este informe
    # distingue dos hechos que antes se veían iguales: `0` es «miré y no había nada que limpiar», `None` es
    # «nadie me dio con qué mirar». Un llamante que olvide inyectar el hook vería un informe perfectamente
    # normal mientras el ledger crece sin límite — que es como una función se pierde en silencio. Este assert
    # decía `== 0` porque capturaba el import perezoso fail-open que había antes.
    assert rep["workers_pruned"] is None
    assert rep["count"] == 2


def test_consolidate_expires_ttl_but_preserves_history_and_pinned(fresh_db):
    from memory.clock import travel

    day = 1_700_000_000
    with travel(day):
        ephemeral = memwriter.insert_memory("café rutinario", level="short", ttl_days=2)
        pinned = memwriter.insert_memory("alergia crítica", level="long", ttl_days=2, pinned=True)
    with travel(day + 3 * 86400):
        rep = memcons.consolidate(limit=1000)
    assert rep["expired"] == 1
    rows = {row["id"]: row for row in memdb.get_db().query("SELECT id, valid FROM memories")}
    assert rows[ephemeral]["valid"] == 0  # expira de la memoria activa
    assert rows[pinned]["valid"] == 1     # un crítico pinned nunca caduca


def test_evict_can_delete_an_already_pruned_invalid_row_without_fts_corruption(fresh_db):
    now = int(time.time())
    mid = memwriter.insert_memory("efímero ya podado", level="short", weight=0.01)
    memdb.get_db().execute(
        "UPDATE memories SET valid=0, updated=? WHERE id=?", (now - 5 * 86400, mid))
    assert memcons.prune_invalid(now=now) == 1
    assert memcons.evict(limit=0) == 1
    assert memdb.get_db().query_one("SELECT id FROM memories WHERE id=?", (mid,)) is None
    assert memdb.get_db().query_one("SELECT COUNT(*) c FROM fts_memories")["c"] == 0


def test_con_hook_inyectado_el_informe_trae_el_NUMERO(fresh_db):
    """La otra mitad: sin ella, «devuelve None» se satisface no llamando nunca al hook."""
    llamadas = []

    def _prune(now=None):
        llamadas.append(now)
        return 7

    rep = memcons.consolidate(limit=1000, prune_workers_fn=_prune)
    assert rep["workers_pruned"] == 7
    assert len(llamadas) == 1, "el hook tiene que llamarse UNA vez, con el reloj del ciclo"


def test_y_un_hook_que_revienta_NO_tumba_el_ciclo(fresh_db):
    """Fail-open, igual que el import perezoso que sustituye: la higiene del ledger no es la memoria."""
    def _boom(now=None):
        raise RuntimeError("ledger inalcanzable")

    rep = memcons.consolidate(limit=1000, prune_workers_fn=_boom)
    assert rep["workers_pruned"] is None
    assert "count" in rep, "el informe tiene que seguir completo"
