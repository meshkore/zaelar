"""`scrape/` reads pages for everyone and depends on none of them (V2-846, audit N6/N8 of its design).

It never imports the turn (`nucleo.flash`), the workers (`nucleo.workers`), the dispatcher, `memory/`, `widgets/`,
`voice/` or `server/`: what it needs from the engine comes through `scrape/hooks.py`, wired at boot. The same ratchet
`search/` has (`test_the_search_service_owes_the_turn_nothing`), read from the AST of every module, lazy imports too.
"""
from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[3] / "scrape"
FORBIDDEN = ("nucleo.flash", "nucleo.workers", "nucleo.dispatch", "nucleo.turn", "memory", "widgets", "voice",
             "server")


def _imports(path: Path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            yield node.module


def test_no_module_of_scrape_imports_the_engine_it_serves():
    bad = [f"{p.name}: {m}" for p in sorted(PKG.glob("*.py")) for m in _imports(p)
           if any(m == f or m.startswith(f + ".") for f in FORBIDDEN)]
    assert not bad, bad


def test_the_package_exists_where_the_ratchet_reads_it():
    assert (PKG / "__init__.py").exists() and len(list(PKG.glob("*.py"))) >= 8
