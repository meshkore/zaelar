"""memory/api — Public facade for central memory (V2-002 · T52).

The sole entry point for the rest of zaelar (FlashBrain, memory agent + headless workers, widgets, server).
It fits the system's HYBRID transport:

  - **async (queue)** — NON-urgent mutations: `write` · `reinforce` · `pin`/`unpin` · `link`. They enter through
    `memory/queue.py` (single writer → zero collisions); they do not block the hot path.
  - **direct (hot path · ms/µs)** — `query` (retriever) · `state` (fixed table) · `load_episode` (lazy).

Each mutation emits **`memory.updated`** through `bus/` so the UI or other subscribers can refresh. `query()`
composes the minimum context = state (ALWAYS) + relevant memories cut to the token budget, and queues **use
reinforcement** for what was used. `start()`/`stop()` run the queue consumer in the server loop; without
`start()` writes are applied inline (standalone/tests) — never lost.

⚠️ The writes and `query` live HERE, not in a submodule: tests patch `memory.api.write` / `memory.api.reinforce`
and expect `ingest_message` / `query` to call the patched one, which only holds while caller and callee share
this module's globals. The submodules hold what nothing patches from inside:
  anchors.py     clock, canonical slots, `as_of`, `[widget:]`/`[task:]` anchors, correction targets
  reads.py       by source / concept / slot prefix, `map`, the background-slot rule
  forgetting.py  forget / unforget and the reset's soft wipes
  episodes.py    episodic files, consolidation, the secret detector
  events.py      the `memory.updated` signal
"""
from .. import db as _db  # noqa: F401  (imports the package; get_db is lazy)
from .. import state as _state
from .. import viewer  # noqa: F401 — V2-808: the bounded reads behind the memory viewer
from .. import writer as _writer
from ..queue import get_queue
from ..action_map_store import (  # noqa: E402,F401 — V2-778 F1: moved, imported back under their names
    action_map_active, action_map_add, action_map_has_seed, action_map_hit, action_map_retarget_seed, action_map_seed_version, action_map_set_seed_version)
from .. import notices_store as notices  # noqa: E402,F401 — V2-796: the notice ledger, through the front door
from ..kv_store import (  # noqa: E402,F401 — V2-778 F1: moved, imported back under their names
    kv_del, kv_get, kv_keys, kv_set)
from .anchors import as_of, canon_slot, correction_targets, now, task_trace_ids, widget_trace_ids  # noqa: F401
from .episodes import (  # noqa: F401
    adopt_episode, consolidate, episode_inbox, list_episodes, load_episode, migrate_inbox, redact_secrets,
    register_episode, write_episode)
from .events import _emit
from .forgetting import clear_conversation, clear_slot_prefix, forget, unforget  # noqa: F401
from .reads import MAP_CAP, background_slot_off_topic, by_concepts, by_slot_prefix, map, recent_by_source  # noqa: F401
from .._prompt import (  # noqa: E402,F401 — the PRESENTATION (what is painted for a model) lives in `_prompt.py`
    compose_state, critical_facts, recent_short, recent_window, salient_long, seconds_since_last_conv)
from ..history import conversation, provenance  # noqa: E402,F401 — V2-802 T-06 / V2-803 T-01
# ── workflows (V2-594): `nucleo/workflows/` reaches the table only through the facade ──
from ..workflows_store import workflow_forget, workflow_hit, workflow_upsert, workflows_for  # noqa: E402,F401

# tokens ≈ characters / 4 (cheap approximation for truncating to the budget).
_CHARS_PER_TOKEN = 4
DEFAULT_BUDGET_TOKENS = 1200

# EXPLICIT facade contract (modularity audit 2026-07-17): this is the public surface; the rest of the repo must not
# import internals (memory.db/writer/queue/slots/…) outside tests.
__all__ = [
    "start", "stop", "redact_secrets",
    "write", "write_now", "ingest_message", "correction_targets", "widget_trace_ids", "task_trace_ids", "reinforce", "reinforce_ids_for", "pin", "unpin", "link",
    "forget", "unforget", "clear_conversation", "clear_slot_prefix",
    "state", "set_state", "compose_state",
    "kv_get", "kv_set",
    "query", "recent_short", "recent_window", "recent_by_source", "by_concepts",
    "seconds_since_last_conv",
    # V2-802 T-06 / V2-803 T-01: where a recalled row came from, and the conversation record as a source.
    "provenance", "conversation",
    "critical_facts", "salient_long", "map", "viewer",
    "load_episode", "register_episode", "write_episode", "list_episodes", "migrate_inbox",
    "episode_inbox", "adopt_episode",
    "consolidate", "DEFAULT_BUDGET_TOKENS",
]


