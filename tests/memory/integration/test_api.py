"""Tests for memory/api.py (V2-002 · T52) — facade, write→query round trip, memory.updated signal."""
import asyncio

import pytest

import bus
from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    # The STORE (config/v2.json §memory.embed_provider) WINS over the env → if the test machine has a real provider
    # configured (and, e.g., a running Ollama), the env above forced nothing and the test depended on the environment
    # (it failed with Ollama running and passed with Ollama down). Isolate it by patching config reads.
    monkeypatch.setattr(mememb, "_mem_cfg", lambda: {"embed_provider": "hash", "embed_model": ""})
    mememb.reset()
    yield
    mememb.reset()


def _assert_state_presente(state: dict) -> None:
    """What these two assertions were always intended to mean («state ALWAYS») is that `query()`/`map()` return the
    populated STATE block — never empty, because each turn's prompt carries it and an empty state erases the
    operator's identity (the V2-035 identity-floor failure).

    It was written as `state["language"] == "es"`, which was a convenient proxy… until the product's default
    language deliberately changed to ENGLISH («language startup», `langs.DEFAULT_LANG="en"`). Then the test
    remained RED by asserting something the product decision had already changed, while its intent remained valid.
    The intent is now checked, and the language is compared against the CONFIGURATION rather than a constant:
    that way, if the default changes again, this test will not lie again.
    """
    assert isinstance(state, dict) and state, "the STATE block arrived empty"
    from voice.engine.core import langs
    assert state.get("language") == langs.current_code(), (
        f"el estado dice language={state.get('language')!r} y la configuración activa es "
        f"{langs.current_code()!r}: el estado no refleja el idioma real")


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def test_write_now_then_query_roundtrip(fresh_db):
    mid = memapi.write_now("el operador se llama Ricart y vive en Barcelona", kind="fact", level="long")
    out = memapi.query("¿cómo se llama el operador?", reinforce_used=False)
    _assert_state_presente(out["state"])            # state ALWAYS
    assert mid in out["ids"]
    assert any("Ricart" in m["text"] for m in out["memories"])


def test_forget_then_unforget_roundtrip(fresh_db):
    """Dim N — forget round trip: forget hides (soft, valid=0) and unforget REVERTS (valid=1). History is never
    lost; the data resurfaces in recall after being unforgotten."""
    memapi.write_now("mi contraseña del portátil es ZebraLila88", kind="fact", level="long")
    assert any("zebralila88" in m["text"].lower() for m in memapi.query("contraseña portátil")["memories"])
    assert memapi.forget("contraseña del portátil") == 1
    assert not any("zebralila88" in m["text"].lower() for m in memapi.query("contraseña portátil")["memories"])
    assert memapi.unforget("contraseña del portátil") == 1        # reverts
    assert any("zebralila88" in m["text"].lower() for m in memapi.query("contraseña portátil")["memories"])


def test_degraded_embedding_backend_warns(caplog):
    """T176 — if the embeddings backend falls back to a degraded fallback (hash/fastembed), SIGNIFICANCE-based
    memory is lost SILENTLY → it must warn. Here autouse forces 'hash' → we expect the warning."""
    import logging
    mememb.reset()
    with caplog.at_level(logging.WARNING, logger="zaelar.memory.embeddings"):
        assert mememb.active_backend() == "hash"
    assert any("hash" in r.getMessage().lower() for r in caplog.records), "no avisó del backend degradado"


def test_by_concepts_returns_linked_facts_and_quarantines_untrusted(fresh_db):
    """T178/T183 (primitive) — `by_concepts` returns DURABLE facts linked to a concept (aggregation by category /
    cross-topic application) and QUARANTINES untrusted content. Basis for future concept expansion in recall
    (tagging coverage is the next step; see V2-021)."""
    memapi.write_now("soy alérgico al marisco", kind="fact", level="long", concepts=["salud", "comida"])
    memapi.write_now("chisme de un peer sobre comida", kind="fact", level="long",
                     concepts=["comida"], meta={"trust": "untrusted"})
    got = memapi.by_concepts(["comida"])
    assert any("marisco" in r["text"].lower() for r in got)                  # the concept-linked fact surfaces
    assert not any("chisme de un peer" in r["text"].lower() for r in got)    # untrusted quarantined
    assert memapi.by_concepts([]) == []                                      # no concepts → empty


