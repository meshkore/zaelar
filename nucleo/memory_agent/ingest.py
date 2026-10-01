"""The ingest pipeline: every operator utterance enters memory through here (single async lock).

Split out VERBATIM (audit 2026-08-23). Orchestrates the gates in order; the order IS the semantics.
"""
from __future__ import annotations

import asyncio
import re


def _pkg():
    """The package namespace, resolved LATE. `remember` must be called through here: the pre-split module was
    one namespace, and tests (test_slot_supersede_guard) patch `memory_agent.remember` by plain assignment to
    capture writes. A binding imported at module top would keep pointing at the real one and the patch would
    stop reaching the pipeline — silently, which is the worst way."""
    from nucleo import memory_agent
    return memory_agent


from loguru import logger

from nucleo.memory_agent.classify import classify
from nucleo.memory_agent.dossier import _state_lines  # noqa: F401
from nucleo.memory_agent.gates import (  # noqa: F401
    _memslots,    _GARBLE_GUARD_SLOTS, _IDENTITY_SLOTS, _OPERATOR_IDENTITY_SLOTS, _PATCH_TO_SLOT,
    _SLOT_TO_STATE_FIELD, _atom_is_nonfact,
    _atom_value_invalid, _established_slot_value, _plausibility_demote, _precision_reject_atom,
    _is_ephemeral_directive, _is_vague_request, _report_self_declared_change_ignored, _slot_for_patch,
    _slot_supersede_guard, _writer_canon)
from nucleo.memory_agent.lang_marks import (  # noqa: F401
    _ASSISTANT_QUERY_RE, _COMMITMENT_RE, _CORRECTION_RE, _CORRECTION_TRAILING_NO_RE, _CORRECTION_YANO_RE,
    _EMPTY_MSG_RE, _FORGET_HARD_RE, _FORGET_RE, _FORGET_TRAILING_RE, _HEALTH_RE, _INCOMING_MSG_RE,
    _NEGATION_PREFIX_RE, _OBSERVATION_RE, _PROFILE_DURABLE_RE, _RELOCATION_RE, _REVERSAL_RE, _ROUTINE_RE,
    _UNFORGET_RE, _looks_like_injection, _talks_about_the_operator)


_INGEST_LOCK = asyncio.Lock()

# The HOME loop for ingestion (V2-601 T-06, audit 2026-09-05). `ingest_utterance` is fired from BOTH event
# loops — the voice job-thread's (nucleo.py, create_task) and uvicorn's (probe, widgets ctx.ingest,
# messaging) — and an `asyncio.Lock` cannot span loops: reproduced by the audit, an UNCONTENDED cross-loop
# acquire never breaks (why this never blew up loudly), but a CONTENDED one hangs the waiter forever and
# poisons the lock, after which every contended ingest raises RuntimeError inside a fire-and-forget task —
# memory writes silently lost until restart. The engine's own rule since INI-012 is that cross-loop delivery
# marshals (`call_soon_threadsafe` / `run_coroutine_threadsafe`, the browser_search/energy_meter/identity
# pattern): every ingest now RUNS on the one home loop the lifespan registers, so the lock only ever lives on
# one loop. `set_loop` never called (unit tests, standalone) → single-loop process → behavior unchanged.
_HOME_LOOP: "asyncio.AbstractEventLoop | None" = None


def set_loop(loop) -> None:
    global _HOME_LOOP
    _HOME_LOOP = loop


async def ingest_utterance(text: str, *, role: str = "operator") -> dict:
    home = _HOME_LOOP
    try:
        here = asyncio.get_running_loop()
    except RuntimeError:
        here = None
    if home is not None and here is not None and home is not here and not home.is_closed():
        fut = asyncio.run_coroutine_threadsafe(_ingest_home(text, role=role), home)
        return await asyncio.wrap_future(fut)
    return await _ingest_home(text, role=role)


async def _ingest_home(text: str, *, role: str = "operator") -> dict:
    async with _INGEST_LOCK:
        result = await _ingest_utterance_locked(text, role=role)
        # Ingestion itself already runs off the voice/chat hot path. Publish the completed state into the
        # FlashBrain cache here, so the next utterance sees a correction/move immediately instead of one turn late.
        try:
            from nucleo.flash import memory_cache
            await memory_cache.refresh()
        except Exception:
            pass
        return result


