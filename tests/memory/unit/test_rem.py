"""Tests del sueño PROFUNDO «fase REM» (memory/rem.py, V2-056). Deterministas: backend hash, hook inyectado."""
import time

import pytest

from memory import consolidator as memcons
from memory import db as memdb
from memory import embeddings as mememb
from memory import rem as memrem
from memory import writer as memwriter


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setattr(mememb, "_mem_cfg", lambda: {"embed_provider": "hash", "embed_model": ""})
    # apaga el dedup semántico DEL WRITER (T125) — aquí probamos el de REM aislado (si no, el writer fusiona
    # los duplicados de la fixture en el propio insert y REM nunca los ve)
    monkeypatch.setenv("MEM_SEMANTIC_DEDUP", "0")
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


def test_due_seeds_then_fires(fresh_db, monkeypatch):
    now = int(time.time())
    assert memrem.due(now) is False                       # 1ª vez: siembra el marcador, no corre
    assert memrem.due(now + 3600) is False                # dentro de la cadencia
    assert memrem.due(now + int(memrem.every_s()) + 10) is True
    monkeypatch.setenv("ZAELAR_REM", "0")
    assert memrem.due(now + 10 * 86400) is False          # kill-switch


def test_semantic_dedup_merges_echoes(fresh_db):
    # mismo multiconjunto de tokens, orden distinto → el embedding hash (léxico) los ve idénticos
    a = memwriter.insert_memory("tiene cita para la ITV el jueves 23", level="mid", kind="fact", weight=0.8)
    b = memwriter.insert_memory("el jueves 23 tiene cita para la ITV", level="mid", kind="fact", weight=0.5)
    merged = memrem.semantic_dedup(threshold=0.95)
    assert merged == 1
    db = memdb.get_db()
    rb = db.query_one("SELECT valid, superseded_by FROM memories WHERE id=?", (b,))
    assert rb["valid"] == 0 and rb["superseded_by"] == a   # gana el de mayor peso; histórico intacto
    ra = db.query_one("SELECT valid FROM memories WHERE id=?", (a,))
    assert ra["valid"] == 1


def test_semantic_dedup_respects_slots_and_pinned(fresh_db):
    memwriter.insert_memory("dato con slot", level="long", kind="fact", slot="goal.current")
    memwriter.insert_memory("con slot dato", level="long", kind="fact", slot="goal.current")
    # con slot NO entra al dedup semántico (ya supersede exacto por slot en el writer)
    assert memrem.semantic_dedup(threshold=0.9) == 0


def test_synthesize_writes_insight_with_supersede(fresh_db):
    for i, t in enumerate(["escuchó a Mocedades por la tarde", "escuchó a Serrat mientras trabajaba",
                           "pidió música de los ochenta", "sonó Tómame o Déjame en YouTube"]):
        memwriter.insert_memory(t, level="mid", kind="fact", concepts=["musica"])
    hook_calls = []

    def hook(groups):
        hook_calls.append(groups)
        return [{"concept": "musica", "insight": "Le gusta la música española clásica y la escucha mientras trabaja."}]

    assert memrem.synthesize(hook, min_group=4) == 1
    db = memdb.get_db()
    rows = db.query("SELECT id, valid, text FROM memories WHERE slot='insight:musica'")
    assert len(rows) == 1 and rows[0]["valid"] == 1
    assert "música" in rows[0]["text"]
    assert hook_calls and hook_calls[0][0]["concept"] == "musica" and len(hook_calls[0][0]["pills"]) >= 4
    # segundo sueño → el insight se REESCRIBE (supersede por slot), no se acumula
    def hook2(groups):
        return [{"concept": "musica", "insight": "Su música de cabecera es la canción española de los ochenta."}]
    assert memrem.synthesize(hook2, min_group=4) == 1
    valid = db.query("SELECT text FROM memories WHERE slot='insight:musica' AND valid=1")
    assert len(valid) == 1 and "ochenta" in valid[0]["text"]


def test_synthesize_failopen_without_hook(fresh_db):
    assert memrem.synthesize(None) == 0


