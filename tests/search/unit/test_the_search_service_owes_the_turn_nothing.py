"""The search service imports nothing from the turn, the voice motor or the widgets (V2-782 T5.1) — a ratchet at zero.

The turn calls `search`; `search` never calls the turn. What it needs from its host (the status light, the
timeline) are callables in `search/hooks.py` the server sets at boot. A new import of `nucleo.flash`, `voice` or
`widgets` from inside `search/` is a red test, not a style note: it is what would make the service a corner of
the brain again, and what would stop it running as its own process.

Allowed from `nucleo`: the leaf helpers the whole engine shares (`nucleo.errors`, `nucleo.workspace`,
`nucleo.energy.meter`). Allowed from the engine: `i18n` (the language table) and the standard library.
"""
from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
SEARCH = ENGINE / "search"

FORBIDDEN_PREFIXES = ("nucleo.flash", "voice", "widgets", "server", "memory", "connectors", "frontend")
# `nucleo.energy.lease` (V2-785): the gate asked BEFORE a paid index is called — the meter's twin, and a leaf.
# `nucleo.energy.egress` (2026-10-23): the door a paid index's URL passes in a mediated deployment — the lease's twin
# for WHERE the call goes, and a leaf like it.
ALLOWED_NUCLEO = {"nucleo.errors", "nucleo.workspace", "nucleo.energy.meter", "nucleo.energy.lease",
                  "nucleo.energy.egress"}


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name, node.lineno
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            pkg = node.module == "nucleo" or (ENGINE / node.module.replace(".", "/")).is_dir()
            for a in (node.names if pkg else [None]):
                yield node.module + (f".{a.name}" if a else ""), node.lineno


def test_search_never_imports_the_turn_the_motor_or_the_widgets():
    bad = []
    for p in sorted(SEARCH.rglob("*.py")):
        for mod, line in _imports(p):
            if mod.startswith(FORBIDDEN_PREFIXES):
                bad.append(f"{p.relative_to(ENGINE)}:{line} imports {mod}")
            if mod.startswith("nucleo") and mod not in ALLOWED_NUCLEO:
                bad.append(f"{p.relative_to(ENGINE)}:{line} reaches into {mod} (only {sorted(ALLOWED_NUCLEO)} are leaves)")
    assert not bad, "\n".join(bad)


def test_the_old_names_are_aliases_of_the_same_module_object():
    """`from nucleo import websearch` and `from search import web` are ONE module: a patch through either name
    reaches both, so the existing tests and callers keep measuring the product."""
    import nucleo
    from nucleo import browser_search, image_search, listing_extract, listing_search, websearch
    import search.browser, search.extract, search.images, search.listing, search.web  # noqa: E401
    assert websearch is search.web and nucleo.websearch is search.web
    assert listing_search is search.listing and listing_extract is search.extract
    assert browser_search is search.browser and image_search is search.images
    assert websearch.search is search.web.search


def test_the_hooks_are_no_ops_until_the_host_sets_them():
    from search import hooks
    hooks.chain_failed("quota", "x")          # unset → nothing happens, nothing raises
    hooks.note("search", "x", text="y")
    seen = []
    old = hooks.on_chain_failure
    try:
        hooks.on_chain_failure = lambda kind, detail: seen.append((kind, detail))
        from search import web
        web.note_failure("HTTP 429 quota")
        assert seen == [("quota", "HTTP 429 quota")]
    finally:
        hooks.on_chain_failure = old
        web.note_success()