async def _ingest_utterance_locked(text: str, *, role: str = "operator") -> dict:
    """Entry point for "something the operator said/wrote" in a turn — the writing CORE (V2-013).

    Flow (LLM while WRITING, off-hot-path; the voice turn never waits for this):
      1. Obvious trivia/command → cheaply DISCARD, without LLM (anti-noise).
      2. Otherwise, the **local LLM processor** (`nucleo/mem_processor`) DISTILLS the turn into curated pills
         (canonical datum + dest + importance + ttl + slot + state_patch) and saves them through the queue.
      3. **Fail-open**: if the local model is unavailable / fails / returns nothing useful → fall back to the
         **regex heuristic** (`classify`) so the profile (name, location…) is not lost. Memory never stops writing.

    Returns a summary dict (`{"source": "llm"|"heuristic"|"discard", "atoms": n, ...}`) for debugging/tests. It does not
    deliver by voice or block the turn. Ignores `role` values other than 'operator'."""
    plan = classify(text)
    # V2-778 F1 — the gates an utterance crosses before anything is written live in
    # `nucleo/memory_agent/ingest_steps.py`.
    _blk = await _ing_steps.gate_the_utterance(
        plan=plan,
        role=role,
        text=text,
    )
    if isinstance(_blk, tuple):
        return _blk[1] if len(_blk) == 2 else _blk[1:]
    if '_is_corr' in _blk:
        _is_corr = _blk['_is_corr']
    if 'atoms' in _blk:
        atoms = _blk['atoms']
    if 'st' in _blk:
        st = _blk['st']
    if 't' in _blk:
        t = _blk['t']
    if 'text' in _blk:
        text = _blk['text']

    # V2-778 F1 — filing the atoms the distiller returned lives in `nucleo/memory_agent/ingest_steps.py`.
    _blk = await _ing_steps.file_the_atoms(
        _is_corr=_is_corr,
        atoms=atoms,
        plan=plan,
        st=locals().get('st'),
        t=t,
    )
    if isinstance(_blk, tuple):
        return _blk[1] if len(_blk) == 2 else _blk[1:]

    # 3. FAIL-OPEN (model unavailable): regex heuristic (profile/desire/fact). Same as before V2-013.
    if plan["level"] or plan["state_patch"]:
        # V2-033: the same precision GATE as the LLM output — raw text is a reified question/request
        # o directiva efímera → no se persiste; identidad en conflicto → degrada (aquí como plan, misma semántica).
        plan_atom = {"text": text, "kind": plan["kind"], "dest": ("state" if plan["state_patch"] else "long"),
                     "slot": plan.get("slot"), "state_patch": plan["state_patch"],
                     "importance": plan["importance"]}
        if _precision_reject_atom(plan_atom, raw=t):
            return {"source": "discard", "atoms": 0, "reason": "precision", "plan": plan}
        plan_atom = _plausibility_demote(plan_atom, state=st, is_correction=_is_corr)
        demoted = plan_atom.get("dest") == "long" and plan["state_patch"] and not plan_atom.get("state_patch")
        await _pkg().remember({
            "text": text,
            "level": ("long" if demoted else plan["level"]),
            "kind": plan["kind"],
            "importance": plan_atom.get("importance", plan["importance"]),
            "pinned": False if demoted else plan["pinned"],
            "state_patch": ({} if demoted else plan["state_patch"]),
            "slot": (None if demoted else plan.get("slot")),
            # demote por conflicto de identidad → CUARENTENA (trust=untrusted): no aflora en recall/prompt.
            "ttl_days": plan.get("ttl_days"),
            "meta": ({"source": "voice", "path": "heuristic-quarantine", "trust": "untrusted"} if demoted
                     else {"source": "voice", "path": "heuristic"}),
            "auto": False,                      # ya clasificamos aquí; evitamos re-clasificar dentro
        })
        return {"source": ("heuristic-demoted" if demoted else "heuristic"), "atoms": 1, "plan": plan}
    return {"source": "discard", "atoms": 0, "plan": plan}


