"""Every import in the product names a module (or a name) that exists — lazy ones included (refactor2710-99, node 2.898).

Use case `docs-single-recipe-not-a-list__us` (2026-10-28, 1/5): «give me the carbonara recipe» never reached the rung
that writes ONE document in one request (`compose_rung`). That rung imported `nucleo.flash.prompt` LAZILY, inside the
function, and refactor2710-08b had deleted that module: the import failed at run time, the rung's own fail-open logged
a warning and handed the commission to a research worker, which delivered a sheet of eight links. No test imported the
function body, so the move looked green. A lazy import is still an import: this walks every one in the product tree and
resolves it — a module, or a name its package actually has.

Disarm: point the import in `nucleo/flash/compose_rung.py::compose` back at `nucleo.flash.prompt` and this goes red.
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import pathlib
import sys

ENGINE = pathlib.Path(__file__).resolve().parents[3]
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

#: The engine's own top-level packages: an import of anything else (stdlib, third party) is not ours to resolve.
_OURS = ("nucleo", "voice", "widgets", "server", "memory", "connectors", "search", "rules", "i18n", "bus",
         "observability", "config", "files", "library", "update")
_SKIP_PARTS = {".venv", "node_modules", "vendor", ".git", "tests", "__pycache__", ".claude", ".meshkore"}


def _resolves(module: str, name: str | None) -> bool:
    try:
        if name is None:
            return importlib.util.find_spec(module) is not None
        if importlib.util.find_spec(f"{module}.{name}") is not None:
            return True
    except Exception:  # noqa: BLE001 — a parent that cannot load is judged below by the attribute read
        pass
    try:
        return hasattr(importlib.import_module(module), name or "")
    except Exception:  # noqa: BLE001 — a module that cannot even load is reported by its own tests
        return True


def _imports(path: pathlib.Path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                if alias.name != "*":
                    yield node.lineno, node.module, alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name, None


def test_every_import_of_ours_resolves():
    missing = []
    for path in sorted(ENGINE.rglob("*.py")):
        rel = path.relative_to(ENGINE)
        if set(rel.parts) & _SKIP_PARTS or rel.parts[0] not in _OURS:
            continue
        for line, module, name in _imports(path):
            if module.split(".", 1)[0] in _OURS and not _resolves(module, name):
                missing.append(f"{rel}:{line}: {module}{'.' + name if name else ''}")
    assert not missing, "imports of modules or names that do not exist (a lazy one fails only when it runs):\n  " \
        + "\n  ".join(missing)