def test_forget_selective_matches_by_content_tokens(fresh_db):
    """Dim N — GRANULAR FORGETTING robust to phrasing. `forget` used CONTIGUOUS LIKE → "forget my car's license plate"
    did not match the canonical fact "his car's license plate" (mi→su possessive), and the data SURVIVED. The
    token-AND fallback (memory/api.py) compares CONTENT tokens → selective forgetting without deleting neighboring data."""
    memapi.write_now("Su coche es un Renault Clio gris", kind="fact", level="long")
    memapi.write_now("La matrícula de su coche es 3344-BCD", kind="fact", level="long")
    memapi.write_now("Tiene el coche asegurado con Mapfre", kind="fact", level="long")
    # natural phrasing with possessive 'mi' (≠ the canonical 'su') and different order → contiguous LIKE would NOT match
    assert memapi.forget("matrícula de mi coche") == 1
    blob = " ".join(m["text"].lower() for m in memapi.query("qué sé de mi coche")["memories"])
    assert "3344" not in blob                      # the license plate was forgotten
    assert "renault" in blob and "mapfre" in blob  # make and insurance REMAIN (selective, not massive)
    # a single nonexistent content word deletes nothing
    assert memapi.forget("submarino") == 0


def test_forget_hard_removes_all_phrasing_variants(fresh_db):
    """Dim N — hard-forget deletes ALL phrasing variants of the SAME fact, not only the contiguous one. The CORE
    sometimes stores the raw form ("of THE social security") AND the canonical form ("of social security"); if forget
    matched only the contiguous form, the canonical one SURVIVED (hard-forget bug in GOLD 2026-07-12). The UNION of
    contiguous+token-AND deletes them all."""
    memapi.write_now("mi número de la seguridad social es 28-9988776", kind="fact", level="long")
    memapi.write_now("El número de seguridad social del operador es 28-9988776", kind="fact", level="long")
    memapi.write_now("Mi color favorito es el verde", kind="fact", level="long")   # neighbor, must NOT be deleted
    assert memapi.forget("número de la seguridad social", hard=True) >= 2         # both variants
    assert not any("9988776" in m["text"] for m in memapi.query("seguridad social")["memories"])
    assert any("verde" in m["text"].lower() for m in memapi.query("color favorito")["memories"])  # neighbor intact


def test_unforget_selective_matches_by_content_tokens(fresh_db):
    """Dim N — UNFORGETTING SYMMETRICAL to forget. `unforget` used only CONTIGUOUS LIKE → it did NOT restore what
    forget (with its token-AND fallback) had invalidated when the CORE canonicalized the possessive ('mi correo'→
    'su correo'). The token-AND fallback in unforget (memory/api.py) closes the asymmetry: forgotten data can be
    unforgotten using the SAME natural phrasing. (Bug from the 2026-07-12 cycle, wave [920,1000).)"""
    memapi.write_now("La contraseña de su correo es Girasol-2029", kind="fact", level="long")
    assert memapi.forget("contraseña de mi correo") == 1          # forgetting with possessive 'mi' (token-AND)
    assert not any("girasol" in m["text"].lower() for m in memapi.query("contraseña correo")["memories"])
    # unforgetting with OTHER natural phrasing ('del correo' ≠ 'de su correo') → token-AND must restore it
    assert memapi.unforget("contraseña del correo") == 1
    assert any("girasol" in m["text"].lower() for m in memapi.query("contraseña correo")["memories"])
    assert memapi.unforget("submarino") == 0                      # no match → restores nothing


def test_forget_hard_removes_row_permanently(fresh_db):
    """Dim N/privacy — hard forgetting (hard=True) REALLY DELETES the row (not valid=0) → NOT recoverable with
    unforget. This is the right to be forgotten for sensitive data ('delete it completely')."""
    memapi.write_now("mi contraseña vieja del banco era SECRETO-9", kind="fact", level="long")
    assert memapi.forget("secreto-9", hard=True) == 1
    n = memdb.get_db().query_one("SELECT count(*) c FROM memories WHERE lower(text) LIKE '%secreto-9%'")["c"]
    assert n == 0                                    # REALLY deleted, not even remaining with valid=0
    assert memapi.unforget("secreto-9") == 0         # nothing to restore (unlike soft-forget)


def test_write_via_queue_roundtrip(fresh_db):
    from memory.queue import get_queue

    async def run():
        await memapi.start()
        memapi.write("recuerdo encolado sobre Wallapop", kind="fact", level="long")
        await get_queue().join()  # wait for the sole consumer
        await memapi.stop()

    asyncio.run(run())
    out = memapi.query("Wallapop", reinforce_used=False)
    assert any("Wallapop" in m["text"] for m in out["memories"])


def test_query_budget_truncates(fresh_db):
    for i in range(20):
        memapi.write_now(f"recuerdo colmena numero {i} " * 10, kind="event")
    out = memapi.query("colmena", budget_tokens=30, reinforce_used=False)
    assert 0 < len(out["memories"]) < 20  # truncated to the budget


