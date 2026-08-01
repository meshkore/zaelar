"""Tests de memory/api.py (V2-002 · T52) — fachada, roundtrip write→query, señal memory.updated."""
import asyncio

import pytest

import bus
from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    # El STORE (config/v2.json §memory.embed_provider) GANA sobre el env → si la máquina de test tiene un provider
    # real configurado (y p. ej. Ollama vivo), el env de arriba no forzaba nada y el test dependía del entorno
    # (fallaba con Ollama arriba, pasaba con Ollama caído). Se aísla parcheando la lectura de config.
    monkeypatch.setattr(mememb, "_mem_cfg", lambda: {"embed_provider": "hash", "embed_model": ""})
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


def test_write_now_then_query_roundtrip(fresh_db):
    mid = memapi.write_now("el operador se llama Ricart y vive en Barcelona", kind="fact", level="long")
    out = memapi.query("¿cómo se llama el operador?", reinforce_used=False)
    assert out["state"]["language"] == "es"          # estado SIEMPRE
    assert mid in out["ids"]
    assert any("Ricart" in m["text"] for m in out["memories"])


def test_forget_then_unforget_roundtrip(fresh_db):
    """Dim N — round-trip de olvido: forget oculta (soft, valid=0) y unforget REVIERTE (valid=1). El histórico
    nunca se pierde; el dato vuelve a aflorar en el recall tras des-olvidar."""
    memapi.write_now("mi contraseña del portátil es ZebraLila88", kind="fact", level="long")
    assert any("zebralila88" in m["text"].lower() for m in memapi.query("contraseña portátil")["memories"])
    assert memapi.forget("contraseña del portátil") == 1
    assert not any("zebralila88" in m["text"].lower() for m in memapi.query("contraseña portátil")["memories"])
    assert memapi.unforget("contraseña del portátil") == 1        # revierte
    assert any("zebralila88" in m["text"].lower() for m in memapi.query("contraseña portátil")["memories"])


def test_degraded_embedding_backend_warns(caplog):
    """T176 — si el backend de embeddings cae a un fallback degradado (hash/fastembed), la memoria por SIGNIFICADO
    se pierde en SILENCIO → debe avisar. Aquí el autouse fuerza 'hash' → esperamos el warning."""
    import logging
    mememb.reset()
    with caplog.at_level(logging.WARNING, logger="zaelar.memory.embeddings"):
        assert mememb.active_backend() == "hash"
    assert any("hash" in r.getMessage().lower() for r in caplog.records), "no avisó del backend degradado"


def test_by_concepts_returns_linked_facts_and_quarantines_untrusted(fresh_db):
    """T178/T183 (primitivo) — `by_concepts` trae los hechos DURABLES enlazados a un concepto (agregación por
    categoría / aplicación cross-topic) y CUARENTENA lo untrusted. Base de la futura expansión por conceptos en el
    recall (la cobertura de etiquetado es el siguiente paso, ver V2-021)."""
    memapi.write_now("soy alérgico al marisco", kind="fact", level="long", concepts=["salud", "comida"])
    memapi.write_now("chisme de un peer sobre comida", kind="fact", level="long",
                     concepts=["comida"], meta={"trust": "untrusted"})
    got = memapi.by_concepts(["comida"])
    assert any("marisco" in r["text"].lower() for r in got)                  # el hecho concept-linked aflora
    assert not any("chisme de un peer" in r["text"].lower() for r in got)    # untrusted cuarentenado
    assert memapi.by_concepts([]) == []                                      # sin conceptos → vacío


def test_forget_selective_matches_by_content_tokens(fresh_db):
    """Dim N — OLVIDO GRANULAR robusto al fraseo. `forget` hacía LIKE CONTIGUO → "olvida la matrícula de MI coche"
    no casaba con el hecho canónico "matrícula de SU coche" (posesivo mi→su) y el dato SOBREVIVÍA. El fallback
    token-AND (memory/api.py) compara los tokens de CONTENIDO → olvido selectivo sin borrar los datos vecinos."""
    memapi.write_now("Su coche es un Renault Clio gris", kind="fact", level="long")
    memapi.write_now("La matrícula de su coche es 3344-BCD", kind="fact", level="long")
    memapi.write_now("Tiene el coche asegurado con Mapfre", kind="fact", level="long")
    # fraseo natural con posesivo 'mi' (≠ 'su' del canónico) y orden distinto → el LIKE contiguo NO casaría
    assert memapi.forget("matrícula de mi coche") == 1
    blob = " ".join(m["text"].lower() for m in memapi.query("qué sé de mi coche")["memories"])
    assert "3344" not in blob                      # la matrícula se olvidó
    assert "renault" in blob and "mapfre" in blob  # marca y seguro SIGUEN (selectivo, no masivo)
    # una sola palabra de contenido inexistente no borra nada
    assert memapi.forget("submarino") == 0