def test_synthesize_demotes_source_pills_without_invalidating(fresh_db):
    # V2-103: REM debe RETIRAR lo que resume (demotar peso), no solo añadir el insight encima — las píldoras
    # crudas siguen `valid=1` (histórico intacto) pero dejan de pesar tanto como el insight que las suplanta.
    ids = [memwriter.insert_memory(t, level="mid", kind="fact", weight=0.8, concepts=["musica"])
           for t in ["escuchó a Mocedades por la tarde", "escuchó a Serrat mientras trabajaba",
                     "pidió música de los ochenta", "sonó Tómame o Déjame en YouTube"]]

    def hook(groups):
        return [{"concept": "musica", "insight": "Le gusta la música española clásica."}]

    assert memrem.synthesize(hook, min_group=4) == 1
    db = memdb.get_db()
    insight = db.query_one("SELECT id FROM memories WHERE slot='insight:musica' AND valid=1")
    for mid in ids:
        row = db.query_one("SELECT valid, weight, meta FROM memories WHERE id=?", (mid,))
        assert row["valid"] == 1                      # nunca se invalida ni se borra
        assert row["weight"] < 0.8                     # pero pesa menos que antes
        assert f'"summarized_by": {insight["id"]}' in (row["meta"] or "")


def test_synthesize_never_demotes_pinned(fresh_db):
    pinned_id = memwriter.insert_memory("hecho pinneado sobre música", level="long", kind="fact",
                                        weight=0.9, pinned=True, concepts=["musica"])
    for t in ["escuchó a Mocedades", "escuchó a Serrat", "música de los ochenta"]:
        memwriter.insert_memory(t, level="mid", kind="fact", weight=0.8, concepts=["musica"])

    def hook(groups):
        return [{"concept": "musica", "insight": "Le gusta la música española clásica."}]

    memrem.synthesize(hook, min_group=4)
    db = memdb.get_db()
    row = db.query_one("SELECT weight, meta FROM memories WHERE id=?", (pinned_id,))
    assert row["weight"] == 0.9
    assert "summarized_by" not in (row["meta"] or "")


# V2-104 (2026-08-16): tras V2-103, `demote_summarized` hace que un insight desplace (no solo compita con) los
# hechos correctos que resume — un insight INVENTADO ya no es ruido de bajo riesgo, es una fuente de error activa.
def test_synthesize_rejects_insight_with_fabricated_proper_noun(fresh_db):
    ids = [memwriter.insert_memory(t, level="mid", kind="fact", weight=0.8, concepts=["musica"])
           for t in ["escuchó a Mocedades por la tarde", "escuchó a Serrat mientras trabajaba",
                     "pidió música de los ochenta", "sonó Tómame o Déjame en YouTube"]]

    def hook(groups):
        # "Rocío" no aparece en ninguna píldora fuente — fabricación clásica de resumen por LLM.
        return [{"concept": "musica", "insight": "A Rocío le gusta la música española clásica."}]

    assert memrem.synthesize(hook, min_group=4) == 0
    db = memdb.get_db()
    assert db.query_one("SELECT id FROM memories WHERE slot='insight:musica' AND valid=1") is None
    for mid in ids:
        row = db.query_one("SELECT weight FROM memories WHERE id=?", (mid,))
        assert row["weight"] == 0.8, "rechazado → las píldoras fuente NO se demotan"


def test_synthesize_rejects_insight_with_fabricated_number(fresh_db):
    for t in ["escuchó a Mocedades", "escuchó a Serrat", "música de los ochenta", "sonó una canción en YouTube"]:
        memwriter.insert_memory(t, level="mid", kind="fact", weight=0.8, concepts=["musica"])

    def hook(groups):
        return [{"concept": "musica", "insight": "Escucha música española unas 12 veces por semana."}]

    assert memrem.synthesize(hook, min_group=4) == 0


def test_synthesize_rejects_oversized_insight(fresh_db):
    for t in ["escuchó a Mocedades", "escuchó a Serrat", "música de los ochenta", "sonó una canción"]:
        memwriter.insert_memory(t, level="mid", kind="fact", weight=0.8, concepts=["musica"])
    largo = "Le gusta la música española. " * 20  # muy por encima de MAX_INSIGHT_CHARS

    def hook(groups):
        return [{"concept": "musica", "insight": largo}]

    assert memrem.synthesize(hook, min_group=4) == 0