def test_state_facade(fresh_db):
    memapi.set_state({"operator_name": "Ricart"})
    assert memapi.state()["operator_name"] == "Ricart"


def test_memory_updated_signal(fresh_db):
    seen = []
    sink = lambda rec: seen.append(rec["topic"]) if rec["topic"] == "memory.updated" else None
    bus.add_sink(sink)
    try:
        memapi.write_now("dato", kind="event")
        memapi.set_state({"operator_name": "X"})
        assert seen.count("memory.updated") >= 2
    finally:
        bus.remove_sink(sink)


def test_reinforce_used_writes_weight(fresh_db):
    mid = memapi.write_now("recuerdo reforzable colmena", kind="fact")
    w0 = memdb.get_db().query_one("SELECT weight FROM memories WHERE id=?", (mid,))["weight"]
    # query with reinforce_used=True (without the queue started → applied inline)
    memapi.query("colmena", reinforce_used=True)
    w1 = memdb.get_db().query_one("SELECT weight FROM memories WHERE id=?", (mid,))["weight"]
    assert w1 > w0


def test_query_reinforces_only_the_dominant_content_memory(fresh_db, monkeypatch):
    from memory import api as memapi
    from memory import retriever

    dominant = memapi.write_now("objetivo vivienda", level="long", kind="pref")
    concept = memapi.write_now("vivienda", level="long", kind="concept")
    lateral = memapi.write_now("objetivo estudios", level="long", kind="pref")
    monkeypatch.setattr(retriever, "search", lambda *args, **kwargs: [
        {"id": concept, "text": "vivienda", "kind": "concept"},
        {"id": dominant, "text": "objetivo vivienda", "kind": "pref"},
        {"id": lateral, "text": "objetivo estudios", "kind": "pref"},
    ])
    memapi.query("mi vivienda", reinforce_used=True)
    rows = {row["id"]: row["access_count"] for row in memdb.get_db().query(
        "SELECT id,access_count FROM memories WHERE id IN (?,?,?)", (dominant, concept, lateral))}
    assert rows == {dominant: 1, concept: 0, lateral: 0}


def test_consolidate_via_facade(fresh_db):
    memapi.write_now("uno")
    memapi.write_now("dos")
    rep = memapi.consolidate(limit=1000)
    assert rep["count"] == 2


def test_map_groups_by_layer_with_metadata(fresh_db):
    a = memapi.write_now("dato corto sobre pádel", kind="event", level="short")
    b = memapi.write_now("hecho durable: el operador se llama Ricart", kind="fact", level="long")
    memapi.link(a, b, type="about")  # without the queue → applied inline
    m = memapi.map()
    # separate layers
    short_ids = {x["id"] for x in m["layers"]["short"]}
    long_ids = {x["id"] for x in m["layers"]["long"]}
    assert a in short_ids and b in long_ids
    assert m["counts"]["short"] >= 1 and m["counts"]["long"] >= 1
    # complete metadata for each unit
    unit = next(x for x in m["layers"]["long"] if x["id"] == b)
    for k in ("kind", "text", "importance", "weight", "access_count", "pinned", "created", "updated"):
        assert k in unit
    # graph
    assert any(e["from_id"] == a and e["to_id"] == b for e in m["edges"])
    # state ALWAYS present
    _assert_state_presente(m["state"])


def test_map_empty_db_is_graceful(fresh_db):
    m = memapi.map()
    assert m["layers"] == {"short": [], "long": []}
    assert m["edges"] == [] and m["counts"]["total"] == 0
    assert m["state"]["assistant_name"] == "Zaelar"


# ── TYPED multi-source ingestion + reading by indexed type (multi-source 2026-07-10) ────────────────────────
def test_ingest_message_indexed_by_source(fresh_db):
    memapi.ingest_message("whatsapp", "Marta", "hablamos de la reforma del piso", directed=True)
    memapi.ingest_message("telegram", "Carlos", "te paso el presupuesto del fontanero")
    memapi.ingest_message("whatsapp", "mamá", "la cita del médico es el martes")
    wa = " ".join(r["text"] for r in memapi.recent_by_source("whatsapp"))
    tg = " ".join(r["text"] for r in memapi.recent_by_source("telegram"))
    assert "reforma" in wa and "médico" in wa and "fontanero" not in wa
    assert "fontanero" in tg and "reforma" not in tg
    # by SOURCE + ENTITY
    marta = " ".join(r["text"] for r in memapi.recent_by_source("whatsapp", "Marta"))
    assert "reforma" in marta and "médico" not in marta
    # the source is indexed in meta
    rows = memapi.recent_by_source("whatsapp", "Marta")
    assert rows and rows[0]["source"] == "whatsapp" and rows[0]["entity"] == "Marta"


