"""Tests of DEEP sleep «REM phase» (memory/rem.py, V2-056). Deterministic: hash backend, injected hook."""
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
    # disable the WRITER's semantic deduplication (T125) — here we test REM's in isolation (otherwise, the writer merges
    # the fixture duplicates during the insert itself and REM never sees them)
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
    assert memrem.due(now) is False                       # first time: seeds the marker, does not run
    assert memrem.due(now + 3600) is False                # within the interval
    assert memrem.due(now + int(memrem.every_s()) + 10) is True
    monkeypatch.setenv("ZAELAR_REM", "0")
    assert memrem.due(now + 10 * 86400) is False          # kill switch


def test_semantic_dedup_merges_echoes(fresh_db):
    # same multiset of tokens, different order → the (lexical) hash embedding sees them as identical
    a = memwriter.insert_memory("tiene cita para la ITV el jueves 23", level="mid", kind="fact", weight=0.8)
    b = memwriter.insert_memory("el jueves 23 tiene cita para la ITV", level="mid", kind="fact", weight=0.5)
    merged = memrem.semantic_dedup(threshold=0.95)
    assert merged == 1
    db = memdb.get_db()
    rb = db.query_one("SELECT valid, superseded_by FROM memories WHERE id=?", (b,))
    assert rb["valid"] == 0 and rb["superseded_by"] == a   # the higher-weight one wins; history remains intact
    ra = db.query_one("SELECT valid FROM memories WHERE id=?", (a,))
    assert ra["valid"] == 1


def test_semantic_dedup_respects_slots_and_pinned(fresh_db):
    memwriter.insert_memory("dato con slot", level="long", kind="fact", slot="goal.current")
    memwriter.insert_memory("con slot dato", level="long", kind="fact", slot="goal.current")
    # an item with a slot does NOT enter semantic deduplication (the writer already performs exact supersession by slot)
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
    # second sleep → the insight is REWRITTEN (superseded by slot), not accumulated
    def hook2(groups):
        return [{"concept": "musica", "insight": "Su música de cabecera es la canción española de los ochenta."}]
    assert memrem.synthesize(hook2, min_group=4) == 1
    valid = db.query("SELECT text FROM memories WHERE slot='insight:musica' AND valid=1")
    assert len(valid) == 1 and "ochenta" in valid[0]["text"]


def test_synthesize_failopen_without_hook(fresh_db):
    assert memrem.synthesize(None) == 0


def test_synthesize_demotes_source_pills_without_invalidating(fresh_db):
    # V2-103: REM must RETIRE what it summarizes (demote its weight), not merely add the insight on top — the raw pills
    # remain `valid=1` (history intact) but no longer carry as much weight as the insight that supersedes them.
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
        assert row["valid"] == 1                      # it is never invalidated or deleted
        assert row["weight"] < 0.8                     # but weighs less than before
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


# V2-104 (2026-08-16): after V2-103, `demote_summarized` makes an insight displace (rather than merely compete with)
# correct facts that it summarizes — an INVENTED insight is no longer low-risk noise, but an active source of error.
def test_synthesize_rejects_insight_with_fabricated_proper_noun(fresh_db):
    ids = [memwriter.insert_memory(t, level="mid", kind="fact", weight=0.8, concepts=["musica"])
           for t in ["escuchó a Mocedades por la tarde", "escuchó a Serrat mientras trabajaba",
                     "pidió música de los ochenta", "sonó Tómame o Déjame en YouTube"]]

    def hook(groups):
        # "Rocío" does not appear in any source pill — classic LLM summary fabrication.
        return [{"concept": "musica", "insight": "A Rocío le gusta la música española clásica."}]

    assert memrem.synthesize(hook, min_group=4) == 0
    db = memdb.get_db()
    assert db.query_one("SELECT id FROM memories WHERE slot='insight:musica' AND valid=1") is None
    for mid in ids:
        row = db.query_one("SELECT weight FROM memories WHERE id=?", (mid,))
        assert row["weight"] == 0.8, "rejected → source pills are NOT demoted"


def test_synthesize_rejects_insight_with_fabricated_number(fresh_db):
    for t in ["escuchó a Mocedades", "escuchó a Serrat", "música de los ochenta", "sonó una canción en YouTube"]:
        memwriter.insert_memory(t, level="mid", kind="fact", weight=0.8, concepts=["musica"])

    def hook(groups):
        return [{"concept": "musica", "insight": "Escucha música española unas 12 veces por semana."}]

    assert memrem.synthesize(hook, min_group=4) == 0