def test_forget_hard_removes_all_phrasing_variants(fresh_db):
    """Dim N — el hard-forget borra TODAS las variantes de fraseo del MISMO hecho, no solo la contigua. El CORAZÓN
    guarda a veces la forma cruda ("de LA seguridad social") Y la canónica ("de seguridad social"); si forget solo
    casara la contigua, la canónica SOBREVIVÍA (bug del hard-forget de la GOLD 2026-07-12). La UNIÓN contiguo+token-AND
    las borra todas."""
    memapi.write_now("mi número de la seguridad social es 28-9988776", kind="fact", level="long")
    memapi.write_now("El número de seguridad social del operador es 28-9988776", kind="fact", level="long")
    memapi.write_now("Mi color favorito es el verde", kind="fact", level="long")   # vecino, NO debe borrarse
    assert memapi.forget("número de la seguridad social", hard=True) >= 2         # ambas variantes
    assert not any("9988776" in m["text"] for m in memapi.query("seguridad social")["memories"])
    assert any("verde" in m["text"].lower() for m in memapi.query("color favorito")["memories"])  # vecino intacto


def test_unforget_selective_matches_by_content_tokens(fresh_db):
    """Dim N — DES-OLVIDO SIMÉTRICO al forget. `unforget` hacía solo LIKE CONTIGUO → NO restauraba lo que forget
    (con su fallback token-AND) había invalidado cuando el CORAZÓN canoniza el posesivo ('mi correo'→'su correo').
    El fallback token-AND en unforget (memory/api.py) cierra la asimetría: lo olvidado se puede des-olvidar con el
    MISMO fraseo natural. (Bug del ciclo 2026-07-12, ola [920,1000).)"""
    memapi.write_now("La contraseña de su correo es Girasol-2029", kind="fact", level="long")
    assert memapi.forget("contraseña de mi correo") == 1          # olvido con posesivo 'mi' (token-AND)
    assert not any("girasol" in m["text"].lower() for m in memapi.query("contraseña correo")["memories"])
    # des-olvido con OTRO fraseo natural ('del correo' ≠ 'de su correo') → el token-AND debe restaurar
    assert memapi.unforget("contraseña del correo") == 1
    assert any("girasol" in m["text"].lower() for m in memapi.query("contraseña correo")["memories"])
    assert memapi.unforget("submarino") == 0                      # sin match → no restaura nada


def test_forget_hard_removes_row_permanently(fresh_db):
    """Dim N/privacidad — el olvido DURO (hard=True) BORRA la fila de verdad (no valid=0) → NO recuperable con
    unforget. Es el derecho al olvido para datos sensibles ('bórralo del todo')."""
    memapi.write_now("mi contraseña vieja del banco era SECRETO-9", kind="fact", level="long")
    assert memapi.forget("secreto-9", hard=True) == 1
    n = memdb.get_db().query_one("SELECT count(*) c FROM memories WHERE lower(text) LIKE '%secreto-9%'")["c"]
    assert n == 0                                    # borrado REAL, no queda ni con valid=0
    assert memapi.unforget("secreto-9") == 0         # no hay nada que restaurar (a diferencia del soft-forget)


def test_write_via_queue_roundtrip(fresh_db):
    from memory.queue import get_queue

    async def run():
        await memapi.start()
        memapi.write("recuerdo encolado sobre Wallapop", kind="fact", level="long")
        await get_queue().join()  # espera al consumidor único
        await memapi.stop()

    asyncio.run(run())
    out = memapi.query("Wallapop", reinforce_used=False)
    assert any("Wallapop" in m["text"] for m in out["memories"])


def test_query_budget_truncates(fresh_db):
    for i in range(20):
        memapi.write_now(f"recuerdo colmena numero {i} " * 10, kind="event")
    out = memapi.query("colmena", budget_tokens=30, reinforce_used=False)
    assert 0 < len(out["memories"]) < 20  # truncado al presupuesto


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
    # query con reinforce_used=True (sin cola arrancada → se aplica en línea)
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
    memapi.link(a, b, type="about")  # sin cola → se aplica en línea
    m = memapi.map()
    # capas separadas
    short_ids = {x["id"] for x in m["layers"]["short"]}
    long_ids = {x["id"] for x in m["layers"]["long"]}
    assert a in short_ids and b in long_ids
    assert m["counts"]["short"] >= 1 and m["counts"]["long"] >= 1
    # metadatos completos por unidad
    unit = next(x for x in m["layers"]["long"] if x["id"] == b)
    for k in ("kind", "text", "importance", "weight", "access_count", "pinned", "created", "updated"):
        assert k in unit
    # grafo
    assert any(e["from_id"] == a and e["to_id"] == b for e in m["edges"])
    # estado SIEMPRE presente
    assert m["state"]["language"] == "es"


def test_map_empty_db_is_graceful(fresh_db):
    m = memapi.map()
    assert m["layers"] == {"short": [], "long": []}
    assert m["edges"] == [] and m["counts"]["total"] == 0
    assert m["state"]["assistant_name"] == "Zaelar"