def test_synthesize_verify_fn_rejects_even_when_deterministic_backstop_passes(fresh_db):
    ids = [memwriter.insert_memory(t, level="mid", kind="fact", weight=0.8, concepts=["musica"])
           for t in ["escuchó a Mocedades", "escuchó a Serrat", "música de los ochenta", "sonó una canción"]]

    def hook(groups):
        return [{"concept": "musica", "insight": "Le gusta escuchar música clásica española."}]

    def verify_fn(insight, pills):
        return False  # segunda opinión: no lo respalda, aunque no haya cifras/nombres inventados

    assert memrem.synthesize(hook, min_group=4, verify_fn=verify_fn) == 0
    db = memdb.get_db()
    for mid in ids:
        assert db.query_one("SELECT weight FROM memories WHERE id=?", (mid,))["weight"] == 0.8


def test_synthesize_verify_fn_exception_treated_as_not_grounded(fresh_db):
    for t in ["escuchó a Mocedades", "escuchó a Serrat", "música de los ochenta", "sonó una canción"]:
        memwriter.insert_memory(t, level="mid", kind="fact", weight=0.8, concepts=["musica"])

    def hook(groups):
        return [{"concept": "musica", "insight": "Le gusta escuchar música clásica española."}]

    def verify_fn(insight, pills):
        raise RuntimeError("proveedor caído")

    assert memrem.synthesize(hook, min_group=4, verify_fn=verify_fn) == 0


def test_synthesize_writes_when_both_gates_pass(fresh_db):
    ids = [memwriter.insert_memory(t, level="mid", kind="fact", weight=0.8, concepts=["musica"])
           for t in ["escuchó a Mocedades", "escuchó a Serrat", "música de los ochenta", "sonó una canción"]]

    def hook(groups):
        return [{"concept": "musica", "insight": "Le gusta escuchar música clásica española."}]

    def verify_fn(insight, pills):
        return True

    assert memrem.synthesize(hook, min_group=4, verify_fn=verify_fn) == 1
    db = memdb.get_db()
    assert db.query_one("SELECT id FROM memories WHERE slot='insight:musica' AND valid=1") is not None
    for mid in ids:
        assert db.query_one("SELECT weight FROM memories WHERE id=?", (mid,))["weight"] < 0.8


def test_grounded_accepts_number_and_proper_noun_present_in_pills(fresh_db):
    pills = ["Ricart tiene cita con el Dr. Soler el 23", "va cada 6 meses"]
    assert memrem._grounded("Ricart visita al Dr. Soler cada 6 meses, cita el 23.", pills) is True


# V2-104, corregido tras validación REAL contra DeepSeek V4 Flash (2026-08-16, live_rem_faithfulness.py): el
# modelo convierte de forma CONSISTENTE una cantidad dicha en palabras en la fuente ("las nueve") a dígito en el
# insight ("las 9") — paráfrasis fiel, pero `_grounded()` la rechaza por comparar substring literal sin
# normalizar dígito↔palabra. Dejar que ese backstop vetara SIEMPRE, antes del `verify_fn`, significaba que un
# insight fiel nunca llegaba a que el verificador REAL (que sí lo aceptaba en 3/3 intentos) tuviera la última
# palabra. `verify_fn`, cuando existe, debe ser el ÁRBITRO — `_grounded()` solo decide sin él.
def test_verify_fn_overrides_deterministic_backstop_false_positive(fresh_db):
    ids = [memwriter.insert_memory(t, level="mid", kind="fact", weight=0.8, concepts=["running"])
           for t in ["corre 8 km los domingos por el Retiro", "entrena la media maratón de Madrid",
                     "escucha a Vetusta Morla mientras corre", "corre siempre antes de las nueve"]]

    def hook(groups):
        return [{"concept": "running", "insight": "Corre 8 km por el Retiro antes de las 9, entrenando la "
                                                    "media maratón de Madrid con Vetusta Morla de fondo."}]

    def verify_fn(insight, pills):
        return True  # el juicio REAL: "9" ≈ "nueve" es la misma cifra, no una fabricación

    pills_for_check = ["corre 8 km los domingos por el Retiro", "entrena la media maratón de Madrid",
                       "escucha a Vetusta Morla mientras corre", "corre siempre antes de las nueve"]
    insight_text = ("Corre 8 km por el Retiro antes de las 9, entrenando la media maratón de Madrid con "
                    "Vetusta Morla de fondo.")
    assert memrem._grounded(insight_text, pills_for_check) is False, \
        "precondición: el backstop determinista SÍ rechaza este caso (dígito vs palabra) — si esto deja de " \
        "fallar, el escenario ya no reproduce el bug real y hay que revisar el test"

    assert memrem.synthesize(hook, min_group=4, verify_fn=verify_fn) == 1
    db = memdb.get_db()
    assert db.query_one("SELECT id FROM memories WHERE slot='insight:running' AND valid=1") is not None
    for mid in ids:
        assert db.query_one("SELECT weight FROM memories WHERE id=?", (mid,))["weight"] < 0.8