def test_synthesize_rejects_oversized_insight(fresh_db):
    for t in ["escuchó a Mocedades", "escuchó a Serrat", "música de los ochenta", "sonó una canción"]:
        memwriter.insert_memory(t, level="mid", kind="fact", weight=0.8, concepts=["musica"])
    largo = "Le gusta la música española. " * 20  # far above MAX_INSIGHT_CHARS

    def hook(groups):
        return [{"concept": "musica", "insight": largo}]

    assert memrem.synthesize(hook, min_group=4) == 0


def test_synthesize_verify_fn_rejects_even_when_deterministic_backstop_passes(fresh_db):
    ids = [memwriter.insert_memory(t, level="mid", kind="fact", weight=0.8, concepts=["musica"])
           for t in ["escuchó a Mocedades", "escuchó a Serrat", "música de los ochenta", "sonó una canción"]]

    def hook(groups):
        return [{"concept": "musica", "insight": "Le gusta escuchar música clásica española."}]

    def verify_fn(insight, pills):
        return False  # second opinion: does not support it, even though no figures/names are fabricated

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


# V2-104, fixed after REAL validation against DeepSeek V4 Flash (2026-08-16, live_rem_faithfulness.py): the
# model CONSISTENTLY converts an amount written in words in the source ("nine") to a digit in the insight
# ("9") — a faithful paraphrase, but `_grounded()` rejects it by comparing literal substrings without
# normalizing digit↔word. Letting that backstop ALWAYS veto, before `verify_fn`, meant that a faithful
# insight never reached the REAL verifier (which accepted it in 3/3 attempts) for the final say. When present,
# `verify_fn` must be the ARBITER — `_grounded()` decides only without it.
def test_verify_fn_overrides_deterministic_backstop_false_positive(fresh_db):
    ids = [memwriter.insert_memory(t, level="mid", kind="fact", weight=0.8, concepts=["running"])
           for t in ["corre 8 km los domingos por el Retiro", "entrena la media maratón de Madrid",
                     "escucha a Vetusta Morla mientras corre", "corre siempre antes de las nueve"]]

    def hook(groups):
        return [{"concept": "running", "insight": "Corre 8 km por el Retiro antes de las 9, entrenando la "
                                                    "media maratón de Madrid con Vetusta Morla de fondo."}]

    def verify_fn(insight, pills):
        return True  # the REAL judgment: "9" ≈ "nine" is the same number, not a fabrication

    pills_for_check = ["corre 8 km los domingos por el Retiro", "entrena la media maratón de Madrid",
                       "escucha a Vetusta Morla mientras corre", "corre siempre antes de las nueve"]
    insight_text = ("Corre 8 km por el Retiro antes de las 9, entrenando la media maratón de Madrid con "
                    "Vetusta Morla de fondo.")
    assert memrem._grounded(insight_text, pills_for_check) is False, \
        "precondition: the deterministic backstop DOES reject this case (digit vs word) — if this stops " \
        "failing, the scenario no longer reproduces the real bug and the test must be reviewed"

    assert memrem.synthesize(hook, min_group=4, verify_fn=verify_fn) == 1
    db = memdb.get_db()
    assert db.query_one("SELECT id FROM memories WHERE slot='insight:running' AND valid=1") is not None
    for mid in ids:
        assert db.query_one("SELECT weight FROM memories WHERE id=?", (mid,))["weight"] < 0.8


def test_grounded_alone_still_gates_when_no_verify_fn(fresh_db):
    """Without `verify_fn` (fail-safe when no LLM is available), `_grounded()` remains the only gate."""
    for t in ["corre 8 km los domingos por el Retiro", "entrena la media maratón de Madrid",
             "escucha a Vetusta Morla mientras corre", "corre siempre antes de las nueve"]:
        memwriter.insert_memory(t, level="mid", kind="fact", weight=0.8, concepts=["running"])

    def hook(groups):
        return [{"concept": "running", "insight": "Corre 8 km por el Retiro antes de las 9, entrenando la "
                                                    "media maratón de Madrid con Vetusta Morla de fondo."}]

    assert memrem.synthesize(hook, min_group=4) == 0  # without verify_fn → the backstop rejects, as before


