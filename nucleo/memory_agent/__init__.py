"""nucleo/memory_agent.py — el agente de MEMORIA ★ del SlowBrain. V2-006 · T81 (mejora V2-013).

Pieza central de la deliberación. Tres caras:

  - `compose_context(prompt, budget)` — da **SOLO lo necesario** para un turno (no vuelca todo el store):
    estado siempre-inyectado (`memory.state()`, µs) + recall híbrido vec+FTS por RRF (`memory.query`), truncado
    al presupuesto de tokens. **Heurística barata el 90%** (el score rel+rec+imp+uso del retriever ya ordena);
    un **router LLM barato** entra SOLO si el recall es ambiguo/pobre (query corta o resultados flojos), para
    reformular/ampliar la consulta — best-effort, guardado (sin modelo → se salta). Modelo POR INVOCACIÓN.
  - `classify(text)` — decide DÓNDE guardar cada cosa (V2-013): perfil del operador (nombre, ubicación, trato,
    hardware, coche) → `state_patch` + traza durable `level='long', pinned=True`; deseos/preferencias →
    `level='long'`; trivia (saludos/comandos) → skip; resto → `level='mid'` (deliberación). Heurística regex es/en
    primero (µs, agnóstica del proveedor); LLM barato SOLO como reserva. Es el "corazón" que decide rápido: sin
    esto el `state` se queda vacío aunque el operador diga su nombre en un turno normal.
  - `remember(item)` — es el **ÚNICO** que escribe a `memory/` desde el SlowBrain. Si el caller no fija destino
    (`level`/`kind`/`state_patch`), auto-clasifica el `text` para no perder nada. Mantiene la tabla `state`
    (perfil del operador) junto al consolidador. `ingest_utterance(text)` es el envoltorio para "algo que dijo/
    escribió el operador este turno" — la vía por la que el FlashBrain (u observer) alimenta al agente sin
    tener que decidir él mismo dónde va cada frase.
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