def test_grounded_alone_still_gates_when_no_verify_fn(fresh_db):
    """Sin `verify_fn` (fail-safe sin LLM disponible), `_grounded()` sigue siendo el único gate."""
    for t in ["corre 8 km los domingos por el Retiro", "entrena la media maratón de Madrid",
             "escucha a Vetusta Morla mientras corre", "corre siempre antes de las nueve"]:
        memwriter.insert_memory(t, level="mid", kind="fact", weight=0.8, concepts=["running"])

    def hook(groups):
        return [{"concept": "running", "insight": "Corre 8 km por el Retiro antes de las 9, entrenando la "
                                                    "media maratón de Madrid con Vetusta Morla de fondo."}]

    assert memrem.synthesize(hook, min_group=4) == 0  # sin verify_fn → el backstop rechaza, como antes


def test_repair_embeddings_limit_configurable(fresh_db, monkeypatch):
    monkeypatch.setenv("ZAELAR_REM_REPAIR_LIMIT", "3")
    for i in range(5):
        memwriter.insert_memory(f"dato sin vector {i}", level="mid", kind="fact")
    db = memdb.get_db()
    db.execute("DELETE FROM vec_memories")   # simula backlog: todas sin vector
    fixed = memrem.repair_embeddings()       # sin `limit=` explícito → usa el default configurable
    assert fixed == 3


def test_repair_embeddings_default_raised_from_200(fresh_db):
    assert memrem._repair_limit_default() >= 1000


# V2-031 T2 (2026-08-17): fase de backfill del índice de paráfrasis — mismo patrón inyectable que synthesize_fn.
def test_index_paraphrases_backfills_pills_without_any(fresh_db):
    ids = [memwriter.insert_memory(t, level="mid", kind="fact")
           for t in ["toca la guitarra los sábados", "cocina platos italianos"]]
    calls = []

    def hook(text):
        calls.append(text)
        return [f"reformulación de: {text}"]

    done = memrem.index_paraphrases(hook)
    assert done == 2
    assert set(calls) == {"toca la guitarra los sábados", "cocina platos italianos"}
    db = memdb.get_db()
    for mid in ids:
        assert db.query_one("SELECT COUNT(*) c FROM paraphrase_index WHERE memory_id=?", (mid,))["c"] == 1


def test_index_paraphrases_skips_pills_that_already_have_one(fresh_db):
    mid = memwriter.insert_memory("dato con paráfrasis ya indexada", level="mid", kind="fact")
    memwriter.index_paraphrases(mid, ["ya tiene una"])
    calls = []

    def hook(text):
        calls.append(text)
        return ["otra"]

    assert memrem.index_paraphrases(hook) == 0
    assert calls == []  # ni se le pregunta al hook — ya estaba cubierta


def test_index_paraphrases_respects_limit_and_hook_failure(fresh_db):
    for i in range(5):
        memwriter.insert_memory(f"dato {i}", level="mid", kind="fact")

    calls = []

    def hook(text):
        calls.append(text)
        if "dato 1" in text:
            raise RuntimeError("proveedor caído")
        return [f"reformulación {text}"]

    done = memrem.index_paraphrases(hook, limit=3)
    assert len(calls) == 3          # respeta el límite
    assert done == 2                # 1 de los 3 falló (fail-open, no cuenta, no rompe el resto)