# ── queue lifecycle ─────────────────────────────────────────────────────────────────────────────
async def start():
    """Start the queue's sole consumer in the current loop (server lifespan)."""
    await get_queue().start()


async def stop(drain: bool = True):
    await get_queue().stop(drain=drain)


# ── writes (async · queue) ────────────────────────────────────────────────────────────────────────────
def write(text: str, *, level: str = "short", kind: str = "event", importance: float | None = None,
          weight: float = 0.5, ttl_days: float | None = None, pinned: bool = False,
          slot: str | None = None, meta: dict | str | None = None,
          concepts: list[str] | None = None, supersedes: list[int] | None = None) -> None:
    """Queue a memory (fire-and-forget). The embedding is computed by the writer. Emits memory.updated.

    PILL (V2-013): `slot` = canonical key for the singular fact (`operator.name`…) → EXACT supersede/dedup in the
    writer; `meta` = free-form JSON wrapper (entity/source/said_at…) for the viewer and graph; `concepts` = 1–3
    lightweight labels (health/finance…) → the writer creates/links concept nodes in the graph (T126)."""
    get_queue().submit(
        "write", text, level=level, kind=kind, importance=importance,
        weight=weight, ttl_days=ttl_days, pinned=pinned, slot=slot, meta=meta, concepts=concepts,
        supersedes=supersedes,
    )
    _emit("memory.updated", {"op": "write", "kind": kind})


def write_now(text: str, **kwargs) -> int:
    """Direct SYNCHRONOUS write (for callers that need the id immediately: episodic storage, tests). Emits memory.updated."""
    mid = _writer.insert_memory(text, **kwargs)
    _emit("memory.updated", {"op": "write", "id": mid})
    return mid


def ingest_message(source: str, entity: str | None, text: str, *, group: str | None = None,
                   directed: bool = False, trust: str = "external", durable: bool = False,
                   importance: float | None = None, ttl_days: float | None = None,
                   concepts: list[str] | None = None, slot: str | None = None) -> None:
    """TYPED INGESTION of an inbound datum from an external SOURCE — the ONLY path through which every connector
    feeds memory (V2-013). All enter with their `source` (whatsapp/telegram/cluster/agent/email…) and `entity`
    (who), INDEXED in `meta` (→ `recent_by_source`) **and** in the TEXT (`[source] entity: body`) so FTS/recall find
    them. `trust`: 'operator' · 'external' (the owner's own connector) · 'untrusted' (a cluster peer). `directed` =
    addressed to zaelar (raises importance). `durable=True` → level `mid` with concepts; default `short`. `slot` →
    EXACT supersede: each ingest with the SAME slot OVERWRITES the last (an evolving synthesis per source/entity,
    e.g. `cluster:<cluster>:<peer>`). Best-effort."""
    body = (text or "").strip()
    if not body:
        return
    where = f" ({group})" if group else ""
    label = f"[{source}] {entity}{where}: {body}" if entity else f"[{source}]{where}: {body}"
    imp = importance if importance is not None else (0.6 if directed else 0.4)
    if concepts is None and durable:
        from memory.concepts import derive_concepts
        concepts = derive_concepts(body) or None
    write(label, level=("mid" if durable else "short"), kind="msg", importance=imp, ttl_days=ttl_days,
          slot=slot,
          meta={"source": source, "entity": entity, "trust": trust, "group": group, "directed": bool(directed)},
          concepts=concepts)


def reinforce(ids: list[int]) -> None:
    if not ids:
        return
    get_queue().submit("reinforce", list(ids))
    _emit("memory.updated", {"op": "reinforce", "ids": list(ids)})


def pin(mid: int) -> None:
    get_queue().submit("pin", int(mid))
    _emit("memory.updated", {"op": "pin", "id": int(mid)})


def unpin(mid: int) -> None:
    get_queue().submit("unpin", int(mid))
    _emit("memory.updated", {"op": "unpin", "id": int(mid)})


