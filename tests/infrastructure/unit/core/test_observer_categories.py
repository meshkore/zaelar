"""
INVENTORY of viewer categories (2026-08-09, operator rule: “if we have N families, ALL events
must be associated with one of them”).

The viewer's top filter can only be reliable if every `kind` emitted by the system belongs to a known family.
When that is not the case, what the operator saw happens: `SESSION` and `BACKGROUND` rows slip through without
any chip governing them — they cannot be turned off, and worse, it is not known which component they belong to.

This test does NOT maintain a hard-coded list: it TRAVERSES the code, extracts the literal `kind` values from each
real call to `voice.observer.emit` (also following the local wrappers `def _emit(kind, ...)`, which are legion),
and requires all of them to be in `_CAT`. Adding a new capability with its own kind and forgetting to classify it
fails here, rather than in front of the operator three weeks later.

`tests/` is intentionally ignored: the tests invent synthetic kinds (“boom”, “oops”) that are not part of the product.
"""
from __future__ import annotations

import ast
from pathlib import Path

from voice import observer

ENGINE = Path(__file__).resolve().parents[4]
_SKIP = (".venv", "node_modules", "__pycache__", "TMP")

# Families that the viewer renders as chips (frontend/app/components/DebugPanel.js::CATS). The backend cannot
# invent a family that the UI does not offer: it would be an event unreachable from the filter.
CATS = {"flash", "worker", "memory", "widget", "system", "pulse"}


def _emitted_kinds() -> dict[str, set[str]]:
    """{kind: {files}} for each `emit("<kind>", …)` in the PRODUCT."""
    found: dict[str, set[str]] = {}
    for f in ENGINE.rglob("*.py"):
        rel = f.relative_to(ENGINE).as_posix()
        if rel.startswith("tests/") or any(p in rel for p in _SKIP):
            continue
        try:
            src = f.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except Exception:
            continue
        if "observer" not in src:
            continue

        # Names that are the observer emit in THIS file: the direct import (with or without an alias) and the
        # local wrappers whose FIRST parameter is called `kind` (those called `label` receive something else
        # — e.g. widgets/navegador/owner.py — and including them would produce false kinds).
        names: set[str] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module and "observer" in n.module:
                names.update(a.asname or a.name for a in n.names if a.name == "emit")
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in ("emit", "_emit"):
                args = [a.arg for a in n.args.args if a.arg != "self"]
                if args and args[0] == "kind":
                    names.add(n.name)

        for n in ast.walk(tree):
            if not isinstance(n, ast.Call) or not n.args:
                continue
            fn = n.func
            direct = isinstance(fn, ast.Name) and fn.id in names
            dotted = (isinstance(fn, ast.Attribute) and fn.attr == "emit"
                      and isinstance(fn.value, ast.Name) and "observer" in fn.value.id.lower())
            if (direct or dotted) and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                found.setdefault(n.args[0].value, set()).add(rel)
    return found


def test_the_scan_finds_the_real_kinds():
    """Guard for the guard itself: if the scan stopped finding anything, the test below would pass vacuously."""
    kinds = _emitted_kinds()
    assert {"brain", "widget", "memory", "task"} <= set(kinds), f"escaneo sospechoso: {sorted(kinds)}"


def test_every_emitted_kind_belongs_to_a_family():
    unmapped = {k: sorted(v) for k, v in _emitted_kinds().items() if k not in observer._CAT}
    assert not unmapped, (
        "kinds sin familia en voice/observer.py::_CAT — el operador no puede filtrarlos:\n"
        + "\n".join(f"  {k}  ← {', '.join(v)}" for k, v in sorted(unmapped.items()))
    )


def test_families_exist_in_the_viewer():
    bad = {k: c for k, c in observer._CAT.items() if c not in CATS}
    assert not bad, f"familias que el visor no pinta como chip (evento inalcanzable desde el filtro): {bad}"