def test_index_paraphrases_noop_without_hook(fresh_db):
    memwriter.insert_memory("dato", level="mid", kind="fact")
    assert memrem.index_paraphrases(None) == 0


# ── a MUTE hook has to be VISIBLE (2026-08-18) ──────────────────────────────────────────────────────────────
# The paraphrase channel sat at 0 rows from the day it was built and no surface said so: the per-pill fail-open
# is correct, but it made "the whole channel is dead" indistinguishable from "no candidates tonight".
def test_index_paraphrases_flags_health_when_the_hook_returns_nothing(fresh_db, monkeypatch):
    for i in range(3):
        memwriter.insert_memory(f"dato {i}", level="mid", kind="fact")

    recorded = []
    import voice.health_state as hs
    monkeypatch.setattr(hs, "record", lambda *a, **k: recorded.append((a, k)))

    assert memrem.index_paraphrases(lambda _t: []) == 0
    assert recorded, "a mute paraphrase channel must reach health_state, not just the log"
    component, state = recorded[0][0][0], recorded[0][0][1]
    assert component == "memory" and state == "degraded"


def test_index_paraphrases_stays_quiet_when_some_pills_do_succeed(fresh_db, monkeypatch):
    """With MIXED candidates the channel is alive: one failing pill is normal noise, not an outage. Without this
    half, the alert would fire every night and stop meaning anything."""
    for i in range(3):
        memwriter.insert_memory(f"dato {i}", level="mid", kind="fact")

    recorded = []
    import voice.health_state as hs
    monkeypatch.setattr(hs, "record", lambda *a, **k: recorded.append(a))

    done = memrem.index_paraphrases(lambda t: [] if "dato 1" in t else [f"otra forma de {t}"])
    assert done == 2
    assert recorded == []


# V2-103 (2026-08-16): la formación de grupos de concepto (`_concept_groups`/`synthesize`) solo se había probado
# con 4-12 píldoras de un único concepto limpio — nunca con una distribución RUIDOSA de cientos de píldoras en
# más conceptos que `MAX_GROUPS`, que es donde un bug de ordenación/corte se volvería invisible en un fixture
# pequeño pero real a escala de producción.
def test_concept_groups_at_scale_picks_largest_and_respects_cap(fresh_db):
    import random
    rnd = random.Random(7)
    # 20 conceptos con tamaños de grupo DISTINTOS y solapados; solo los MAX_GROUPS=8 más poblados deben
    # sintetizarse, y ninguno por debajo de MIN_GROUP=4 debe aparecer nunca.
    sizes = {f"concepto{n}": n for n in range(1, 21)}   # concepto1→1 píldora … concepto20→20 píldoras
    for concept, n in sizes.items():
        for i in range(n):
            memwriter.insert_memory(f"{concept} dato {i} {rnd.random()}", level="mid", kind="fact",
                                    concepts=[concept])

    groups = memrem._concept_groups(min_group=4, max_groups=8)
    assert len(groups) == 8
    got = {g["concept"]: len(g["pills"]) for g in groups}
    # los 8 conceptos con MÁS píldoras (concepto13..concepto20) son los elegidos, en orden descendente
    expected_top8 = sorted(sizes.items(), key=lambda kv: -kv[1])[:8]
    assert set(got) == {c for c, _ in expected_top8}
    assert all(n >= 4 for n in got.values()), "ningún grupo por debajo de MIN_GROUP debe colarse"
    sizes_sorted = sorted(got.values(), reverse=True)
    assert sizes_sorted == sorted(sizes_sorted, reverse=True)  # viene ya ordenado de mayor a menor

    hook_seen = []

    def hook(gs):
        hook_seen.extend(g["concept"] for g in gs)
        return [{"concept": g["concept"], "insight": f"Insight de {g['concept']} sobre {len(g['pills'])} datos."}
                for g in gs]

    written = memrem.synthesize(hook, min_group=4)
    assert written == 8
    assert set(hook_seen) == {c for c, _ in expected_top8}
    db = memdb.get_db()
    n_insights = db.query_one("SELECT COUNT(*) c FROM memories WHERE kind='insight' AND valid=1")["c"]
    assert n_insights == 8


