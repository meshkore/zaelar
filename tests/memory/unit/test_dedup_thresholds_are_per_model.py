"""The semantic-dedup thresholds belong to ONE embedding model (V2-824).

The writer's insert-time distance (0.45) and REM's cosine (0.86) were measured on `embeddinggemma`. Applied to
another model's geometry they are noise — measured live on fastembed, the same 0.45 fused two unrelated
sentences and the new fact was lost (audit 2026-07-26). So:

  · `memory/dedup_thresholds.py` holds a row PER MODEL and both doors read it for the ACTIVE model;
  · a model with no row — the cloud titular, on purpose, until `python -m tests.memory.benchmarks.calibrate_dedup` measures it —
    gets NO semantic dedup: the writer keeps its exact-text and slot dedup, REM skips the pass and says so;
  · an env override is the operator's hand calibration for the active model and wins;
  · the calibration script runs on a COPY of a database and PRINTS — it never writes the table.
"""
from __future__ import annotations

import json
import shutil

import pytest

from memory import db as memdb
from memory import dedup_thresholds as thr
from memory import embeddings as emb
from memory import rem as memrem
from memory import writer as memwriter

_DIM = 768


def _hash_vec(t: str) -> list[float]:
    return emb._l2_normalize(emb._fit_dim(emb._hash_embed(t, _DIM), _DIM))


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("MEM_DEDUP_MAX_DIST", raising=False)
    monkeypatch.delenv("ZAELAR_REM_DEDUP_SIM", raising=False)
    monkeypatch.delenv("MEM_SEMANTIC_DEDUP", raising=False)
    emb.reset()
    yield
    emb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _as(monkeypatch, provider: str, model: str, vectors=None):
    """Declare the active model; `vectors(texts)` is the fake provider when one is needed."""
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": provider, "embed_model": model})
    if provider == "ollama":
        monkeypatch.setattr(emb, "_ollama_embed", lambda texts, *, timeout=None: vectors(texts))
    elif provider == "openai":
        monkeypatch.setattr(emb, "_cloud_embed", lambda texts, *, timeout=None: vectors(texts))
    emb.reset()


# ── the table ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_embeddinggemma_is_calibrated_and_the_tag_does_not_matter():
    for name in ("embeddinggemma", "embeddinggemma:latest", "embeddinggemma:300m"):
        row = thr.for_model(name)
        assert row and row["writer_max_dist"] == 0.45 and row["rem_min_sim"] == 0.86


def test_the_cloud_titular_is_NOT_calibrated_on_purpose():
    from config import models as table
    titular = table.titular("embeddings")["model"]
    assert thr.for_model(titular) is None, (
        f"{titular} has a row — only `python -m tests.memory.benchmarks.calibrate_dedup` on a real database may write one")


@pytest.mark.parametrize("backend", ["hash", "fastembed"])
def test_the_safety_nets_are_never_calibrated(monkeypatch, backend):
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": backend, "embed_model": "embeddinggemma"})
    monkeypatch.setattr(emb, "_fastembed_embed", lambda texts: [[0.1] * _DIM for _ in texts])
    emb.reset()
    assert thr.active() is None and thr.writer_max_dist() is None and thr.rem_min_sim() is None


def test_an_env_override_is_a_hand_calibration_for_the_active_model(monkeypatch):
    _as(monkeypatch, "openai", "text-embedding-3-small", lambda t: [_hash_vec(x) for x in t])
    assert thr.writer_max_dist() is None
    monkeypatch.setenv("MEM_DEDUP_MAX_DIST", "0.3")
    monkeypatch.setenv("ZAELAR_REM_DEDUP_SIM", "0.9")
    assert thr.writer_max_dist() == 0.3 and thr.rem_min_sim() == 0.9
    monkeypatch.setenv("MEM_SEMANTIC_DEDUP", "0")
    assert thr.writer_max_dist() is None and thr.rem_min_sim() is None, "the kill switch beats everything"


# ── the writer's door ─────────────────────────────────────────────────────────────────────────────────────────

def test_on_the_uncalibrated_titular_two_paraphrases_are_two_rows(fresh_db, monkeypatch):
    """Vectors IDENTICAL on purpose: with any threshold at all the second write would merge into the first. It
    does not, because the model has no row — exact-text dedup still works, meaning-level dedup is off."""
    _as(monkeypatch, "openai", "text-embedding-3-small", lambda t: [_hash_vec("same") for _ in t])
    a = memwriter.insert_memory("Su jefa se llama Laura.", level="long", kind="fact")
    b = memwriter.insert_memory("Laura es su jefa.", level="long", kind="fact")
    assert a != b
    c = memwriter.insert_memory("Su jefa se llama Laura.", level="long", kind="fact")
    assert c == a, "exact dedup is untouched"


def test_on_the_calibrated_model_the_same_vectors_merge(fresh_db, monkeypatch):
    _as(monkeypatch, "ollama", "embeddinggemma", lambda t: [_hash_vec("same") for _ in t])
    a = memwriter.insert_memory("Su jefa se llama Laura.", level="long", kind="fact")
    b = memwriter.insert_memory("Laura es su jefa.", level="long", kind="fact")
    assert a == b, "distance 0 ≤ 0.45: the calibrated model merges the echo"


