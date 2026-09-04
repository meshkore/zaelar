"""Tests for memory/consolidator.py (V2-002 · T49) — decay, eviction (pinned untouchable), dedup, promotion."""
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
    # WINDOW-based decay (2026-07-20): Δt = now − max(last_access, last cycle) → we seed the marker 10 days
    # back so that the window covers the entire period of inactivity (without a marker, the first decay only initializes it).
    memcons._kv_set("decay_last_run", str(now - 10 * 86400))
    memcons.decay(now=now, lam=0.1)  # high λ to see the effect: factor ≈ e^-1
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
    assert wf > ws  # the recent one (recent access) decays much less


def test_evict_only_over_limit(fresh_db):
    for i in range(3):
        memwriter.insert_memory(f"m{i}", weight=0.5)
    assert memcons.evict(limit=10) == 0  # below the limit → deletes nothing
    assert memcons.count() == 3


def test_evict_removes_lowest_weight(fresh_db):
    a = memwriter.insert_memory("bajo", weight=0.1)
    b = memwriter.insert_memory("alto", weight=0.9)
    removed = memcons.evict(limit=1)
    assert removed == 1
    ids = {r["id"] for r in memdb.get_db().query("SELECT id FROM memories")}
    assert a not in ids and b in ids  # the one with the lower weight is gone


def test_pinned_never_evicted(fresh_db):
    pin = memwriter.insert_memory("clave del ledger", weight=0.01, pinned=True)  # negligible weight but pinned
    for i in range(3):
        memwriter.insert_memory(f"relleno{i}", weight=0.9)
    memcons.evict(limit=1)  # forces extensive forgetting
    ids = {r["id"] for r in memdb.get_db().query("SELECT id FROM memories")}
    assert pin in ids  # the pinned item ALWAYS survives
    # and only the pinned item remains if everything else was deletable
    assert memcons.count() == 1


# V2-103 (2026-08-16): the only previous eviction test used 1–4 hand-made rows — it never tested the ORDER of
# sacrifice at a realistic volume (hundreds/thousands of rows, with mixed weights/salience/pinned), which is where a
# regression in the `ORDER BY` or in the salience criterion (`_SALIENT_IMPORTANCE`) would be invisible in such a
# small fixture but real at production scale.
def test_evict_at_scale_preserves_salient_and_pinned_order(fresh_db):
    import random
    rnd = random.Random(42)
    pinned_ids = set()
    salient_ids = set()   # important OR with slot OR kind profile/pref — protected UNTIL the end
    trivia_ids = set()    # the rest — sacrificed first

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

    # lower the limit until only the trivia and some of the salient items fit (never the pinned items)
    removed = memcons.evict(limit=250)
    assert removed == total - 250
    remaining = {r["id"] for r in memdb.get_db().query("SELECT id FROM memories")}
    assert memcons.count() == 250

    assert pinned_ids <= remaining, "ningún pinned puede desaparecer, a cualquier escala"
    # with 600 trivia rows and only 250 slots, ALL trivia must be gone before touching the salient items
    survivors_are_trivia = remaining & trivia_ids
    assert not survivors_are_trivia, "la trivia se sacrifica ENTERA antes de tocar una sola fila saliente"
    # of the salient items (300) + pinned items (20) = 320 "protected" candidates for 250 slots → 70
    # lower-weight salient items were sacrificed, never the pinned items
    survivors_salient = remaining & salient_ids
    assert len(survivors_salient) == 250 - len(pinned_ids)


def test_dedup_merges_identical_text(fresh_db):
    a = memwriter.insert_memory("El Operador  se llama Ricart", weight=0.5)
    b = memwriter.insert_memory("el operador se llama ricart", weight=0.8)  # same normalized form
    c = memwriter.insert_memory("otra cosa", weight=0.5)
    removed = memcons.dedup()
    assert removed == 1
    ids = {r["id"] for r in memdb.get_db().query("SELECT id FROM memories")}
    assert b in ids and c in ids and a not in ids  # keeps the one with the higher weight (b)


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
    # NONE, not 0 (audit 2026-08-23). Worker-ledger cleanup is now INJECTED, and this report
    # distinguishes two facts that previously looked identical: `0` means “I looked and there was nothing to clean”, `None` means
    # “nobody gave me anything to look at”. A caller that forgets to inject the hook would see a perfectly
    # normal report while the ledger grows without limit — the way a function can silently get lost. This assert
    # used to say `== 0` because it captured the lazy fail-open import that existed before.
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
    assert rows[ephemeral]["valid"] == 0  # expires from active memory
    assert rows[pinned]["valid"] == 1     # a critical pinned item never expires


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
    """The other half: without it, “returns None” is satisfied by never calling the hook."""
    llamadas = []

    def _prune(now=None):
        llamadas.append(now)
        return 7

    rep = memcons.consolidate(limit=1000, prune_workers_fn=_prune)
    assert rep["workers_pruned"] == 7
    assert len(llamadas) == 1, "el hook tiene que llamarse UNA vez, con el reloj del ciclo"


def test_y_un_hook_que_revienta_NO_tumba_el_ciclo(fresh_db):
    """Fail-open, just like the lazy import it replaces: ledger hygiene is not memory."""
    def _boom(now=None):
        raise RuntimeError("ledger inalcanzable")

    rep = memcons.consolidate(limit=1000, prune_workers_fn=_boom)
    assert rep["workers_pruned"] is None
    assert "count" in rep, "el informe tiene que seguir completo"


def test_dedup_never_merges_across_the_trust_boundary(fresh_db):
    """2026-09-05: identical text said by the operator and by quarantined external material (`trust: untrusted`)
    are TWO facts. Merging them can let the untrusted row survive and inherit the trusted lineage's edges and
    reinforcement — the trust class now splits the dedup group."""
    a = memwriter.insert_memory("la clave del garaje es 4321", level="long", kind="fact", weight=0.3)
    b = memwriter.insert_memory("la clave del garaje es 4321", level="long", kind="fact", weight=0.9,
                                meta={"trust": "untrusted"})
    assert memcons.dedup() == 0
    db = memdb.get_db()
    assert db.query_one("SELECT COUNT(*) c FROM memories WHERE id IN (?,?)", (a, b))["c"] == 2


def test_prune_deindexes_a_pinned_invalid_shell(fresh_db):
    """2026-09-05 (measured live: a superseded pinned profile row kept its vector forever): `pinned` protects a
    row from DELETION, not from de-indexing. An invalid pinned shell leaves the indexes like any other; its
    `memories` row stays, so history is intact and `unforget(include_pinned=True)` can still revive it."""
    mid = memwriter.insert_memory("me llamo Ricard", level="long", kind="profile", pinned=True)
    db = memdb.get_db()
    assert db.query_one("SELECT 1 x FROM vec_memories WHERE memory_id=?", (mid,)) is not None
    old = int(time.time()) - 3 * 86400
    db.execute("UPDATE memories SET valid=0, updated=? WHERE id=?", (old, mid))
    assert memcons.prune_invalid() == 1
    assert db.query_one("SELECT 1 x FROM vec_memories WHERE memory_id=?", (mid,)) is None
    assert db.query_one("SELECT 1 x FROM memories WHERE id=?", (mid,)) is not None  # the row itself survives