def test_hygiene_alerts_on_heuristic_flood(fresh_db):
    for i in range(12):
        memwriter.insert_memory(f"crudo {i}", level="mid", kind="fact",
                                meta={"source": "voice", "path": "heuristic"})
    h = memrem.hygiene()
    assert h["written_24h"] >= 12 and h["heuristic_pct"] > 90 and h["alert"] is True


def test_run_full_cycle_reports(fresh_db):
    memwriter.insert_memory("un dato", level="mid", kind="fact")
    rep = memrem.run(synthesize_fn=None)
    assert set(rep) >= {"repaired", "sem_deduped", "insights", "hygiene", "ms"}
    # el marcador queda sembrado → el próximo due() respeta cadencia
    assert memrem.due() is False


# ── V2-482 · un vector de ESPACIO AJENO se retira para que la reparación lo vea ─────────────────────────────
#
# `repair_embeddings` solo busca filas SIN vector, que es lo que deja el guarda de firma del writer. Una fila
# cuyo vector ajeno se coló ANTES del guarda tiene vector, así que la pasada de reparación no la selecciona
# jamás: el daño es permanente por construcción. Medido 2026-08-29 sobre la memoria viva del operador — 15
# filas durables con un `_hash_embed` literal dentro de un índice sellado `ollama:embeddinggemma:768`.

@pytest.fixture
def sellado_gemma(monkeypatch):
    """El índice declara un espacio REAL, y el backend activo de los tests es `hash` → todo vector hash que
    haya dentro es ajeno. Se declara la precondición en vez de heredarla del entorno."""
    from memory import reembed as memreembed
    monkeypatch.setattr(memreembed, "stored_signature", lambda: "ollama:embeddinggemma:768")
    monkeypatch.setattr(memwriter, "_embed_sig_ok", lambda: True)


def _vector_de(mid: int):
    row = memdb.get_db().query_one("SELECT embedding FROM vec_memories WHERE memory_id=?", (mid,))
    return memrem._unpack(row["embedding"]) if row else None


def test_un_vector_hash_dentro_de_un_indice_sellado_se_retira(fresh_db, sellado_gemma):
    mid = memwriter.insert_memory("Le interesan los Ferrari.", level="long", kind="pref")
    assert _vector_de(mid) is not None                      # el writer lo metió con el backend hash activo
    assert memrem._drop_foreign_vectors(memdb.get_db(), 100) == 1
    assert _vector_de(mid) is None


def test_la_fila_queda_MARCADA_para_que_hygiene_la_cuente(fresh_db, sellado_gemma):
    mid = memwriter.insert_memory("Le interesa la guitarra.", level="long", kind="pref")
    memrem._drop_foreign_vectors(memdb.get_db(), 100)
    row = memdb.get_db().query_one(
        "SELECT json_extract(meta,'$.embed_pending') AS p FROM memories WHERE id=?", (mid,))
    assert row["p"] == "foreign_space"


def test_un_vector_del_espacio_BUENO_no_se_toca(fresh_db, sellado_gemma):
    mid = memwriter.insert_memory("Vive en Madrid.", level="long", kind="fact")
    denso = [0.03] * mememb.dim()
    memdb.get_db().execute("UPDATE vec_memories SET embedding=? WHERE memory_id=?",
                           (memwriter._pack(denso), mid))
    assert memrem._drop_foreign_vectors(memdb.get_db(), 100) == 0
    assert _vector_de(mid) is not None


def test_si_HASH_es_el_espacio_sellado_no_hay_nada_ajeno(fresh_db, monkeypatch):
    """Dev, tests, una BD recién nacida: ahí los vectores hash son NATIVOS, no intrusos."""
    from memory import reembed as memreembed
    monkeypatch.setattr(memreembed, "stored_signature", lambda: "hash:hash:768")
    memwriter.insert_memory("Le interesan los Ferrari.", level="long", kind="pref")
    assert memrem._drop_foreign_vectors(memdb.get_db(), 100) == 0