def test_repair_embeddings_limit_configurable(fresh_db, monkeypatch):
    monkeypatch.setenv("ZAELAR_REM_REPAIR_LIMIT", "3")
    for i in range(5):
        memwriter.insert_memory(f"dato sin vector {i}", level="mid", kind="fact")
    db = memdb.get_db()
    db.execute("DELETE FROM vec_memories")   # simulate backlog: all without a vector
    fixed = memrem.repair_embeddings()       # without explicit `limit=` → uses the configurable default
    assert fixed == 3


def test_repair_embeddings_default_raised_from_200(fresh_db):
    assert memrem._repair_limit_default() >= 1000


# V2-031 T2 (2026-08-17): paraphrase-index backfill phase — same injectable pattern as synthesize_fn.
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


# V2-103 (2026-08-16): concept-group formation (`_concept_groups`/`synthesize`) had only been tested with
# 4–12 pills from one clean concept — never with a NOISY distribution of hundreds of pills across more concepts
# than `MAX_GROUPS`, where an ordering/truncation bug would become invisible in a small but production-scale fixture.
def test_concept_groups_at_scale_picks_largest_and_respects_cap(fresh_db):
    import random
    rnd = random.Random(7)
    # 20 concepts with DISTINCT, overlapping group sizes; only the 8 most populated MAX_GROUPS should be
    # synthesized, and none below MIN_GROUP=4 should ever appear.
    sizes = {f"concepto{n}": n for n in range(1, 21)}   # concepto1→1 píldora … concepto20→20 píldoras
    for concept, n in sizes.items():
        for i in range(n):
            memwriter.insert_memory(f"{concept} dato {i} {rnd.random()}", level="mid", kind="fact",
                                    concepts=[concept])

    groups = memrem._concept_groups(min_group=4, max_groups=8)
    assert len(groups) == 8
    got = {g["concept"]: len(g["pills"]) for g in groups}
    # the 8 concepts with the MOST pills (concepto13..concepto20) are selected, in descending order
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
    # the marker is seeded → the next due() respects the interval
    assert memrem.due() is False


# ── V2-482 · a vector from a FOREIGN SPACE is removed so repair can see it ─────────────────────────────────
#
# `repair_embeddings` only looks for rows WITHOUT a vector, which is what the writer's signature guard leaves behind. A row
# whose foreign vector slipped in BEFORE the guard has a vector, so the repair pass never selects it: the damage is permanent
# by construction. Measured 2026-08-29 on the operator's live memory — 15 durable rows with a literal `_hash_embed` inside a
# sealed `ollama:embeddinggemma:768` index.

@pytest.fixture
def sellado_gemma(monkeypatch):
    """The index declares a REAL space, and the active test backend is `hash` → every hash vector inside it
    is foreign. The precondition is declared instead of inherited from the environment."""
    from memory import reembed as memreembed
    monkeypatch.setattr(memreembed, "stored_signature", lambda: "ollama:embeddinggemma:768")
    monkeypatch.setattr(memwriter, "_embed_sig_ok", lambda: True)
    monkeypatch.setattr(memreembed, "_SPACE_CACHE", (0.0, True, None))   # global: se restaura, no se pisa


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
    """Dev, tests, a freshly created database: there, hash vectors are NATIVE, not intruders."""
    from memory import reembed as memreembed
    monkeypatch.setattr(memreembed, "stored_signature", lambda: "hash:hash:768")
    memwriter.insert_memory("Le interesan los Ferrari.", level="long", kind="pref")
    assert memrem._drop_foreign_vectors(memdb.get_db(), 100) == 0


def test_sin_firma_sellada_no_se_llama_ajeno_a_nada(fresh_db, monkeypatch):
    """Without a declared space there is nothing against which to be foreign — deleting would throw away the only
    semantic channel that database has."""
    from memory import reembed as memreembed
    monkeypatch.setattr(memreembed, "stored_signature", lambda: None)
    memwriter.insert_memory("Le interesan los Ferrari.", level="long", kind="pref")
    assert memrem._drop_foreign_vectors(memdb.get_db(), 100) == 0


def test_repair_embeddings_AHORA_alcanza_la_fila_con_vector_ajeno(fresh_db, sellado_gemma, monkeypatch):
    """The whole path: removing the foreign vector is what lets the SAME pass re-embed it correctly.

    `embed` se sustituye por un vector denso porque en producción `_embed_sig_ok()` cierto significa que el
    active backend IS the sealed one; with the test `hash`, repair would return another foreign vector."""
    mid = memwriter.insert_memory("Le interesan los Ferrari.", level="long", kind="pref")
    denso = [0.02] * mememb.dim()
    monkeypatch.setattr(mememb, "embed", lambda _t: list(denso))
    monkeypatch.setattr(mememb, "last_degraded", False)
    assert memrem.repair_embeddings(limit=100) == 1
    assert _vector_de(mid) == pytest.approx(denso)
    row = memdb.get_db().query_one(
        "SELECT json_extract(meta,'$.embed_pending') AS p FROM memories WHERE id=?", (mid,))
    assert row["p"] is None                                 # reparada → el marcador se limpia