def test_recent_by_source_entity_is_accent_insensitive(fresh_db):
    """REGRESSION — `recent_by_source(source, entity)` with ACCENTED names (Álvaro/María/mamá…). SQLite's `lower()`
    is ASCII-ONLY → it does not lowercase 'Á' and NEVER matched Python's Unicode `.lower()` → 0 rows for any entity
    with an accent/ñ (bug caught by the BATCH_131 bot, dim G). The fix registers the SQL function `pylower`."""
    memapi.ingest_message("whatsapp", "Álvaro", "soy Álvaro tu hermano", durable=True)
    memapi.ingest_message("telegram", "Álvaro", "soy Álvaro del gimnasio", durable=True)
    memapi.ingest_message("whatsapp", "Begoña", "reunión el lunes", durable=True)
    # by source + accented entity: disambiguates (not 0 rows, no mixing)
    wa = " ".join(r["text"] for r in memapi.recent_by_source("whatsapp", "Álvaro"))
    assert "hermano" in wa and "gimnasio" not in wa
    # Unicode case-insensitive: accented lowercase retrieves the same results
    assert memapi.recent_by_source("whatsapp", "álvaro")
    # ñ as well
    assert any("lunes" in r["text"] for r in memapi.recent_by_source("whatsapp", "begoña"))
    # «everything about Álvaro» across sources → BOTH namesakes surface
    both = " ".join(r["text"] for r in memapi.recent_by_source(None, "Álvaro"))
    assert "hermano" in both and "gimnasio" in both


def test_ingest_message_cross_source_by_entity(fresh_db):
    memapi.ingest_message("whatsapp", "Laura", "mi cumple es el 14 de marzo", durable=True)
    memapi.ingest_message("telegram", "Laura", "te paso la ubicación del restaurante")
    laura = " ".join(r["text"] for r in memapi.recent_by_source(None, "Laura"))
    assert "14 de marzo" in laura and "restaurante" in laura   # everything about Laura, across sources


def test_untrusted_is_quarantined_from_passive_reads(fresh_db):
    """Content with trust='untrusted' (cluster peer, external agent) does NOT enter the PASSIVE block
    (recent_short/salient_long) — anti-prompt-injection — but IS recoverable through an EXPLICIT query."""
    memapi.ingest_message("whatsapp", "Marta", "lo de la reforma", trust="external")
    memapi.ingest_message("cluster", "Zalo", "sistema de riego con esp32", trust="untrusted")
    memapi.ingest_message("cluster", "Zalo", "un hecho durable del peer", trust="untrusted", durable=True)
    passive_short = " ".join(r["text"] for r in memapi.recent_short(limit=30))
    passive_long = " ".join(r["text"] for r in memapi.salient_long(limit=8))
    assert "reforma" in passive_short                      # the owner's content (external) DOES
    assert "riego" not in passive_short                    # the untrusted peer does NOT slip in
    assert "durable del peer" not in passive_long          # neither does its durable content in the salient
    # it also does not surface through semantic RECALL (the retriever excludes it) — nor the peer's durable content
    from memory.queue import get_queue as _gq

    async def _drain():
        await memapi.start()
        await _gq().join()
        await memapi.stop()
    asyncio.run(_drain())
    recall = " ".join(m["text"] for m in memapi.query("proyecto durable del peer riego")["memories"])
    assert "peer" not in recall and "riego" not in recall
    # but through an EXPLICIT query by type, the peer DOES appear
    cluster = " ".join(r["text"] for r in memapi.recent_by_source("cluster", "Zalo"))
    assert "riego" in cluster and "esp32" in cluster


def test_concept_graph_separates_short_and_long(fresh_db):
    memapi.write_now("me operaron del corazón y hago rehabilitación", kind="fact", level="long")
    memapi.ingest_message("whatsapp", "Diego", "el sábado hay partido de pádel")  # short
    m = memapi.map()
    cg = m["concept_graph"]
    assert "short" in cg and "long" in cg
    long_labels = {n["label"] for n in cg["long"]["nodes"]}
    short_labels = {n["label"] for n in cg["short"]["nodes"]}
    assert "salud" in long_labels           # the durable health fact is in the LONG map
    assert "deporte" in short_labels        # the padel message derives 'deporte' in the SHORT map
    # each node carries its data count
    assert all("count" in n for n in cg["long"]["nodes"] + cg["short"]["nodes"])