def test_the_writer_reads_the_threshold_from_the_table_not_from_a_constant(monkeypatch):
    assert not hasattr(memwriter, "SEMANTIC_DEDUP_MAX_DIST"), "the number moved to memory/dedup_thresholds.py"
    _as(monkeypatch, "ollama", "embeddinggemma", lambda t: [_hash_vec(x) for x in t])
    assert memwriter.semantic_dedup_max_dist() == 0.45


# ── REM's door ────────────────────────────────────────────────────────────────────────────────────────────────

def test_rem_skips_the_pass_on_an_uncalibrated_model_and_says_so(fresh_db, monkeypatch, caplog):
    _as(monkeypatch, "openai", "text-embedding-3-small", lambda t: [_hash_vec("same") for _ in t])
    monkeypatch.setenv("MEM_SEMANTIC_DEDUP", "1")
    memwriter.insert_memory("tiene cita para la ITV el jueves", level="mid", kind="fact", weight=0.8)
    memwriter.insert_memory("el jueves tiene cita para la ITV", level="mid", kind="fact", weight=0.5)
    # (the writer did not merge them: uncalibrated model)
    assert memdb.get_db().query_one("SELECT COUNT(*) c FROM memories WHERE valid=1 AND level='mid'")["c"] == 2
    import logging
    caplog.set_level(logging.INFO)
    assert memrem.semantic_dedup() == 0
    assert memdb.get_db().query_one("SELECT COUNT(*) c FROM memories WHERE valid=1 AND level='mid'")["c"] == 2
    assert not hasattr(memrem, "SEM_DEDUP_THRESHOLD")


def test_rem_merges_on_the_calibrated_model(fresh_db, monkeypatch):
    monkeypatch.setenv("MEM_SEMANTIC_DEDUP", "0")        # keep the WRITER out so REM sees both rows
    _as(monkeypatch, "ollama", "embeddinggemma", lambda t: [_hash_vec("same") for _ in t])
    memwriter.insert_memory("tiene cita para la ITV el jueves", level="mid", kind="fact", weight=0.8)
    memwriter.insert_memory("el jueves tiene cita para la ITV", level="mid", kind="fact", weight=0.5)
    monkeypatch.delenv("MEM_SEMANTIC_DEDUP")
    assert memrem.semantic_dedup() == 1


def test_an_explicit_threshold_still_works_whatever_the_model(fresh_db, monkeypatch):
    """The REM tests pass a threshold by hand on the hash backend: an explicit number is an explicit number."""
    monkeypatch.setenv("MEM_SEMANTIC_DEDUP", "0")
    _as(monkeypatch, "hash", "")
    memwriter.insert_memory("tiene cita para la ITV el jueves 23", level="mid", kind="fact", weight=0.8)
    memwriter.insert_memory("el jueves 23 tiene cita para la ITV", level="mid", kind="fact", weight=0.5)
    monkeypatch.delenv("MEM_SEMANTIC_DEDUP")
    assert memrem.semantic_dedup(threshold=0.95) == 1


# ── the calibration script ────────────────────────────────────────────────────────────────────────────────────

def test_the_calibration_script_measures_a_copy_and_prints_without_writing(fresh_db, tmp_path, monkeypatch, capsys):
    from tests.memory.benchmarks import calibrate_dedup as cal
    _as(monkeypatch, "ollama", "embeddinggemma", lambda t: [_hash_vec(x) for x in t])
    monkeypatch.setenv("MEM_SEMANTIC_DEDUP", "0")
    a = memwriter.insert_memory("Le gusta el cine coreano.", level="long", kind="pref", concepts=["cine"])
    memwriter.insert_memory("Vio tres películas coreanas en marzo.", level="long", kind="event", concepts=["cine"])
    memwriter.index_paraphrases(a, ["Disfruta de las películas de Corea."])
    memwriter.insert_memory("Laura es su jefa.", level="long", kind="fact", concepts=["trabajo"])
    memwriter.insert_memory("Laura le pidió el informe.", level="long", kind="event", concepts=["trabajo"])
    copy = tmp_path / "copy.db"
    memdb.get_db().conn.commit()
    memdb.get_db().conn.execute("PRAGMA wal_checkpoint(FULL)")   # WAL: the rows are not in the main file yet
    shutil.copy(memdb.db_path(), copy)
    before = dict(thr.CALIBRATED)

    assert cal.main(["--db", str(copy), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["model"] == "embeddinggemma"
    by = {c["class"].split(" ")[0]: c for c in report["classes"]}
    assert by["echoes"]["n"] == 1, "the stored paraphrase is the echo"
    assert by["same"]["n"] >= 1, "two pills about one concept are the same-entity pair"
    assert by["negations"]["n"] >= 1, "«le gusta» → «no le gusta»"
    assert "verdict" in report["suggested"]
    assert thr.CALIBRATED == before, "the script prints a suggestion; a human writes the row"


def test_the_negation_rewrite_is_deterministic_and_conservative():
    from tests.memory.benchmarks.calibrate_dedup import negate
    assert negate("Le gusta el cine coreano.") == "no Le gusta el cine coreano."
    assert negate("Vive en Madrid.") == "no Vive en Madrid."
    assert negate("She is a doctor.") == "She is not a doctor."
    assert negate("No le gusta el pescado.") is None, "already negative: skipped, never double-negated"
    assert negate("Madrid.") is None, "no verb a rule knows: skipped, counted, never guessed"