# ── V2-485 · the FOREIGN vector that cannot be reproduced from text, but whose SHAPE gives it away ─────────

def _con_vector_rellenado(texto: str) -> int:
    """A pill whose vector comes from a half-dimensional space, padded with zeros — the exact shape
    of a fastembed inside a 768-dimensional index."""
    mid = memwriter.insert_memory(texto, level="long", kind="fact")
    dim = mememb.dim()
    relleno = [0.05] * (dim // 2) + [0.0] * (dim // 2)
    memdb.get_db().execute("UPDATE vec_memories SET embedding=? WHERE memory_id=?",
                           (memwriter._pack(relleno), mid))
    return mid


def test_un_vector_RELLENADO_desde_un_espacio_menor_se_retira(fresh_db, sellado_gemma):
    """The operator's 9: 384 nonzeros + 384 trailing zeros inside a sealed 768-dimensional embeddinggemma index.
    A fastembed cannot be reproduced from its text — its shape gives it away."""
    mid = _con_vector_rellenado("un dato cualquiera")
    memrem._drop_foreign_vectors(memdb.get_db(), 100)
    assert _vector_de(mid) is None


def test_con_FASTEMBED_sellado_un_vector_rellenado_es_el_NATIVO(fresh_db, monkeypatch):
    """The safeguard that prevents the fix from consuming a healthy database: fastembed IS 384 padded to 768, so
    in that case the shape gives nothing away and only the hash fingerprint is useful."""
    from memory import reembed as memreembed
    monkeypatch.setattr(memreembed, "stored_signature", lambda: "fastembed:bge-small:768")
    monkeypatch.setattr(memwriter, "_embed_sig_ok", lambda: True)
    mid = _con_vector_rellenado("un dato cualquiera")
    memrem._drop_foreign_vectors(memdb.get_db(), 100)
    assert _vector_de(mid) is not None


def test_la_frontera_del_relleno_es_la_MITAD_de_la_dimension():
    """Deliberately coarse: a 512-dimensional model padded to 768 leaves 256 zeros and is NOT caught. Widening it
    would start guessing about merely sparse vectors, and here a false positive throws away a good vector."""
    assert memrem._looks_padded([0.1] * 384 + [0.0] * 384) is True
    assert memrem._looks_padded([0.1] * 385 + [0.0] * 383) is False
    assert memrem._looks_padded([0.1] * 768) is False


def test_el_aviso_DESGLOSA_la_clase_de_vector_retirado(fresh_db, sellado_gemma, monkeypatch):
    """The two classes enter through different doors — hash through a stale permission (V2-484), padded through a
    path without a guard (V2-485). An alert that counts them together under one label sends the next diagnosis
    to the wrong door, which is what happened when it only knew about hash."""
    memwriter.insert_memory("Le interesan los Ferrari.", level="long", kind="pref")   # vector hash real
    _con_vector_rellenado("otro dato cualquiera")                                     # forma de fastembed
    dicho: list[str] = []
    # Capture the module logger, NOT with `caplog`: this uses loguru, which does not propagate to stdlib
    # `logging` — a case built on caplog would pass without having read a single alert.
    monkeypatch.setattr(memrem.logger, "warning", lambda m, *a, **k: dicho.append(str(m)))
    memrem._drop_foreign_vectors(memdb.get_db(), 100)
    aviso = " ".join(dicho)
    assert "1 hash" in aviso and "1 rellenado" in aviso


def test_la_reparacion_no_escribe_vectores_ajenos_si_el_backend_cae_A_MITAD(fresh_db, monkeypatch):
    """The same V2-484 shape in the worst place: the function that REPAIRS, in a loop. The signature is checked on
    entry and then N rows are repaired; a backend that resolves to `hash` halfway through is not declared degraded
    (a configured hash is its own coherent space), and the entry permission remains in force.

    It uses the REAL signature, not a falsified `_embed_sig_ok`: a double that always says yes cannot measure a
    guard that exists precisely to say no. (The first attempt used the fixture that falsifies it and was
    red with and without the fix — meaning it measured nothing.)"""
    from memory import embeddings as mememb
    from memory import reembed as memreembed
    monkeypatch.setattr(memreembed, "stored_signature", lambda: "ollama:embeddinggemma:768")
    monkeypatch.setattr(mememb, "active_backend", lambda: mememb._backend)   # follows the backend, like the real one
    monkeypatch.setattr(mememb, "_active_model_name", lambda: "embeddinggemma")
    monkeypatch.setattr(memreembed, "_SPACE_CACHE", (0.0, True, None))

    ids = [memwriter.insert_memory(f"dato durable {i}", level="long", kind="fact") for i in range(4)]
    memdb.get_db().execute("DELETE FROM vec_memories")           # all pending repair

    denso = [0.02] * mememb.dim()
    llamadas = {"n": 0}

    def _embed_que_cae_a_mitad(_t):
        llamadas["n"] += 1
        if llamadas["n"] > 2:
            mememb._backend = "hash"                             # halfway through the loop the space stops matching
        return list(denso)

    monkeypatch.setattr(mememb, "_backend", "ollama")
    monkeypatch.setattr(mememb, "embed", _embed_que_cae_a_mitad)
    monkeypatch.setattr(mememb, "last_degraded", False)
    memrem.repair_embeddings(limit=100)

    con_vector = memdb.get_db().query_one(
        "SELECT COUNT(*) c FROM vec_memories WHERE memory_id IN (%s)" % ",".join("?" * len(ids)), tuple(ids))
    assert con_vector["c"] == 2      # the two before the failure, and none afterward


def test_a_stale_pending_marker_on_a_vectored_row_is_cleared(fresh_db):
    """Found live 2026-09-05: a row with a healthy native vector still carried `embed_pending` from an old
    outage. The repair pass only selects vector-LESS rows, so the marker was unclearable by construction and
    `hygiene()` counted it as pending forever — a health number nobody can trust. The repair entrance now
    clears markers whose vectors already exist."""
    import json as _json
    mid = memwriter.insert_memory("dato con vector sano", level="mid", kind="fact")
    db = memdb.get_db()
    assert db.query_one("SELECT 1 x FROM vec_memories WHERE memory_id=?", (mid,)) is not None
    meta = _json.loads(db.query_one("SELECT meta FROM memories WHERE id=?", (mid,))["meta"] or "{}")
    meta["embed_pending"] = "degraded"
    db.execute("UPDATE memories SET meta=?", (_json.dumps(meta),))
    assert memrem.hygiene()["embed_pending"] == 1
    memrem.repair_embeddings()
    assert memrem.hygiene()["embed_pending"] == 0, "the stale marker must be cleared by the repair entrance"
    assert db.query_one("SELECT 1 x FROM vec_memories WHERE memory_id=?", (mid,)) is not None  # vector untouched


def test_semantic_dedup_never_crosses_the_trust_boundary(fresh_db):
    """2026-09-05: quarantined external material (`trust: untrusted` — remember_external, cluster peers) must
    not join a trusted lineage in EITHER direction: an untrusted echo must never invalidate a trusted pill, and
    its shell must never inherit trusted edges. Same fence `_concept_groups` already applies to synthesis."""
    a = memwriter.insert_memory("le encanta el restaurante Casa Pepe", level="mid", kind="fact", weight=0.9)
    b = memwriter.insert_memory("el restaurante Casa Pepe le encanta", level="mid", kind="fact", weight=0.2,
                                meta={"trust": "untrusted"})
    assert memrem.semantic_dedup(threshold=0.95) == 0
    db = memdb.get_db()
    assert db.query_one("SELECT valid FROM memories WHERE id=?", (a,))["valid"] == 1
    assert db.query_one("SELECT valid FROM memories WHERE id=?", (b,))["valid"] == 1


def test_sim_table_fallback_agrees_without_numpy(fresh_db, monkeypatch):
    """The numpy matmul is an accelerator, never a dependency: with numpy unimportable, `_sim_table` falls back
    to the pure-Python dot product and returns the same similarities."""
    import sys
    vecs = {1: [1.0, 0.0], 2: [0.6, 0.8]}
    with_np = memrem._sim_table([1, 2], vecs)
    monkeypatch.setitem(sys.modules, "numpy", None)   # `import numpy` now raises → fallback path
    without_np = memrem._sim_table([1, 2], vecs)
    assert with_np(1, 2) == pytest.approx(without_np(1, 2)) == pytest.approx(0.6)
