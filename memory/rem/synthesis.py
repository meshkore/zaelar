"""REM's LLM phases, both with the model INJECTED by the caller (memory imports no brain): the paraphrase-index
backfill (1b) and concept synthesis into insights (3), with the insight fidelity gates."""
from __future__ import annotations

import os
import re as _re

from loguru import logger

from .. import db as _db
from .. import writer as _writer
from .common import _NUM_RE

MIN_GROUP = 4          # minimum pills of a concept to deserve synthesis
MAX_GROUPS = 8         # cap of groups synthesised per sleep (bounded cost)
MAX_INSIGHT_CHARS = 400  # 1-2 sentences; without a ceiling an insight can grow sleep after sleep


# ── phase 1b · PARAPHRASE index (V2-031 T2, injected LLM) ────────────────────────────────────────────────
def _paraphrase_limit_default() -> int:
    """Budget per sleep — same pattern as `_repair_limit_default()`, but THIS phase costs a real LLM call per
    pill, so the default is deliberately MODEST: the backlog drains over several nights.
    Configurable (§memory.rem_paraphrase_limit / ZAELAR_REM_PARAPHRASE_LIMIT)."""
    env = os.getenv("ZAELAR_REM_PARAPHRASE_LIMIT")
    if env:
        try:
            return max(1, int(env))
        except ValueError:
            pass
    try:
        from config import v2 as _v2
        return max(1, int((_v2.get("memory") or {}).get("rem_paraphrase_limit") or 30))
    except Exception:
        return 30


def index_paraphrases(paraphrase_fn, limit: int | None = None) -> int:
    """Backfills the paraphrase index: durables with NO `paraphrase_index` row yet, up to `limit`.
    `paraphrase_fn(text) -> [str, …]` is injected by the caller (the loop). Fail-open: without a hook, without
    vec, or on any per-pill failure, that pill just stays without paraphrases (still retrieved by its own
    embedding — this only ADDS surface). Returns the pills indexed with ≥1 paraphrase."""
    if paraphrase_fn is None:
        return 0
    db = _db.get_db()
    if not db.vec_available:
        return 0
    if limit is None:
        limit = _paraphrase_limit_default()
    rows = db.query(
        "SELECT m.id, m.text FROM memories m "
        "LEFT JOIN paraphrase_index p ON p.memory_id = m.id "
        "WHERE m.valid=1 AND m.level IN ('mid','long') AND m.kind NOT IN ('conv','concept','insight') "
        "AND p.memory_id IS NULL GROUP BY m.id LIMIT ?",
        (limit,),
    )
    done = 0
    empty = 0
    for r in rows:
        try:
            variants = paraphrase_fn(r["text"]) or []
        except Exception as e:  # noqa: BLE001
            logger.debug(f"rem.index_paraphrases: hook falló para #{r['id']}: {str(e)[:120]}")
            empty += 1
            continue
        if not variants:
            empty += 1
            continue
        if _writer.index_paraphrases(r["id"], variants) > 0:
            done += 1
    # A MUTE hook has to be VISIBLE: the hook returns [] on ANY problem, so «the whole channel is dead» read as
    # «nothing tonight» (the channel once stood at 0 rows since it was built). Only when work was ATTEMPTED and
    # NOTHING came out — with mixed results one failing pill is noise, not an outage.
    if empty and not done:
        logger.warning(f"rem.index_paraphrases: {empty} candidates and NOT ONE paraphrase — paraphrase channel mute")
        try:
            from voice import health_state
            health_state.record("memory", "degraded",
                                f"paraphrase channel mute: {empty} candidates, 0 indexed")
        except Exception:  # noqa: BLE001
            pass  # observability NEVER breaks the sleep cycle
    return done


# ── V2-104: insight fidelity — a deterministic backstop before the LLM gate ──────────────────────────────
def _proper_nouns(text: str) -> set[str]:
    """Capitalised words that do NOT open their sentence — proper-noun/entity candidates. The sentence-opening
    capital does not count (an almost certain false positive); the rest do."""
    nouns: set[str] = set()
    for sentence in _re.split(r"(?<=[.!?])\s+", text.strip()):
        words = sentence.split()
        for i, w in enumerate(words):
            core = w.strip(".,;:!?()\"'“”«»").strip()
            if i == 0 or len(core) < 3 or not core[0].isupper() or not core.isalpha():
                continue
            nouns.add(core)
    return nouns


def _grounded(insight: str, pills: list[str]) -> bool:
    """FREE backstop (no LLM): every figure/date and proper noun of the insight must appear in its source pills.
    It proves no SEMANTIC fidelity — only catches the crudest fabrication. The fine check is the injected
    `verify_fn`."""
    source = " ".join(pills).lower()
    for num in _NUM_RE.findall(insight):
        if num.lower() not in source:
            return False
    for noun in _proper_nouns(insight):
        if noun.lower() not in source:
            return False
    return True