def test_sin_firma_sellada_no_se_llama_ajeno_a_nada(fresh_db, monkeypatch):
    """Sin espacio declarado no hay nada respecto a lo que ser ajeno — borrar sería tirar el único canal
    semántico que esa base tiene."""
    from memory import reembed as memreembed
    monkeypatch.setattr(memreembed, "stored_signature", lambda: None)
    memwriter.insert_memory("Le interesan los Ferrari.", level="long", kind="pref")
    assert memrem._drop_foreign_vectors(memdb.get_db(), 100) == 0


def test_repair_embeddings_AHORA_alcanza_la_fila_con_vector_ajeno(fresh_db, sellado_gemma, monkeypatch):
    """El camino entero: retirar el vector ajeno es lo que hace que la MISMA pasada lo re-embeba bien.

    `embed` se sustituye por un vector denso porque en producción `_embed_sig_ok()` cierto significa que el
    backend activo ES el sellado; con el `hash` de los tests, reparar devolvería otro vector ajeno."""
    mid = memwriter.insert_memory("Le interesan los Ferrari.", level="long", kind="pref")
    denso = [0.02] * mememb.dim()
    monkeypatch.setattr(mememb, "embed", lambda _t: list(denso))
    monkeypatch.setattr(mememb, "last_degraded", False)
    assert memrem.repair_embeddings(limit=100) == 1
    assert _vector_de(mid) == pytest.approx(denso)
    row = memdb.get_db().query_one(
        "SELECT json_extract(meta,'$.embed_pending') AS p FROM memories WHERE id=?", (mid,))
    assert row["p"] is None                                 # reparada → el marcador se limpia


# ── V2-485 · el vector AJENO que no se puede reproducir desde el texto, pero cuya FORMA lo delata ───────────

def _con_vector_rellenado(texto: str) -> int:
    """Una píldora cuyo vector viene de un espacio de media dimensión, rellenado con ceros — la forma exacta
    de un fastembed dentro de un índice de 768."""
    mid = memwriter.insert_memory(texto, level="long", kind="fact")
    dim = mememb.dim()
    relleno = [0.05] * (dim // 2) + [0.0] * (dim // 2)
    memdb.get_db().execute("UPDATE vec_memories SET embedding=? WHERE memory_id=?",
                           (memwriter._pack(relleno), mid))
    return mid


def test_un_vector_RELLENADO_desde_un_espacio_menor_se_retira(fresh_db, sellado_gemma):
    """Los 9 del índice del operador: 384 no-ceros + 384 ceros al final dentro de un índice de 768 sellado
    embeddinggemma. Un fastembed no se reproduce desde su texto — su forma sí lo dice."""
    mid = _con_vector_rellenado("un dato cualquiera")
    memrem._drop_foreign_vectors(memdb.get_db(), 100)
    assert _vector_de(mid) is None


def test_con_FASTEMBED_sellado_un_vector_rellenado_es_el_NATIVO(fresh_db, monkeypatch):
    """La mitad que impide que el arreglo se coma una base sana: fastembed ES 384 rellenados a 768, así que
    ahí la forma no delata nada y solo vale la huella de hash."""
    from memory import reembed as memreembed
    monkeypatch.setattr(memreembed, "stored_signature", lambda: "fastembed:bge-small:768")
    monkeypatch.setattr(memwriter, "_embed_sig_ok", lambda: True)
    mid = _con_vector_rellenado("un dato cualquiera")
    memrem._drop_foreign_vectors(memdb.get_db(), 100)
    assert _vector_de(mid) is not None


def test_la_frontera_del_relleno_es_la_MITAD_de_la_dimension():
    """Deliberadamente gruesa: un modelo de 512 rellenado a 768 deja 256 ceros y NO se caza. Ensancharla
    empezaría a adivinar sobre vectores meramente dispersos, y aquí un falso positivo tira un vector bueno."""
    assert memrem._looks_padded([0.1] * 384 + [0.0] * 384) is True
    assert memrem._looks_padded([0.1] * 385 + [0.0] * 383) is False
    assert memrem._looks_padded([0.1] * 768) is False
