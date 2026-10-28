"""Sanctioned writes from OUTSIDE the voice turn: widgets, workers, connectors.

Split out VERBATIM (audit 2026-08-23). `remember_external` never touches `state` nor identity slots (V2-033).
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from nucleo.memory_agent.dossier import _derive_concepts  # noqa: F401
from nucleo.memory_agent.classify import classify
from nucleo.memory_agent import writer as _writer
from nucleo.memory_agent.gates import (  # noqa: F401
    _memslots,    _IDENTITY_SLOTS, _atom_value_invalid, _precision_reject_atom)


async def remember(item: dict[str, Any]) -> None:
    """Queues in memory whatever is worth saving. **Only writer** for the SlowBrain.

    `item`:
      - `text`         — the memory (required to write a `memories` entry).
      - `kind`         — 'fact'|'pref'|'summary'|'result'|'event'|'profile' (default: auto-classified).
      - `level`        — 'short'|'mid'|'long' (default: auto-classified; `None` = skip).
      - `importance`   — optional 0..1; `pinned` — bool.
      - `slot`         — canonical key for the singular fact (`operator.name`…) → EXACT supersede/dedup (V2-013).
      - `meta`         — dict/JSON: metadata capsule (source/path/raw/state_patch/said_at…) for the viewer/graph.
      - `ttl_days`     — optional float: expiration (`None` = never expires).
      - `state_patch`  — optional dict: shallow merge into the `state` table.
      - `auto`         — bool (default True): if the caller does not set `level`/`kind`/`state_patch`, `text` is
                         auto-classified with `classify()` so that profile data (name, location, etc.) is not lost.
    Best effort: all failures are swallowed (memory is not critical to closing the turn)."""
    if not isinstance(item, dict):
        return
    try:
        from memory import api as memory
    except Exception:
        return

    text = (item.get("text") or "").strip()
    level = item.get("level")
    kind = item.get("kind")
    importance = item.get("importance")
    pinned = bool(item.get("pinned", False))
    patch = item.get("state_patch") or {}
    slot = item.get("slot")
    meta = item.get("meta")
    ttl_days = item.get("ttl_days")
    concepts = item.get("concepts")   # V2-013 T126: lightweight concept labels → graph nodes/edges
    supersedes = item.get("supersedes")  # V2-565: ids of recently written slotless pills this fact corrects

    # Auto-classify to DERIVE the level when the caller did not set it (even if kind/importance were provided):
    # `remember({text, kind:"result"})` MUST be written — previously the `not kind` guard left it with level=None
    # and wrote nothing (`test_remember_writes_to_memory` was failing). Respect whatever the caller DID set (kind/patch/…).
    auto = bool(item.get("auto", True))
    if auto and text and level is None:
        plan = classify(text)
        if not patch:
            patch = plan["state_patch"] or {}
        level = plan["level"]
        kind = kind or plan["kind"]
        if importance is None:
            importance = plan["importance"]
        pinned = pinned or plan["pinned"]
        if slot is None:
            slot = plan.get("slot")

    # Concept backstop (T126): if it is DURABLE and the LLM did not label it, derive from keywords → guaranteed graph
    # coverage (so category recall does not depend on the small model's consistency).
    if not concepts and text and level in ("mid", "long"):
        concepts = _derive_concepts(text) or None

    if text and level:                          # `level=None` = skip explícito del clasificador
        try:
            memory.write(
                text,
                kind=kind or "fact",
                level=level,
                importance=importance,
                pinned=pinned,
                ttl_days=ttl_days,
                slot=slot,
                meta=meta,
                concepts=concepts,
                supersedes=supersedes,
            )
            _observe_write(kind or "fact", level, slot, meta)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"memory_agent.remember write falló: {e}")

    if isinstance(patch, dict) and patch:
        try:
            memory.set_state(patch)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"memory_agent.remember state_patch falló: {e}")


def _observe_write(kind, level, slot, meta) -> None:
    """One event per pill written, carrying its KIND: the viewer and the Master tell a `request` from a `result`."""
    try:
        from voice.observer import emit
        emit("memory", f"píldora escrita · {kind}", role="system",
             extra={"layer": "write", "pill_kind": kind, "level": level, "slot": slot or "",
                    "source": str((meta or {}).get("source") or "")})
    except Exception as e:  # noqa: BLE001 — observability NEVER breaks the memory
        logger.debug(f"memory_agent: write event not emitted: {e}")


async def remember_external(item: dict, *, source: str = "external") -> dict:
    """Write arriving from OUTSIDE the process (Brain Workers via `hbmem` → `POST /api/memory/remember`).

    Audit 2026-07-14: `remember(auto=True)` could derive a `state_patch`, so a worker OVERWROTE his identity in
    `state` past the V2-033 quarantine — what the same words spoken by VOICE would not do. Policy for this path:
      - **NEVER touches `state`** (a worker does not speak for the operator; `auto=False`, without state_patch).
      - **Precision gate** (P0a): a reified question/request is not persisted.
      - **Banned IDENTITY slots**: `--slot operator.name` and its family are DEGRADED to a standalone fact (the identity
        lineage is written only by the operator's turn); work slots (`goal.moto`, `weather:x`, namespaced) pass normally
        — exact superseding remains theirs.
      - **Stamped provenance** (`meta.source="worker:<id>"`); the KIND is the pill grammar's, a `result` only ever
        the circuit's verdict (`writer.result`, V2-825 F1). Returns `{ok, reason}` for the endpoint."""
    if not isinstance(item, dict):
        return {"ok": False, "reason": "bad-item"}
    text = (item.get("text") or "").strip()
    if not text:
        return {"ok": False, "reason": "empty"}
    kind = _writer.distilled_kind(item.get("kind"))     # the grammar's, never `result`: that is the circuit's door
    if _precision_reject_atom({"text": text, "kind": kind}, raw=text):
        return {"ok": False, "reason": "precision"}
    slot = _memslots.canonical(item.get("slot"))
    identity_dropped = False
    if slot and slot in _IDENTITY_SLOTS:
        slot, identity_dropped = None, True
    meta = dict(item.get("meta") or {})
    meta.setdefault("source", source)
    await remember({
        "text": text,
        "kind": kind,
        "level": item.get("level") or "mid",
        "importance": item.get("importance"),
        "ttl_days": item.get("ttl_days"),
        "slot": slot,
        "meta": meta,
        "auto": False,                          # never re-classify: this path does not derive state_patch
    })
    return {"ok": True, "identity_slot_dropped": identity_dropped}


# Serializes calls to ingest_utterance in the ORDER in which they were launched (testing marathon 2026-07-22):
# both real voice (nucleo.py) and the probe launch them as `fire-and-forget` (asyncio.create_task) to avoid blocking
# the turn — correct for latency, but without this, two consecutive, rapid turns ("note that my size is
# M" followed 2s later by "forget that about the size") can complete in the WRONG order: the forgetting action (fast,
# deterministic, no LLM) can finish and find nothing to invalidate BEFORE the reminder (slow,
# goes through the CORE/LLM) finishes writing — the "forgotten" data survives. A module-level lock ensures
# that each ingestion is processed from start to finish before the next one begins, in arrival order
# (asyncio.Lock is FIFO); it does not affect turn latency (it remains fire-and-forget from the caller).
