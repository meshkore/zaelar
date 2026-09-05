"""The two ratchets that make the memory refactor SAFE — put in place BEFORE anything moves (audit 2026-08-23).

`test_memory_boundary.py` guards one direction: the rest of the repo must come in through the facade. This file
guards the other two ways the structure can rot while every functional test stays green:

  1. **memory/ importing nucleo/.** The memory package should be autonomous ("memory does not import brains" —
     the rule `rem.py` already lives by, taking its LLM hooks by injection). Measured 2026-08-23: SIX inverse
     imports; F3 took it to FOUR by moving `server_api.py` out (it was transport, not memory — see below).
     Then to THREE by injecting the workers-ledger cleanup, and all three left are BLESSED with their
     reason written in the row. A closed
     inventory, ratcheted: a new inverse import breaks with a name, and the list only shrinks.

     The bar for blessing one is deliberately high and stated per row: `db.py -> workspace` is a filesystem
     path with no reasoning near it, and the two in `rerank.py` buy a BILLING guarantee that a
     registered-callback design would quietly reopen. Purity that costs unbilled money is a bad trade, and
     saying so beats leaving a row that reads like unfinished work.

  2. **The facade's surface drifting during the split.** The refactor's contract is "move without changing
     semantics — zero caller changes". That is only checkable if the surface is frozen first: `__all__` and the
     de-facto public names are snapshotted here, so a function silently lost (or gained) in the move breaks
     loudly instead of breaking some caller three weeks later.

Same pattern as `test_observer_categories.py` and `test_roadmap_closure.py`: CLOSED inventory, declared debt
can only go DOWN. If one of these fails while you are adding code, the question is not "how do I silence it"
but "does this belong on the other side of the boundary?".
"""
from __future__ import annotations

import pathlib
import re

from memory import api as memapi

REPO = pathlib.Path(__file__).resolve().parents[3]

# ── ratchet 1 · memory/ → nucleo/ ───────────────────────────────────────────────────────────────────────────

#: Every inverse import that exists today, with why it is here and how it leaves. The refactor's F3 empties
#: this down to the single blessed one. Adding a row needs the reason written; removing rows is the goal.
INVERSE_IMPORTS_DEBT: dict[tuple[str, str], str] = {
    ("memory/db.py", "nucleo.workspace"):
        "infra, not a brain: resolves the workspace root (a filesystem path, no reasoning anywhere near it). "
        "BLESSED permanently on 2026-08-23 — moving it would mean a shared-infra package for one function.",
    ("memory/rerank.py", "nucleo.llm_egress"):
        "remote rerank egress, deferred import inside the opt-in remote path. STAYS: see energy_meter below — "
        "the two travel together and splitting them would route egress without metering it.",
    ("memory/rerank.py", "nucleo.energy_meter"):
        "meters the remote rerank call. STAYS, deliberately (2026-08-23): its own comment says it is metered "
        "while DORMANT so that turning the remote reranker on is never free by accident. A registered-callback "
        "design reopens exactly that hole for any process that forgets to register — real money going unbilled, "
        "silently, in exchange for layer purity. Deferred import inside an opt-in branch is the cheaper trade.",
    ("memory/embeddings.py", "nucleo.energy_meter"):
        "meters the CLOUD embedding call (V2-501). Same trade as rerank above, and the argument is stronger "
        "here: the reranker is dormant, this runs on every insert AND every query. Deferred import inside the "
        "cloud branch, right after a successful response; the local backends never reach it.",
}

_FROM_DOTTED_RE = re.compile(r"^[ \t]*from[ \t]+nucleo\.([a-z_]+)")           # from nucleo.workers import ledger
_FROM_PLAIN_RE = re.compile(r"^[ \t]*from[ \t]+nucleo[ \t]+import[ \t]+(.+)")  # from nucleo import workspace as _w
_IMPORT_RE = re.compile(r"^[ \t]*import[ \t]+nucleo\.([a-z_]+)")               # import nucleo.workspace


def _inverse_imports() -> set[tuple[str, str]]:
    """`(memory/<file>, nucleo.<module>)` for every import of nucleo inside memory/, at the granularity the
    debt table speaks: the first module level under `nucleo`."""
    found: set[tuple[str, str]] = set()
    for p in (REPO / "memory").glob("*.py"):
        for line in p.read_text(encoding="utf-8").splitlines():
            m = _FROM_DOTTED_RE.match(line) or _IMPORT_RE.match(line)
            if m:
                found.add((f"memory/{p.name}", f"nucleo.{m.group(1)}"))
                continue
            m = _FROM_PLAIN_RE.match(line)
            if m:  # each imported name IS a module here
                for n in m.group(1).split(","):
                    n = n.split(" as ")[0].split("#")[0].strip()
                    if n:
                        found.add((f"memory/{p.name}", f"nucleo.{n}"))
    return found


