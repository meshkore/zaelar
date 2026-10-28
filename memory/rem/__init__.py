"""memory/rem — memory's DEEP sleep ("REM phase", V2-056).

The consolidator (`consolidator.py`, hourly) is LIGHT sleep: cheap mechanics (promote/exact dedup/decay/prune/
evict). This is the DEEP cycle (daily by default), where memory is ORDERED, RELATED and SYNTHESISED. Each phase is
isolated (one failure does not end the sleep) and all are off the hot path:

  1. `repair_embeddings()` — re-embeds pills WITHOUT a vector or marked `meta.embed_pending`; the semantic index
     SELF-REPAIRS every night (repair.py).
  1b. `index_paraphrases(hook)` — backfills the write-time paraphrase index (synthesis.py).
  2. `semantic_dedup()` — dedup by MEANING (cosine over existing vectors, no LLM): near-duplicates without a slot
     merge, edges move over, the rest is invalidated with `superseded_by` — never deleted (dedup.py).
  3. `synthesize(hook)` — the LLM part, INJECTED by the caller (memory imports no brain): durables grouped by
     CONCEPT distil into 1 INSIGHT per group (`slot=insight:<concept>`, rewritten each sleep) (synthesis.py).
  4. `hygiene()` — the day's check: % of heuristic writes (a downed distiller must raise an alert),
     `embed_pending` left, sizes. The REPORT goes back to the caller and out on the bus (`memory.rem`).

Cadence: `due()` / marker `sys_kv.rem_last_run` (config §memory.rem_every_hours, default 24h; env ZAELAR_REM_SECS
wins). Kill-switch: ZAELAR_REM=0. Everything is deterministic except phase 3 (fail-open hook → no insights).
"""
from __future__ import annotations

import os
import time

from loguru import logger

from .. import db as _db
from .common import _cos, _now, _unpack  # noqa: F401
from .dedup import SEM_DEDUP_THRESHOLD, _conflicting_numbers, _sim_table, semantic_dedup  # noqa: F401
from .repair import (  # noqa: F401
    _DEGRADED_STREAK_STOP, _FOREIGN_MATCH, _clear_stale_pending, _drop_foreign_vectors, _looks_padded,
    _pending_without_vector, _repair_limit_default, _report_repair_backlog, _report_repair_blocked,
    repair_embeddings,
)
from .synthesis import (  # noqa: F401
    MAX_GROUPS, MAX_INSIGHT_CHARS, MIN_GROUP, _concept_groups, _grounded, _paraphrase_limit_default, _proper_nouns,
    _reject, index_paraphrases, synthesize,
)

HEURISTIC_ALERT_PCT = 50.0
HEURISTIC_ALERT_MIN = 10


def enabled() -> bool:
    return os.getenv("ZAELAR_REM", "1").strip().lower() not in ("0", "false", "no", "off")


def every_s() -> float:
    env = os.getenv("ZAELAR_REM_SECS")
    if env:
        return max(3600.0, float(env))
    try:
        from config import v2 as _v2
        return max(3600.0, float((_v2.get("memory") or {}).get("rem_every_hours") or 24) * 3600.0)
    except Exception:
        return 24 * 3600.0


def due(now: int | None = None) -> bool:
    """Is deep sleep due? A persistent marker (survives restarts). Without one, it seeds `now` (the first REM
    comes one cycle AFTER the system starts, never at boot)."""
    if not enabled():
        return False
    now = now or _now()
    from ..consolidator import _kv_get, _kv_set
    last = _kv_get("rem_last_run")
    if last is None:
        _kv_set("rem_last_run", str(now))
        return False
    return (now - int(float(last))) >= every_s()


# ── phase 4 · the day's hygiene ──────────────────────────────────────────────────────────────────────────
def hygiene(window_s: int = 86400) -> dict:
    """Health check of the last 24h of WRITING — the guard that was missing (the distiller was down for 2 days and
    the heuristic % soared with nobody seeing it)."""
    db = _db.get_db()
    since = _now() - window_s
    total = db.query_one(
        "SELECT COUNT(*) c FROM memories WHERE created >= ? AND kind NOT IN ('conv','concept')", (since,))["c"]
    heur = db.query_one(
        "SELECT COUNT(*) c FROM memories WHERE created >= ? AND kind NOT IN ('conv','concept') "
        "AND json_extract(meta, '$.path') LIKE 'heuristic%'", (since,))["c"]
    pending = db.query_one(
        "SELECT COUNT(*) c FROM memories WHERE valid=1 AND json_extract(meta, '$.embed_pending') IS NOT NULL",
        ())["c"]
    pct = round(100.0 * heur / total, 1) if total else 0.0
    return {
        "written_24h": total,
        "heuristic_24h": heur,
        "heuristic_pct": pct,
        "embed_pending": pending,
        "alert": bool(total >= HEURISTIC_ALERT_MIN and pct >= HEURISTIC_ALERT_PCT),
    }


# ── orchestration ────────────────────────────────────────────────────────────────────────────────────────
def run(synthesize_fn=None, verify_fn=None, paraphrase_fn=None) -> dict:
    """One DEEP sleep cycle. Synchronous (the caller wraps it in `asyncio.to_thread`); each phase isolated.
    `verify_fn` (V2-104) is `synthesize()`'s second fidelity gate, optional; `paraphrase_fn` (V2-031 T2) feeds
    `index_paraphrases()`, optional and independent."""
    t0 = time.time()
    report: dict = {}
    for name, fn in (("repaired", repair_embeddings),
                     ("paraphrased", lambda: index_paraphrases(paraphrase_fn)),
                     ("sem_deduped", semantic_dedup),
                     ("insights", lambda: synthesize(synthesize_fn, verify_fn=verify_fn)),
                     ("hygiene", hygiene)):
        try:
            report[name] = fn()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"rem.{name} falló: {str(e)[:140]} → fase saltada")
            report[name] = None
    from ..consolidator import _kv_set
    _kv_set("rem_last_run", str(_now()))
    report["ms"] = round((time.time() - t0) * 1000)
    try:
        import bus
        bus.emit_sync("memory.rem", dict(report))
    except Exception:
        pass
    logger.info(f"sueño REM: {report}")
    return report
