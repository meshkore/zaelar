"""nucleo/memory_agent.py — the SlowBrain's ★ MEMORY agent. V2-006 · T81 (V2-013 enhancement).

Central piece of deliberation. Three facets:

  - `compose_context(prompt, budget)` — provides **ONLY what is necessary** for one turn (it does not dump the entire store):
    always-injected state (`memory.state()`, µs) + hybrid vec+FTS recall via RRF (`memory.query`), truncated
    to the token budget. **Cheap heuristic 90% of the time** (the retriever's rel+rec+imp+uso score already ranks results);
    a **cheap LLM router** enters ONLY if recall is ambiguous/poor (short query or weak results), to
    rephrase/expand the query — best-effort, cached (if there is no model → skipped). Model PER INVOCATION.
  - `classify(text)` — decides WHERE to store each item (V2-013): operator profile (name, location, treatment,
    hardware, car) → `state_patch` + durable trace `level='long', pinned=True`; wants/preferences →
    `level='long'`; trivia (greetings/commands) → skip; everything else → `level='mid'` (deliberation). Regex heuristic es/en
    first (µs, provider-agnostic); cheap LLM ONLY as a fallback. It is the fast-deciding "heart": without
    it, `state` remains empty even when the operator says their name during a normal turn.
  - `remember(item)` — is the **ONLY** one that writes to `memory/` from the SlowBrain. If the caller does not set a destination
    (`level`/`kind`/`state_patch`), it auto-classifies the `text` so nothing is lost. It maintains the `state` table
    (operator profile) alongside the consolidator. `ingest_utterance(text)` is the wrapper for "something the operator said/
    wrote this turn" — the channel through which the FlashBrain (or observer) feeds the agent without
    having to decide for itself where each sentence belongs.
"""

# Split into a package by the architecture audit 2026-08-23 (god-file: 1,486 lines, six responsibilities).
# This __init__ re-exports the COMPLETE surface the old module exposed — public API and the private names
# tests read — so no caller and no test changes: `from nucleo import memory_agent` behaves as before.
from __future__ import annotations

from nucleo.memory_agent.classify import classify  # noqa: F401
from nucleo.memory_agent.dossier import (  # noqa: F401
    _WEAK_SCORE, _agenda_lines, _background_slot_off_topic, _derive_concepts, _dossier_sync, _is_ambiguous,
    _llm_expand_query, _state_lines, compose_context)
from nucleo.memory_agent.external import remember, remember_external  # noqa: F401
from nucleo.memory_agent.gates import (  # noqa: F401
    _GARBLE_GUARD_SLOTS, _IDENTITY_SLOTS, _PATCH_TO_SLOT, _SLOT_TO_STATE_FIELD, _atom_is_nonfact,
    _atom_value_invalid, _established_slot_value, _is_ephemeral_directive, _is_vague_request,
    _plausibility_demote, _precision_reject_atom, _report_self_declared_change_ignored, _report_slot_guard,
    _same_entity_refinement, _slot_for_patch, _slot_supersede_guard, _writer_canon)
from nucleo.memory_agent.ingest import (  # noqa: F401
    _INGEST_LOCK, _sanitize_state_patch, _write_atom, ingest_utterance, maintain_state)
from nucleo.memory_agent.lang_marks import (  # noqa: F401 — the WHOLE bank: tests read it name by name
    _ASSISTANT_QUERY_RE,
    _COMMAND_RE,
    _COMMITMENT_RE,
    _CORRECTION_RE,
    _CORRECTION_TRAILING_NO_RE,
    _CORRECTION_YANO_RE,
    _DESIRE_RE,
    _EMPTY_MSG_RE,
    _FORGET_HARD_RE,
    _FORGET_RE,
    _FORGET_TRAILING_RE,
    _HEALTH_RE,
    _INCOMING_MSG_RE,
    _INJECTION_RE,
    _MOVE_VERBS,
    _NEGATION_PREFIX_RE,
    _OBSERVATION_RE,
    _PROFILE_CAR_RE,
    _PROFILE_DURABLE_RE,
    _PROFILE_GOAL_RE,
    _PROFILE_HW_RE,
    _PROFILE_LOC_RE,
    _PROFILE_NAME_RE,
    _PROFILE_PROJECT_RE,
    _PROFILE_TREATMENT_RE,
    _RELOCATION_RE,
    _REVERSAL_RE,
    _ROUTINE_RE,
    _SELF_REF_ELIDED_RE,
    _SELF_REF_RE,
    _TRIVIA_SKIP_RE,
    _UNFORGET_RE,
    _looks_like_injection,
    _talks_about_the_operator)
