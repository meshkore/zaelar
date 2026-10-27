"""memory/dedup_thresholds.py — the semantic-dedup thresholds, PER EMBEDDING MODEL (V2-824).

Two places merge memories by MEANING without an LLM: the writer at insert time (`writer._find_semantic_dup`,
an L2 distance over normalised vectors) and the REM phase (`rem.semantic_dedup`, a cosine over the stored
vectors). Both thresholds are GEOMETRY: they describe how far apart two phrasings of one fact land in ONE model's
space. They were measured on `embeddinggemma` (writer 0.45 on 2026-07-12 via the test bot; REM 0.86 on
2026-07-20 against the operator's database) and they have no meaning in any other model's space — the same
0.45 measured live with a fastembed backend fused two completely unrelated sentences (audit 2026-07-26).

So the thresholds live HERE, keyed by model, and the rule is:

  · the active model has a row → semantic dedup runs with that row's numbers;
  · it has none → semantic dedup is OFF in both places and the writer falls back to what it already does —
    exact-text and slot dedup, deterministic, no false positives. A near-duplicate that slips through is
    harmless; a merge that loses a fact is not.

**No value is invented.** The titular (`text-embedding-3-small`) has no row on purpose: its numbers come from
`python -m tests.memory.benchmarks.calibrate_dedup --db <copy of a real zaelar.db>`, which prints suggested thresholds measured on
echoes of one fact vs same-entity different facts vs negations. Only a measurement writes a row here.

An env override (`MEM_DEDUP_MAX_DIST` for the writer, `ZAELAR_REM_DEDUP_SIM` for REM) still applies to the
ACTIVE model: it is the operator stating a calibration by hand, and it wins over the table and over «no row».
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("zaelar.memory.dedup_thresholds")

#: model name (as the backend reports it, tag stripped) → calibrated thresholds. Match is by prefix on the
#: tag-less name so `embeddinggemma:latest` and `embeddinggemma:300m` share the row — they are the same model.
CALIBRATED: dict[str, dict] = {
    "embeddinggemma": {
        "writer_max_dist": 0.45,   # L2 on L2-normalised vectors: same fact in other words ≤0.51; same entity, other fact ≥0.80
        "rem_min_sim": 0.86,       # cosine: echoes of one task 0.82-0.90; at 0.92 nothing merged
        "measured": "writer 2026-07-12 (test bot) · REM 2026-07-20 (operator's database)",
    },
}

_FALSY = ("0", "false", "no", "off")


def _bare(name: str) -> str:
    return (name or "").strip().lower().split(":")[0]


def for_model(model: str) -> dict | None:
    """The calibrated row for `model`, or None when nobody measured it."""
    b = _bare(model)
    if not b:
        return None
    for key, row in CALIBRATED.items():
        if b == key or b.startswith(key):
            return dict(row)
    return None


def active_model() -> str:
    """The embedding model whose space the vectors are in RIGHT NOW. `hash` and `fastembed` are not models anybody
    calibrated (hash is lexical; fastembed loads its own default and mislabels it), so they resolve to no row."""
    from . import embeddings as _emb
    backend = _emb.active_backend()
    if backend not in ("cloud", "ollama"):
        return ""
    return _emb._active_model_name()


def active() -> dict | None:
    return for_model(active_model())


def semantic_dedup_enabled() -> bool:
    """The kill switch, shared by both doors: `MEM_SEMANTIC_DEDUP=0` turns semantic dedup off everywhere."""
    return os.getenv("MEM_SEMANTIC_DEDUP", "1").strip().lower() not in _FALSY


def _env_float(name: str, raw: str) -> float | None:
    """A hand calibration that is not a number turns semantic dedup OFF — and says so, once per call site."""
    try:
        return float(raw)
    except ValueError:
        logger.warning("%s=%r is not a number — semantic dedup stays OFF for the active model", name, raw)
        return None


def writer_max_dist() -> float | None:
    """The writer's insert-time threshold for the ACTIVE model, or None → semantic dedup off at insert."""
    if not semantic_dedup_enabled():
        return None
    env = os.getenv("MEM_DEDUP_MAX_DIST", "").strip()
    if env:
        return _env_float("MEM_DEDUP_MAX_DIST", env)
    row = active()
    return float(row["writer_max_dist"]) if row else None


def rem_min_sim() -> float | None:
    """REM's cosine threshold for the ACTIVE model, or None → the REM semantic pass is skipped."""
    if not semantic_dedup_enabled():
        return None
    env = os.getenv("ZAELAR_REM_DEDUP_SIM", "").strip()
    if env:
        return _env_float("ZAELAR_REM_DEDUP_SIM", env)
    row = active()
    return float(row["rem_min_sim"]) if row else None
