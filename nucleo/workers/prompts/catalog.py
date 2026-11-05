"""The worker's TWO-LAYER catalogue (V2-851 §5, F3): the headline of what exists in the brief, a family's full set on
request through the bridge (`python -m nucleo.cli.bridge catalog <family>`).

Measured before this (F0 §15e): the first request of a worker was ≈46k chars, 64 % of it the brief, every family of
every capability written out whatever the task — the browser method to a worker writing a document, the trusted
sites to one sending a message. Model time is 70-90 % of a worker's wall, and its first request is the slowest.
Same rule as V2-526's for the voice turn: a catalogue never costs prompt in full — one or two lines per family, the
rest when the task's checkpoint 4 needs it.

A family's full text REUSES what already existed (the browser's blocks in `prompts/web.py`, the network's step 0,
the site catalogue, the library and third-party blocks, `cli.widget`'s manifest reads, the bridge's `decide` hint);
the headlines and the few short texts that had no home are words of the `voice` pack (`worker_brief.*`).
"""
from __future__ import annotations

import re
from typing import Callable

#: A worker's first message may cost this many chars (V2-851 §5). Measured 2026-11-05 on the composer, es+en, no memory
#: and no conversation: hotel errand 15.6k WITH a research brief (the largest sample; 24.8k before without one),
#: document 10.4k (27.2k before), message 9.2k (26.0k before). A brief over it is a defect: raise it only with a
#: declared mechanism beside it. The battery's C11 reads the same number on the live `worker_start.prompt_chars`.
PROMPT_CEILING_CHARS = 16_000

#: The order the headlines are listed in. Changing it changes the cached prefix of every worker.
FAMILIES = ("browser", "mesh", "sites", "messaging", "widgets", "results", "library", "third_party", "schedule", "decide",
            "rules", "method")


def words(path: str, default: str = "") -> str:
    try:
        from i18n import langs
        return str(langs.words(f"worker_brief.{path}", default=default) or default)
    except Exception:  # noqa: BLE001 — a missing pack never blocks a worker
        return default


def headlines(skip: tuple = ()) -> str:
    """One line per family, in a fixed order (part of the stable prefix)."""
    lines = [f"  · {name} — {words(f'families.{name}')}" for name in FAMILIES
             if name not in skip and words(f"families.{name}")]
    return (words("catalog_intro") + "\n" + "\n".join(lines)) if lines else ""


def said_block() -> str:
    """His standing rules as DATA (`rules_bridge`), or ''."""
    try:
        from nucleo.workers import rules_bridge
        return rules_bridge.brief_block()
    except Exception:  # noqa: BLE001
        return ""


def known_lines(goal: str) -> str:
    """What is already KNOWN about this errand (the workflow table's route, the sources that walled or served before):
    facts about THIS task, so they stay in the brief while the network's how-to is a family. '' when nothing."""
    try:
        from nucleo.workers.prompts import context
        return (context._known_route_line(goal) + context._sources_line()).strip()
    except Exception:  # noqa: BLE001
        return ""


def _browser() -> str:
    from nucleo.workers.prompts import web
    from nucleo.workers.prompts.drawer import _HUMAN_NAV_GUIDE
    from nucleo.workers.providers import claude as _c
    py = _c.bridge_python()
    try:
        from i18n import langs
        native = langs.current_language().native
    except Exception:  # noqa: BLE001
        native = "English"
    return "\n\n".join([web.driving_block(py).rstrip(), _HUMAN_NAV_GUIDE.rstrip(), web.method_block(py).rstrip(),
                        web.close_block(native)])


def _mesh() -> str:
    from nucleo.workers.prompts.context import _mesh_first_block
    return _mesh_first_block(browser=False)


def _sites() -> str:
    from i18n import langs
    from nucleo.flash import site_catalog
    return site_catalog.directive_block(site_catalog.resolve_locale(langs.current_code()))


def _widgets() -> str:
    try:
        from widgets import runtime
        ids = sorted({str(w.get("id")) for w in runtime.catalog() if w.get("id")})
    except Exception:  # noqa: BLE001
        ids = []
    return words("family_text.widgets") + ("\n" + ", ".join(ids) if ids else "")


def _results() -> str:
    from nucleo.workers.prompts.drawer import _with_presentation
    from nucleo.workers.prompts.research import sheet_contract
    return _with_presentation(sheet_contract())       # + the results surface's presentation budgets


def _library() -> str:
    from nucleo.workers.prompts.surfaces import library_block
    return library_block()


def _third_party() -> str:
    from nucleo.workers.prompts.surfaces import errand_block
    return errand_block()


def _decide() -> str:
    from nucleo.cli.bridge import _hint_decide
    return _hint_decide()


def _method() -> str:
    from nucleo.workers.prompts.context import _METHOD_BLOCK
    return _METHOD_BLOCK


_FULL: dict[str, Callable[[], str]] = {
    "browser": _browser, "mesh": _mesh, "sites": _sites, "widgets": _widgets, "results": _results, "library": _library,
    "third_party": _third_party, "decide": _decide, "method": _method,
    "messaging": lambda: words("family_text.messaging"), "schedule": lambda: words("family_text.schedule"),
    "rules": lambda: words("family_text.rules"),
}


def full(name: str) -> str:
    """A family's full set, with the real interpreter in every bridge line; an unknown name lists the families."""
    key = str(name or "").strip().lower()
    fn = _FULL.get(key)
    if fn is None:
        return words("catalog_unknown", "No family «{name}». Families: {names}.").format(
            name=name, names=", ".join(FAMILIES))
    text = fn() or ""
    py = ""
    try:
        from nucleo.workers.providers import claude as _c
        py = _c.bridge_python()
    except Exception:  # noqa: BLE001
        pass
    return with_py(text, py)


def with_py(text: str, py: str) -> str:
    """Every bare `python -m nucleo.` with the real interpreter; one already absolute (the browser's) stays."""
    return re.sub(r"(?<![/\w.])python -m nucleo\.", lambda _m: f"{py} -m nucleo.", text) if py else text