def test_no_NEW_inverse_import_appears():
    """A new memory→nucleo import must be a deliberate, written-down decision — never drift."""
    new = _inverse_imports() - set(INVERSE_IMPORTS_DEBT)
    assert not new, (
        f"memory/ grew new imports of nucleo/: {sorted(new)}. Memory must not import brains — take the "
        f"dependency by injection (see rem.py), or write the debt down here WITH its reason and exit plan.")


def test_the_debt_list_matches_reality_so_it_only_shrinks():
    """A row whose import no longer exists must be DELETED — a stale row is slack a future leak hides in."""
    stale = set(INVERSE_IMPORTS_DEBT) - _inverse_imports()
    assert not stale, (
        f"these debt rows no longer exist in the code — delete them so the ratchet keeps its grip: {sorted(stale)}")


# ── ratchet 2 · the facade's surface, frozen for the move ───────────────────────────────────────────────────

#: `memory.api.__all__` exactly as it stands the day the refactor starts. F2 may CHANGE this deliberately
#: (editing both the code and this snapshot in the same commit); it must never change as a side effect.
DECLARED_SURFACE = {
    "start", "stop",
    "write", "write_now", "ingest_message", "correction_targets", "reinforce", "reinforce_ids_for", "pin", "unpin", "link",
    # 2026-09-04 (V2-577, a widget event reaches the pills it outdates): the deterministic door that resolves
    # the `[widget:<id>]` text anchor, so widget lifecycle writes can supersede the widget's prior story.
    "widget_trace_ids",
    "forget", "unforget",
    # 2026-08-31 (V2-528, stopping means discarding): the reset invalidates the conversational buffer ("the chat
    # is erased" includes the SEEDING of the window) and the `task.*` slots (the "we are doing X" pills). Soft
    # (`valid=0`), forget doctrine: excluded from all reads, retained for auditing.
    "clear_conversation", "clear_slot_prefix",
    "state", "set_state", "compose_state", "add_user_rule", "remove_user_rule",
    "kv_get", "kv_set",
    "query", "recent_short", "recent_window", "recent_by_source", "by_concepts",
    "seconds_since_last_conv",
    "critical_facts", "salient_long", "map",
    "load_episode", "register_episode", "write_episode", "list_episodes", "migrate_inbox",
    "consolidate", "DEFAULT_BUDGET_TOKENS",
}

#: Public in practice but NOT declared in `__all__` — real drift, measured 2026-08-23 and frozen as-is on
#: purpose: resolving it (declare or underscore) is F2's job, with callers checked. `by_slot_prefix` for one
#: already has an external consumer (the use-cases harness, V2-260).
UNDECLARED_PUBLIC = {
    "now", "canon_slot", "as_of", "kv_keys", "kv_del", "note_widgets_used", "background_slot_off_topic",
    "by_slot_prefix",
    # The action-map storage family (V2-539/V2-545): `memory` owns the table, `nucleo/actionmap/store.py` is the
    # single caller. Inventoried rather than declared for the same reason as the rest of this set — the ratchet
    # was already red on the four that shipped with V2-539, so promoting them into the frozen surface is F2's
    # call with its callers checked, not a side effect of adding two more.
    "action_map_active", "action_map_add", "action_map_has_seed", "action_map_hit",
    "action_map_seed_version", "action_map_set_seed_version", "action_map_retarget_seed",
    # V2-594 · the workflow table's four (`nucleo/workflows/` is the only caller, through the facade like
    # everything else). Inventoried and not declared, for the same reason as the action-map set above: joining
    # the frozen surface is a decision with its callers checked, not a side effect of adding a table.
    "workflows_for", "workflow_upsert", "workflow_hit", "workflow_forget",
}


def _public_names() -> set[str]:
    return {n for n in dir(memapi)
            if not n.startswith("_") and (callable(getattr(memapi, n)) or n == "DEFAULT_BUDGET_TOKENS")
            and getattr(getattr(memapi, n), "__module__", "memory.api") == "memory.api"}


def test_declared_surface_is_frozen():
    assert set(memapi.__all__) == DECLARED_SURFACE, (
        f"memory.api.__all__ changed. If deliberate, update DECLARED_SURFACE in the same commit; if not, the "
        f"move just altered the facade. Diff: +{set(memapi.__all__) - DECLARED_SURFACE} "
        f"-{DECLARED_SURFACE - set(memapi.__all__)}")


def test_every_declared_name_exists_and_nothing_public_is_unaccounted():
    missing = DECLARED_SURFACE - set(dir(memapi))
    assert not missing, f"declared in __all__ but gone from the module: {sorted(missing)}"
    unaccounted = _public_names() - DECLARED_SURFACE - UNDECLARED_PUBLIC
    assert not unaccounted, (
        f"new public names on the facade, neither declared nor inventoried: {sorted(unaccounted)}. Either add "
        f"to __all__ (and DECLARED_SURFACE) or underscore them — a surface that grows silently cannot be frozen.")
