"""Every door that starts work or opens an errand's surface goes through THE door (V2-844 F2).

V2-784 made `flow_of` «the one door» from a request to its flow and gave it ONE caller; nothing failed when the next
door that started work went around it, and the class stayed open for two weeks — six doors routing «is this sentence
about an existing errand?», each its own way, at its own moment. This is the gate V2-784 lacked.

The work-starting calls are few and named: `escalate_to_slowbrain` (the portal, which routes every turn's request
through `flow_door.at_the_portal`), `errand.born` (an errand born in the turn), `fast_pass` (the turn's first rung),
and `_sheet_open` (an errand's sheet). Every function in product code that calls or hands on one of them is DECLARED
here with HOW it reaches the route — and a new one fails until somebody says how. «Callers of the door = doors that
create work», counted.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PRODUCT = ("nucleo", "voice", "widgets", "server", "connectors", "search", "memory", "rules", "daemon", "bus", "library")
DOORS = ("escalate_to_slowbrain", "born", "fast_pass", "_sheet_open")
#: Where `born` comes from: the name is common (watchers, traces), the door is this one.
BORN_HOME = ("nucleo.acts.errand", "nucleo.acts.errand_birth")
#: The names that ARE the route (a function that names one of them asks the door).
ROUTE = {"at_the_portal", "for_request", "route", "settled", "join"}

PORTAL = "the portal routes it (`flow_door.at_the_portal`)"
CONTINUES = "continues an errand that exists (its uid or record): the route already took it, never routed twice"
DECLARED: dict[tuple[str, str], str] = {
    ("nucleo/acts/search_listing.py", "listings"): "ROUTED: `flow_of.join` before its pass",
    ("nucleo/acts/search_listing.py", "_born"): "only `listings` calls it, after `join` said new",
    ("nucleo/acts/search_sheet.py", "fast_pass"): "the first rung a routed door started; births only when handed no box",
    ("nucleo/acts/search_sheet.py", "_hand_on"): "the first rung's hand-on, under the errand it was born as",
    ("nucleo/acts/tools.py", "<module>"): "the model's call is RECORDED into the turn's request; `close_the_turn` launches it",
    ("nucleo/turn/pipeline_errands.py", "launch_the_errands"): "ROUTED: `flow_of.settled` before it launches; " + PORTAL,
    ("nucleo/flash/compose_rung.py", "_to_the_worker"): PORTAL,
    ("nucleo/flash/cluster.py", "_on_tool_call"): PORTAL + " (a peer's turn has no trace of his: the dispatcher decides)",
    ("nucleo/cli/worker_api_exec.py", "_not_mine"): "the worker handed words back: an errand of their own, never refolded",
    ("nucleo/cli/worker_api_exec.py", "_spawn_child"): "a worker's own sub-errand, under its parent",
    ("nucleo/cli/worker_api_exec.py", "_own_sheet"): CONTINUES,
    ("nucleo/cli/worker_api_resume.py", "resume_soon"): CONTINUES + " (his answer resumes the session that asked, V2-851)",
    ("nucleo/circuit/__init__.py", "_close"): CONTINUES,
    ("nucleo/circuit/reopen.py", "on_criteria"): CONTINUES,
    ("nucleo/dispatch/confirm.py", "resolve_confirm"): CONTINUES + " (his yes relaunches the parked errand)",
    ("nucleo/dispatch/control.py", "_later"): CONTINUES + " (the web resume of an incomplete errand)",
    ("nucleo/dispatch/listener.py", "run_listener"): CONTINUES + " (the errand the portal opened)",
    ("nucleo/flash/resume_turn.py", "resume"): CONTINUES,
    ("nucleo/pulse/rehydrate.py", "_later"): CONTINUES,
    ("nucleo/request/append.py", "_rerun"): "the dispatcher's backstop re-running a delivered pass in its box",
    ("nucleo/sheets.py", "sheet_for_delivery"): CONTINUES,
    ("nucleo/workers/quota_wait.py", "fire"): CONTINUES,
    ("nucleo/workers/rate_retry.py", "_go"): CONTINUES,
    ("nucleo/workers/relay.py", "relay_out_of_fuel"): CONTINUES,
    ("nucleo/workers/relay.py", "restart_stalled"): CONTINUES,
    ("nucleo/events/stream.py", "_launch"): CONTINUES + " (the event reached it through `flow_of.route(event=…)`, a subscribed rule's "
                                            "stream, V2-851 F4 branch c; the stream's own recurring row carries it)",
}


def _aliases(tree) -> tuple[set, set]:
    """Names bound to `born` and names bound to its module, anywhere in the file."""
    names, mods = set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module in BORN_HOME:
            names |= {a.asname or a.name for a in n.names if a.name == "born"}
        if isinstance(n, ast.ImportFrom) and n.module == "nucleo.acts":
            mods |= {a.asname or a.name for a in n.names if f"nucleo.acts.{a.name}" in BORN_HOME}
        if isinstance(n, ast.Import):
            mods |= {a.asname for a in n.names if a.name in BORN_HOME and a.asname}
    return names, mods


def callers() -> dict[tuple[str, str], set]:
    out: dict[tuple[str, str], set] = {}
    for top in PRODUCT:
        for p in sorted((ROOT / top).rglob("*.py")):
            if "_user" in p.parts or "__pycache__" in p.parts:
                continue
            tree = ast.parse(p.read_text(encoding="utf-8"))
            born_names, born_mods = _aliases(tree)
            rel = str(p.relative_to(ROOT))

            def walk(node, fn):
                for ch in ast.iter_child_nodes(node):
                    if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        walk(ch, ch.name)
                        continue
                    name = ""
                    if isinstance(ch, ast.Attribute) and ch.attr in DOORS:
                        name = ch.attr if ch.attr != "born" or (isinstance(ch.value, ast.Name)
                                                                 and ch.value.id in born_mods) else ""
                    elif isinstance(ch, ast.Name) and ch.id in DOORS:
                        name = ch.id if ch.id != "born" or ch.id in born_names else ""
                    if name:
                        out.setdefault((rel, fn), set()).add(name)
                    walk(ch, fn)
            walk(tree, "<module>")
    return out


def _function(path: str, fn: str):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    return next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn)


ROUTE_HOME = ("nucleo.turn.flow_of", "nucleo.turn.flow_door")


def _names_the_route(fn_node) -> bool:
    """Does this function call the route — `flow_of`/`flow_door` by the names it imported them under?"""
    mods, funcs = set(), set()
    for n in ast.walk(fn_node):
        if isinstance(n, ast.ImportFrom) and n.module == "nucleo.turn":
            mods |= {a.asname or a.name for a in n.names if f"nucleo.turn.{a.name}" in ROUTE_HOME}
        if isinstance(n, ast.ImportFrom) and n.module in ROUTE_HOME:
            funcs |= {a.asname or a.name for a in n.names if a.name in ROUTE}
    return any((isinstance(n, ast.Attribute) and n.attr in ROUTE and isinstance(n.value, ast.Name)
                and n.value.id in mods) or (isinstance(n, ast.Name) and n.id in funcs) for n in ast.walk(fn_node))


def test_every_door_that_starts_work_is_declared_with_how_it_reaches_the_route():
    found = set(callers())
    new, gone = sorted(found - set(DECLARED)), sorted(set(DECLARED) - found)
    assert not new, ("a door that starts work or opens an errand's sheet is not routed by `flow_of` — route it (the "
                     "portal, `join`, `settled`) or say here how it continues an errand that exists:\n  "
                     + "\n  ".join(f"{p}::{f}" for p, f in new))
    assert not gone, "a declared door is gone — take it off the list:\n  " + "\n  ".join(f"{p}::{f}" for p, f in gone)


def test_the_portal_and_the_routed_doors_really_ask_the_route():
    for (path, fn), how in DECLARED.items():
        if how.startswith(("THE portal", "ROUTED")):
            assert _names_the_route(_function(path, fn)), f"{path}::{fn} is declared routed and never asks the route"


def test_the_portal_asks_the_route_before_it_opens_anything():
    """Every caller declared as reaching the portal leans on THIS: the portal itself routes a turn's request."""
    fn = _function("nucleo/acts/errand.py", "escalate_to_slowbrain")
    assert _names_the_route(fn), "the escalation portal no longer routes: every door declared «the portal routes it» is open"
