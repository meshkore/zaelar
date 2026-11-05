"""V2-851 §3b — `circuit.settle` is the ONLY writer of a task's ending (`done | failed | cancelled`), for every row.

Measured in F0 on real sessions: 12 of ~135 rows (9 %) had more than one writer of their final state, and one row
read `done` with an outcome saying it could not finish. Six functions wrote an ending of their own (`ledger.closed`,
`first_rung_delivered`, `reconciled`, `interrupted`, the list runner twice) and nothing recorded which one did.

The door, read off the product's own source: every call to the task store's two writers (`task_patch`, `task_put`)
outside `settle` may only write a LIVE state, as a literal (or a module constant, or a choice between literals). A
state the reader cannot see — a variable, a `**kwargs` with no explicit `state` — counts as an ending: it could be one.
Raw SQL that updates `tasks` outside the store itself counts too.
"""
from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
ENDINGS = {"done", "failed", "cancelled"}
WRITERS = ("task_patch", "task_put")
#: The one writer: `settle` and the helper only it calls, in the circuit package.
SETTLE = {("nucleo/circuit/__init__.py", "settle"), ("nucleo/circuit/__init__.py", "_settle_row")}
STORE = "memory/tasks_store.py"
_SKIP = {".venv", "tests", "node_modules", "__pycache__", ".git", ".meshkore", ".claude", "TMP"}
UNKNOWN = "?"


def _consts(tree: ast.AST) -> dict[str, str]:
    """Module-level `NAME = "literal"` — what a `state=NAME` resolves to."""
    out = {}
    for n in getattr(tree, "body", []):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
            out.update({t.id: n.value.value for t in n.targets if isinstance(t, ast.Name)})
    return out


def _values(node: ast.AST, consts: dict[str, str]) -> set[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        return _values(node.body, consts) | _values(node.orelse, consts)
    if isinstance(node, ast.Name) and node.id in consts:
        return {consts[node.id]}
    return {UNKNOWN}


def _written_state(call: ast.Call, consts: dict[str, str]) -> set[str] | None:
    """The states a writer call may write; None when it writes no state at all."""
    name = call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", "")
    if name == "task_patch":
        kw = {k.arg: k.value for k in call.keywords}
        if "state" in kw:
            return _values(kw["state"], consts)
        return {UNKNOWN} if None in kw else None              # `**fields` may carry a state the reader cannot see
    if name == "task_put" and call.args:
        row = call.args[0]
        if not isinstance(row, ast.Dict):
            return {UNKNOWN}
        for k, v in zip(row.keys, row.values):
            if k is None:
                return {UNKNOWN}
            if isinstance(k, ast.Constant) and k.value == "state":
                return _values(v, consts)
        return None
    return None


def ending_writers(src: str, rel: str) -> list[str]:
    """`file:line in function` for every write that may set an ending outside `settle`."""
    tree = ast.parse(src)
    consts = _consts(tree)
    out = []

    def walk(node: ast.AST, fn: str) -> None:
        for child in ast.iter_child_nodes(node):
            here = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
            if isinstance(child, ast.Call) and (rel, fn) not in SETTLE:
                name = child.func.attr if isinstance(child.func, ast.Attribute) else getattr(child.func, "id", "")
                states = _written_state(child, consts) if name in WRITERS else None
                if states and (states & ENDINGS or UNKNOWN in states):
                    out.append(f"{rel}:{child.lineno} in {fn or '<module>'} writes {sorted(states)}")
            if (rel != STORE and isinstance(child, ast.Constant) and isinstance(child.value, str)
                    and "UPDATE TASKS SET" in child.value.upper()):
                out.append(f"{rel}:{child.lineno} raw SQL updates tasks")
            walk(child, here)
    walk(tree, "")
    return out


def _product_files():
    for p in ENGINE.rglob("*.py"):
        rel = p.relative_to(ENGINE).as_posix()
        if not any(part in _SKIP for part in rel.split("/")):
            yield rel, p


def test_the_reader_sees_every_shape_of_an_ending_write():
    """Guard for the guard: a scanner that stopped seeing writes would pass vacuously."""
    src = '''
LIVE = "running"
def a(ts, uid, s, kw):
    ts.task_patch(uid, state="done")
    ts.task_patch(uid, state=s)
    ts.task_patch(uid, **kw)
    ts.task_put({"id": uid, "state": "failed" if s else "running"})
    ts.task_put(kw)
    db.execute("UPDATE tasks SET state='done'")
def b(ts, uid):
    ts.task_patch(uid, state=LIVE, title="x")
    ts.task_patch(uid, state="waiting" if uid else "running", **{"x": 1})
    ts.task_put({"id": uid, "state": "pending"})
    ts.task_patch(uid, title="x")
'''
    found = ending_writers(src, "nucleo/x.py")
    assert len(found) == 6 and all(" in a " in f or "raw SQL" in f for f in found), found


def test_settle_is_seen_as_the_writer_it_is():
    """…and it does see `settle` itself writing: the exemption is by name, not because the reader is blind."""
    src = (ENGINE / "nucleo/circuit/__init__.py").read_text(encoding="utf-8")
    assert any("_settle_row" in f for f in ending_writers(src, "nucleo/circuit/__x.py")), \
        "the settle body no longer writes through the store — this door would prove nothing"


def test_no_ending_is_written_outside_settle():
    found = []
    for rel, p in _product_files():
        src = p.read_text(encoding="utf-8")
        if not any(w in src for w in WRITERS) and "UPDATE TASKS" not in src.upper():
            continue
        found += ending_writers(src, rel)
    assert not found, ("a task's ending written outside `circuit.settle` — call `settle(row=…, state=…)`:\n  "
                       + "\n  ".join(found))