def _sanitize_state_patch(patch: dict | None) -> dict:
    """(V2-050) The CORE sometimes uses the SLOT NAME as the STATE key ('goal.current' instead of the
    'objetivo' field) → a STRAY key that another update of the same fact NEVER supersedes (bot v1 #28: the old goal
    'septiembre' persisted under 'goal.current' even though 'objetivo' was already the new one). Rename each key that is a
    SLOT to its canonical `state_field`; keys that are already state fields (hardware/car/language…) are preserved."""
    out: dict = {}
    for k, v in (patch or {}).items():
        out[_memslots.state_field(k) or k] = v
    return out


def _correction_whitelist() -> set[int]:
    """The ids the distiller was allowed to aim at (V2-565) — recomputed here rather than threaded through the
    call chain: `correction_targets()` is deterministic over the DB, so offer-time and act-time agree except
    for a benign race (a pill written in between enlarges the set; one superseded in between is re-checked by
    the writer guard anyway). Fail-open to EMPTY: no whitelist, no reach."""
    try:
        from memory import api as _mem_api
        return {int(c["id"]) for c in _mem_api.correction_targets()}
    except Exception:  # noqa: BLE001
        return set()


async def _write_atom(atom: dict, *, raw: str = "") -> None:
    """Writes ONE pill from the LLM processor through the façade (async queue). Maps `dest` → layer:
    `state` = sets state + durable `long/pinned` trace with slot; `long`/`short` = memory with its ttl/slot."""
    dest = atom.get("dest")
    meta = {"source": "voice", "path": "llm", "raw": (raw or "")[:120]}
    _patch = _sanitize_state_patch(atom.get("state_patch"))   # slot-name→state_field (no claves stray, V2-050)
    atom = dict(atom, state_patch=_patch)
    if _patch:
        meta["state_patch"] = _patch
    # The atom's canonical `value` is PERSISTED (P0d, 2026-08-19). It was computed by the distiller, used to build
    # `state_patch`, and then thrown away — so for the five identity slots with no `state_field`
    # (birthday/phone/email/address/diet) nothing on the row recorded WHAT value the slot holds, only a sentence
    # containing it. Comparing sentences instead is not a substitute: "Su cumpleaños es el 12 de febrero" and "El
    # cumpleaños de Marta es el 3 de mayo" share the token "cumpleaños", which the refinement test reads as the
    # same entity. The value is the thing the slot is ABOUT; without it the supersede guard below cannot exist.
    _val = atom.get("value")
    if isinstance(_val, str) and _val.strip() and atom.get("slot"):
        meta["value"] = _val.strip()[:120]
    # V2-033 P0b: átomo degradado por conflicto de identidad (garble) → CUARENTENA (trust=untrusted): recuperable
    # only through an explicit query, never surfaces in recall/prompt (the retriever and recent_short exclude it).
    if atom.get("_quarantine"):
        meta["trust"] = "untrusted"
        meta["path"] = "plausibility-quarantine"
    if dest == "state":
        await _pkg().remember({
            "text": atom["text"],
            "level": "long",
            "kind": atom.get("kind") or "profile",
            "importance": atom.get("importance", 0.9),
            "pinned": True,
            "state_patch": atom.get("state_patch") or {},
            "slot": atom.get("slot"),
            "meta": meta,
            "concepts": atom.get("concepts"),
            "auto": False,
        })
    elif dest in ("long", "short"):
        await _pkg().remember({
            "text": atom["text"],
            "level": dest,
            "kind": atom.get("kind") or "fact",
            "importance": atom.get("importance", 0.5),
            "pinned": False,
            "ttl_days": atom.get("ttl_days"),
            "slot": atom.get("slot"),
            "meta": meta,
            "concepts": atom.get("concepts"),
            # V2-565: whitelisted ids this corrected fact supersedes — applied by the writer, the single door.
            "supersedes": atom.get("supersedes") or None,
            "auto": False,
        })


def maintain_state(patch: dict) -> dict:
    """Updates the operator profile (`state`) alongside the consolidator. Shallow merge. Direct."""
    from memory import api as memory
    return memory.set_state(patch or {})


from nucleo.memory_agent import ingest_steps as _ing_steps  # noqa: E402 — V2-778 F1, reads this module back