def link(from_id: int, to_id: int, type: str = "about", weight: float = 1.0) -> None:
    get_queue().submit("link", int(from_id), int(to_id), type, weight)
    _emit("memory.updated", {"op": "link"})


# ── state (direct · hot path) ─────────────────────────────────────────────────────────────────────────
def state() -> dict:
    """State (fixed table). Direct, µs, no search. ALWAYS in the prompt."""
    return _state.read()


def set_state(fields: dict) -> dict:
    """Updates the state (shallow merge). Emits memory.updated."""
    s = _state.patch(fields)
    _emit("memory.updated", {"op": "state"})
    return s


def note_widgets_used(ids) -> list:
    """Stamp widget(s) in the `recent_widgets` MRU (V2-078): the second narrowing layer for "which widget does this
    refer to?" (open > recently used > catalog). The canvas choke point calls it when a widget becomes OPEN. Emits
    memory.updated so the cached prompt can be rebuilt outside the turn (V2-011)."""
    merged = _state.push_recent_widgets(ids)
    _emit("memory.updated", {"op": "state"})
    return merged


# ── recall ────────────────────────────────────────────────────────────────────────────────────────────
def _pack(memories: list[dict], budget_tokens: int) -> list[dict]:
    """Truncate the list to the token budget (approximately chars/4)."""
    out, used = [], 0
    for m in memories:
        cost = max(1, len(m.get("text", "")) // _CHARS_PER_TOKEN)
        if used + cost > budget_tokens and out:
            break
        out.append(m)
        used += cost
    return out


def reinforce_ids_for(mems: list[dict]) -> list[int]:
    """Which pills of a package count as USED. One home for the policy.

    SELECTIVE reinforcement: the package carries concepts, graph neighbours and side results for context, and
    reinforcing all of them turns a housing question into «use» of the allergy. Without explicit feedback on what
    the LLM read, the honest signal is the first CONTENT memory (concept nodes are indexes, not lived memories).

    The TRIGGER moved out of `query()` (V2-311: reinforce on DELIVERY, not on composing) but the POLICY stays here:
    a caller reinforcing the whole `ids` (40 pills instead of 1) would erase selectivity with nothing failing."""
    return [m["id"] for m in mems if m.get("kind") != "concept"][:1]


def query(prompt: str, budget_tokens: int = DEFAULT_BUDGET_TOKENS, limit: int = 12,
          expand: bool = True, reinforce_used: bool = True, lexical_only: bool = False,
          lane: str = "own") -> dict:
    """Hot path: composes the minimum context = state (ALWAYS) + relevant memories within the budget.

    Returns {'state': dict, 'memories': list[dict], 'ids': list[int], 'reinforce_ids': list[int]}; queues the
    reinforcement of what was used.

    `lane` (V2-802 T-03, `retriever.LANE_*`) defaults to `own`: this is the OPERATOR-FACT recall (turn recall,
    worker dossier), and inbound messages are another question — they drowned it by volume. A caller that IS
    asking about messages passes `messages`, or `all` for own rows first and messages after them."""
    from .. import retriever as _retriever  # lazy import (avoids import-time cycles)

    st = _state.read()
    mems = _retriever.search(prompt, limit=limit, expand=expand, reinforce=False, lexical_only=lexical_only,
                             lane=lane)
    # THE CHOKEPOINT for the background-slot rule: every surface that shows pills to a model gets them from here,
    # so a FUTURE surface inherits it. A list of surfaces was tried and missed one each time it was extended.
    mems = [m for m in mems if not background_slot_off_topic(m.get("slot"), prompt)]
    if lane == "all":
        # Each lane packs in its own budget: one shared budget would let a long own lane push the messages out.
        mems = (_pack([m for m in mems if m.get("kind") != "msg"], budget_tokens)
                + _pack([m for m in mems if m.get("kind") == "msg"], budget_tokens))
    else:
        mems = _pack(mems, budget_tokens)
    ids = [m["id"] for m in mems]
    a_reforzar = reinforce_ids_for(mems)
    if reinforce_used and a_reforzar:
        reinforce(a_reforzar)  # async write (access resets the decay)
    return {"state": st, "memories": mems, "ids": ids, "reinforce_ids": a_reforzar}
