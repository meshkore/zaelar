#!/usr/bin/env python3
"""The engine's import graph, one command away (refactor2710-00 T-01).

A measuring instrument of the tests, not product code — it lives under `tests/`. Per product module: lines, fan-in
(product importers), the importers themselves, how many times its dotted name appears in `tests/`, and whether its
header carries a dated incident. Every later refactor2710 section is
measured against a run of this script, so it reads the tree only — no imports, no side effects.

    ./.venv/bin/python -m tests.infrastructure.import_graph out.json            # full rows
    ./.venv/bin/python -m tests.infrastructure.import_graph out.json --summary  # + package totals and orphans on stdout
"""

from __future__ import annotations

import argparse
import ast
import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ("nucleo", "voice", "server", "widgets", "memory", "search", "rules", "bus", "observability",
            "connectors", "library", "config")
SKIP_PARTS = {".venv", "__pycache__", "_user", "_data"}
DOTTED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
INCIDENT = re.compile(r"\(?\b20(25|26)-\d\d-\d\d")


def product_modules() -> dict[str, tuple[str, str]]:
    mods = {}
    for pkg in PACKAGES:
        for p in sorted((ROOT / pkg).rglob("*.py")):
            rel = p.relative_to(ROOT)
            if SKIP_PARTS & set(rel.parts):
                continue
            name = rel.with_suffix("").as_posix().replace("/", ".")
            if name.endswith(".__init__"):
                name = name[: -len(".__init__")]
            try:
                mods[name] = (rel.as_posix(), p.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
    return mods


def imports_of(src: str, name: str, is_package: bool) -> set[str]:
    """Absolute names this module imports. A relative `from . import x` / `from ..y import z` is resolved against
    the module's own package — skipping it marks every module reached only that way as an orphan."""
    out: set[str] = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    here = name.split(".") if is_package else name.split(".")[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = here[: len(here) - (node.level - 1)] if node.level - 1 <= len(here) else []
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            if not module:
                continue
            out.add(module)
            out.update(f"{module}.{a.name}" for a in node.names)
    return out


def resolve(name: str, mods: dict) -> str:
    """Longest known prefix: `a.b.func` resolves to module `a.b`."""
    while name and name not in mods:
        name = name.rsplit(".", 1)[0] if "." in name else ""
    return name


def package_of(path: str) -> str:
    """The bucket the package ratchet uses: `nucleo/<sub>` for subpackages, `nucleo (top)` for its loose files,
    `voice/engine/llm` apart from the rest of `voice`, and the top-level directory for everything else."""
    parts = path.split("/")
    if parts[0] == "nucleo":
        return f"nucleo/{parts[1]}" if len(parts) > 2 else "nucleo (top)"
    if path.startswith("voice/engine/llm/"):
        return "voice/engine/llm"
    return parts[0]


def build() -> list[dict]:
    mods = product_modules()
    importers: dict[str, set[str]] = collections.defaultdict(set)
    for name, (path, src) in mods.items():
        for imp in imports_of(src, name, path.endswith("__init__.py")):
            target = resolve(imp, mods)
            if target and target != name:
                importers[target].add(name)
    test_refs: collections.Counter = collections.Counter()
    for p in (ROOT / "tests").rglob("*.py"):
        try:
            test_refs.update(DOTTED.findall(p.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    rows = []
    for name, (path, src) in mods.items():
        prod = sorted(importers.get(name, ()))
        rows.append({"m": name, "p": path, "pkg": package_of(path), "lines": src.count("\n") + 1,
                     "fanin": len(prod), "importers": prod, "tests": test_refs.get(name, 0),
                     "incident": bool(INCIDENT.search(src[:1500]))})
    return sorted(rows, key=lambda r: r["m"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", help="where to write the JSON rows")
    ap.add_argument("--summary", action="store_true", help="print package totals and orphans")
    args = ap.parse_args()
    rows = build()
    Path(args.out).write_text(json.dumps(rows, indent=0))
    print(f"modules {len(rows)} lines {sum(r['lines'] for r in rows)}")
    if args.summary:
        totals: collections.Counter = collections.Counter()
        for r in rows:
            totals[r["pkg"]] += r["lines"]
        for pkg, n in totals.most_common():
            print(f"  {pkg:28} {n:>7}")
        # `__main__.py` is an entry point by definition (`python -m server`), like a package's `__init__.py`.
        orphans = [r["p"] for r in rows if not r["fanin"] and not r["p"].endswith(("__init__.py", "__main__.py"))]
        print(f"orphans (no product importer) {len(orphans)}")


if __name__ == "__main__":
    main()
