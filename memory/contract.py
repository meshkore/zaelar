"""memory/contract.py — memory's BOUNDARY, written as code (V2-114 F0).

Memory has to be able to evolve (and even be reimplemented) without the agent noticing. That requires knowing,
without ambiguity, **what the agent asks of a memory**. This module declares it: it is executable documentation
of the surface a replacement must cover, plus the list of who is allowed to bypass the facade.

Measured 2026-08-18 across 48 production files: **84 of ~108 imports already go through `memory.api`**. The
boundary does not need inventing, it needs closing — and above all it needs to stay closed, which is what the
ratchet in `tests/memory/unit/test_memory_boundary.py` is for.

**What this is NOT.** It is not an indirection layer: `memory/api.py` is still the implementation and nobody has
to come through here to call it. It is a `Protocol` (structural typing), so `memory.api` satisfies it without
inheriting anything and at zero runtime cost. It exists so that (a) a replacement knows what to implement, (b) a
remote client (V2-114 F3) has an exact target, and (c) the ratchet has something to compare against.

**What is deliberately OUTSIDE the contract**, and why:
  - `memory.vault*` — the secret vault is a different concern (crypto, passkeys, out-of-band reveal). It shares
    the SQLite file, not memory semantics. A memory replacement should not have to reimplement it.
  - `memory.rem` / `memory.consolidator` / `memory.reembed` — the SLEEP axis. Orchestrated by `nucleo/loop.py`,
    not by the turn. It is maintenance of the implementation, not something the agent asks for.
  - `memory.embeddings` / `memory.retriever` / `memory.writer` / `memory.db` — internals. If a replacement does
    not use sqlite-vec, none of this means anything to it.
  - `memory.concepts.derive_concepts` — a pure stdlib function with no DB; it is shared vocabulary, not state.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MemoryContract(Protocol):
    """What the agent needs from a memory. Grouped by SPEED, which is the axis that governs the design
    (V2-011/V2-013): the voice turn can only afford the first two families."""

    # ── µs READS · ALWAYS in the prompt, never heavy I/O ──────────────────────────────────────────────────
    def state(self) -> dict:
        """Fixed state table (identity, location, goal, open widgets…). Direct read."""
        ...

    def compose_state(self) -> tuple[str, str, dict]:
        """The SHARED STATE block, already composed: `(block, op, stats)`. The caller caches it outside the
        turn; this function may NOT call an LLM or the retriever."""
        ...

    def recent_short(self, *args: Any, **kwargs: Any) -> list[dict]:
        """Short-term working set, complete and over-inclusive. µs."""
        ...

    def recent_window(self, *args: Any, **kwargs: Any) -> list[dict]:
        """Recent conversational window, verbatim, for "what were we talking about"."""
        ...

    # ── ms READS · ON DEMAND, off the event loop, ZERO LLM ────────────────────────────────────────────────
    def query(self, *args: Any, **kwargs: Any) -> list[dict]:
        """Semantic recall of long-term memory. The only family that tolerates waiting — and even so, no LLM."""
        ...

    def recent_by_source(self, *args: Any, **kwargs: Any) -> list[dict]:
        """Read by indexed SOURCE (whatsapp/telegram/cluster/email…), without the retriever."""
        ...

    def by_concepts(self, *args: Any, **kwargs: Any) -> list[dict]:
        """Read by concept, for aggregation by category."""
        ...

    def as_of(self, *args: Any, **kwargs: Any) -> Any:
        """Reconstruction at a past date: "what did we believe was true on day X?" (bi-temporal, schema v5)."""
        ...

    def critical_facts(self, *args: Any, **kwargs: Any) -> list[dict]:
        """Facts that must ALWAYS surface (allergies, medication). Outside the normal cap."""
        ...

    def salient_long(self, *args: Any, **kwargs: Any) -> list[dict]:
        """Salient durable profile for the state block."""
        ...

    # ── WRITES · may be SLOW, never on the hot path ───────────────────────────────────────────────────────
    def write(self, *args: Any, **kwargs: Any) -> Any:
        """Queues a write (fire-and-forget). Returns None: whoever needs the id uses `write_now`."""
        ...

    def write_now(self, *args: Any, **kwargs: Any) -> int:
        """SYNCHRONOUS write that returns the id. For episodic memory and tests."""
        ...

    def ingest_message(self, *args: Any, **kwargs: Any) -> None:
        """TYPED path for an incoming datum from a SOURCE, carrying `trust` (operator/external/untrusted).
        `untrusted` implies QUARANTINE: never in the passive prompt."""
        ...

    def set_state(self, *args: Any, **kwargs: Any) -> Any:
        """Patch of the fixed state."""
        ...

    def forget(self, *args: Any, **kwargs: Any) -> int:
        """Forgetting at the operator's request. `hard=True` really deletes (right to be forgotten)."""
        ...

    def unforget(self, *args: Any, **kwargs: Any) -> int:
        """The operator takes back a forget."""
        ...

    # ── AUXILIARY STATE · durable key-value that must NOT travel in the prompt ────────────────────────────
    def kv_get(self, *args: Any, **kwargs: Any) -> Any: ...
    def kv_set(self, *args: Any, **kwargs: Any) -> Any: ...
    def kv_keys(self, *args: Any, **kwargs: Any) -> Any: ...
    def kv_del(self, *args: Any, **kwargs: Any) -> Any: ...


# ── Who may bypass the facade, and why ───────────────────────────────────────────────────────────────────
# The ratchet (`tests/memory/unit/test_memory_boundary.py`) FAILS if an import of `memory` internals appears
# outside this list. Adding an entry is a conscious decision justified here; the goal is that declared debt can
# only go DOWN, same pattern as `test_roadmap_closure.py`.
#
# Measured 2026-08-18: **24 leaks in production**, across 13 submodules. Pleasant surprise from the measurement:
# `memory.db`, `memory.retriever`, `memory.queue`, `memory.consolidator`, `memory.episodic`, `memory.graph*` and
# `memory.clock` are **NOT imported from production** — their 78 occurrences were all in `tests/`, where touching
# internals is legitimate. The real boundary was considerably more closed than it looked.
BLESSED_INTERNAL_IMPORTS: dict[str, str] = {
    # ── separate concern: crypto/passkeys/out-of-band reveal. Shares the SQLite file, not the semantics ──
    "memory.vault": "secret vault — its own subsystem (V2-060), not memory",
    "memory.vault_api": "the vault's FastAPI router",
    # ── server wiring: a router has to be imported to be mounted ──
    # ── the SLEEP axis: orchestrated by nucleo/loop.py (~1 Hz), never by the turn ──
    "memory.rem": "daily REM phase, orchestrated by the loop",
    "memory.reembed": "vector-space migration, verified at boot",
    # ── shared vocabulary/gates: pure stdlib, no DB ──
    "memory.concepts": "derive_concepts — pure function, no state",
    "memory.slots": "canonical slot registry — the source the distiller's prompt is GENERATED from",
    "memory.secrets": "fail-closed secret detection, runs BEFORE writing",
    # ── REAL candidates for closing by re-exporting from the facade (declared debt, not a forever blessing) ──
    "memory.state": "fixed state table — CLOSEABLE: re-export from the facade",
    "memory.journal": "task journal — CLOSEABLE: re-export from the facade",
    # ── internals with a legitimate, bounded caller ──
    "memory.writer": "the single writer — touched by memory_agent, which IS the writer",
    "memory.rerank": "reranker state for the config panel",
    "memory.embeddings": "backend state/dimension for the config panel and boot",
}