# ── phase 3 · SYNTHESIS (injected LLM): concepts → insights ──────────────────────────────────────────────
def _concept_groups(min_group: int = MIN_GROUP, max_groups: int = MAX_GROUPS) -> list[dict]:
    """Groups of durables per graph CONCEPT node (most populated first). No LLM: a direct traversal."""
    db = _db.get_db()
    rows = db.query(
        "SELECT c.id AS cid, c.text AS concept, m.id AS mid, m.text AS pill FROM memories c "
        "JOIN edges e ON (e.from_id = c.id OR e.to_id = c.id) "
        "JOIN memories m ON m.id = (CASE WHEN e.from_id = c.id THEN e.to_id ELSE e.from_id END) "
        "WHERE c.kind='concept' AND m.valid=1 AND m.level IN ('mid','long') "
        "AND m.kind NOT IN ('conv','concept','insight') "
        "AND (m.meta IS NULL OR m.meta NOT LIKE '%\"trust\": \"untrusted\"%')",
    )
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(r["concept"], {"concept": r["concept"], "pills": [], "_ids": set()})
        if r["mid"] not in g["_ids"]:
            g["_ids"].add(r["mid"])
            g["pills"].append(r["pill"])
    out = [g for g in groups.values() if len(g["pills"]) >= min_group]
    out.sort(key=lambda g: -len(g["pills"]))
    for g in out:
        # V2-103: `synthesize()` needs the ids to DEMOTE the raw pills that fed the insight.
        g["ids"] = sorted(g.pop("_ids", set()))
    return out[:max_groups]


def _reject(concept: str, reason: str) -> None:
    """A rejected insight is a MEMORY failure, not a silent discard — same discipline as the hook failure below
    (a `logger.warning` among thousands of lines once went unseen for weeks)."""
    logger.warning(f"rem.synthesize: insight de «{concept}» rechazado — {reason}")
    try:
        from voice import health_state
        health_state.record("memory", "degraded", f"insight de «{concept}» rechazado: {reason}")
    except Exception:  # noqa: BLE001
        pass


def synthesize(synthesize_fn, min_group: int = MIN_GROUP, verify_fn=None) -> int:
    """Distils 1 insight per concept group and writes it with `slot=insight:<concept>` (rewritten each sleep, never
    accumulated). `synthesize_fn(groups)->[{concept,insight}]` is injected by the caller. Fail-open: no hook or no
    answer = 0 insights.

    V2-104: every insight passes a fidelity gate before it is written and its sources demoted. With `verify_fn`
    wired, IT IS THE ARBITER — a second LLM opinion in a FRESH call. `_grounded()` decides only when there is NO
    `verify_fn`: letting it veto first rejected faithful paraphrases (digit↔word, «nueve» → «9») the real verifier
    accepted. ASYMMETRIC on any rejection: the insight is not written and the sources are NOT demoted — the group
    retries next sleep. Since demotion (V2-103), a bad insight would DISPLACE the correct facts."""
    if synthesize_fn is None:
        return 0
    groups = _concept_groups(min_group=min_group)
    if not groups:
        return 0
    try:
        results = synthesize_fn(groups) or []
    except Exception as e:  # noqa: BLE001
        # NEVER silent: a hook failure is a MEMORY failure (a prompt `KeyError` once left this phase writing no
        # insight for weeks). Marked in `health_state` → the ◉ shows it. Still fail-open: the other phases run.
        logger.error(f"rem.synthesize: hook falló ({str(e)[:160]}) → sin insights este sueño")
        try:
            from voice import health_state
            health_state.record("memory", "outage", f"sueño REM sin insights: {str(e)[:120]}")
        except Exception:  # noqa: BLE001
            pass
        return 0
    written = 0
    for it in results:
        if not isinstance(it, dict):
            continue    # a malformed item from an injected hook must not kill the whole phase
        concept = (it.get("concept") or "").strip().lower()
        insight = (it.get("insight") or "").strip() if it.get("insight") else ""
        if not concept or not insight or len(insight) < 12:
            continue
        if len(insight) > MAX_INSIGHT_CHARS:
            _reject(concept, f"demasiado largo ({len(insight)} > {MAX_INSIGHT_CHARS} chars)")
            continue
        src = next((g for g in groups if g["concept"] == concept), None)
        pills = src["pills"] if src else []
        # `verify_fn`, when present, is the ARBITER — not `_grounded()` (a literal substring check that cannot
        # see «las nueve» = «las 9»). Semantic judgement is a MODEL's call, not a pattern's (V2-075).
        if verify_fn is not None:
            try:
                ok = bool(verify_fn(insight, pills))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"rem.synthesize: verify_fn falló ({str(e)[:120]}) → tratado como NO fiable")
                ok = False
            if not ok:
                _reject(concept, "la verificación por LLM no lo respalda")
                continue
        elif not _grounded(insight, pills):
            _reject(concept, "una cifra o un nombre propio no aparece en los datos fuente (sin verify_fn: solo backstop)")
            continue
        try:
            insight_id = _writer.insert_memory(
                insight, level="long", kind="insight", importance=0.65,
                slot=f"insight:{concept}",
                meta={"source": "rem", "concept": concept},
                concepts=[concept],
            )
            written += 1
            # V2-103: REM must RETIRE what it summarises — DEMOTE (never invalidate/delete) the raw pills so they
            # stop competing at full weight with the insight. Only an insight that passed the gates gets here.
            if src and src.get("ids"):
                _writer.demote_summarized(src["ids"], insight_id)
        except Exception:
            continue
    return written