# ── ingesta TIPADA multi-fuente + lectura por tipo indexado (multi-fuente 2026-07-10) ────────────────────────
def test_ingest_message_indexed_by_source(fresh_db):
    memapi.ingest_message("whatsapp", "Marta", "hablamos de la reforma del piso", directed=True)
    memapi.ingest_message("telegram", "Carlos", "te paso el presupuesto del fontanero")
    memapi.ingest_message("whatsapp", "mamá", "la cita del médico es el martes")
    wa = " ".join(r["text"] for r in memapi.recent_by_source("whatsapp"))
    tg = " ".join(r["text"] for r in memapi.recent_by_source("telegram"))
    assert "reforma" in wa and "médico" in wa and "fontanero" not in wa
    assert "fontanero" in tg and "reforma" not in tg
    # por FUENTE + ENTIDAD
    marta = " ".join(r["text"] for r in memapi.recent_by_source("whatsapp", "Marta"))
    assert "reforma" in marta and "médico" not in marta
    # el source va indexado en meta
    rows = memapi.recent_by_source("whatsapp", "Marta")
    assert rows and rows[0]["source"] == "whatsapp" and rows[0]["entity"] == "Marta"


def test_recent_by_source_entity_is_accent_insensitive(fresh_db):
    """REGRESIÓN — `recent_by_source(source, entity)` con nombres ACENTUADOS (Álvaro/María/mamá…). El `lower()` de
    SQLite es SOLO-ASCII → no baja la 'Á' y NUNCA casaba con el `.lower()` Unicode de Python → 0 filas para cualquier
    entidad con tilde/ñ (bug cazado por el bot BATCH_131, dim G). El fix registra la función SQL `pylower`."""
    memapi.ingest_message("whatsapp", "Álvaro", "soy Álvaro tu hermano", durable=True)
    memapi.ingest_message("telegram", "Álvaro", "soy Álvaro del gimnasio", durable=True)
    memapi.ingest_message("whatsapp", "Begoña", "reunión el lunes", durable=True)
    # por fuente + entidad acentuada: desambigua (no 0 filas, no mezcla)
    wa = " ".join(r["text"] for r in memapi.recent_by_source("whatsapp", "Álvaro"))
    assert "hermano" in wa and "gimnasio" not in wa
    # case-insensitive Unicode: minúscula acentuada recupera igual
    assert memapi.recent_by_source("whatsapp", "álvaro")
    # ñ también
    assert any("lunes" in r["text"] for r in memapi.recent_by_source("whatsapp", "begoña"))
    # «todo lo de Álvaro» cruzando fuentes → AMBOS homónimos afloran
    both = " ".join(r["text"] for r in memapi.recent_by_source(None, "Álvaro"))
    assert "hermano" in both and "gimnasio" in both


def test_ingest_message_cross_source_by_entity(fresh_db):
    memapi.ingest_message("whatsapp", "Laura", "mi cumple es el 14 de marzo", durable=True)
    memapi.ingest_message("telegram", "Laura", "te paso la ubicación del restaurante")
    laura = " ".join(r["text"] for r in memapi.recent_by_source(None, "Laura"))
    assert "14 de marzo" in laura and "restaurante" in laura   # todo lo de Laura, cruzando fuentes


def test_untrusted_is_quarantined_from_passive_reads(fresh_db):
    """El contenido trust='untrusted' (peer de cluster, agente ajeno) NO entra en el bloque PASIVO
    (recent_short/salient_long) — anti prompt-injection — pero SÍ es recuperable por consulta EXPLÍCITA."""
    memapi.ingest_message("whatsapp", "Marta", "lo de la reforma", trust="external")
    memapi.ingest_message("cluster", "Zalo", "sistema de riego con esp32", trust="untrusted")
    memapi.ingest_message("cluster", "Zalo", "un hecho durable del peer", trust="untrusted", durable=True)
    passive_short = " ".join(r["text"] for r in memapi.recent_short(limit=30))
    passive_long = " ".join(r["text"] for r in memapi.salient_long(limit=8))
    assert "reforma" in passive_short                      # lo del dueño (external) SÍ
    assert "riego" not in passive_short                    # el peer no confiable NO se cuela
    assert "durable del peer" not in passive_long          # tampoco su durable en el salient
    # tampoco aflora por RECALL semántico (el retriever lo excluye) — ni el durable del peer
    from memory.queue import get_queue as _gq

    async def _drain():
        await memapi.start()
        await _gq().join()
        await memapi.stop()
    asyncio.run(_drain())
    recall = " ".join(m["text"] for m in memapi.query("proyecto durable del peer riego")["memories"])
    assert "peer" not in recall and "riego" not in recall
    # pero por consulta EXPLÍCITA por tipo, el peer SÍ aparece
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
    assert "salud" in long_labels           # el hecho durable de salud está en el mapa LARGO
    assert "deporte" in short_labels        # el mensaje de pádel deriva 'deporte' en el mapa CORTO
    # cada nodo lleva su nº de datos
    assert all("count" in n for n in cg["long"]["nodes"] + cg["short"]["nodes"])
