#
# widgets/validator.py — static + runtime CONTRACT enforcement for a generated/modified widget (V2-098 split).
#
# Extracted from widgets/generator.py: that file mixed job orchestration (spawn the headless Claude Code agent,
# lock/journal it) with this — a static analyzer that has no shared mutable state with the orchestration half and
# is cohesive on its own ("does this widget's code obey the contract?"). generator.py imports `_validate` and the
# other names it calls directly, so existing callers (tests/widget_harness.py, widgets/server_api.py, and every test
# that does `from widgets import generator; generator._validate(...)`) keep working unchanged.
#
import json
import os
import re

from loguru import logger

from widgets import paths
from widgets import validator_js as _validator_js  # split out (refactor2710-99)
from widgets import validator_actions as _validator_actions  # split out (refactor2710-99)


def _keyword_collisions(wid: str, keywords: list) -> dict:
    """Map each of this widget's keywords to the OTHER catalog widgets already using it (case-insensitive).
    AGENTS.md asks for precise, non-overlapping keywords; this is the enforcement half."""
    from . import runtime
    mine = {str(k).strip().lower() for k in (keywords or []) if str(k).strip()}
    out: dict = {}
    for w in runtime.catalog():
        if w.get("id") == wid:
            continue
        theirs = {str(k).strip().lower() for k in (w.get("keywords") or [])}
        for k in sorted(mine & theirs):
            out.setdefault(k, []).append(w.get("id"))
    return out


# ── static house-rules scan (SEC-3) ──────────────────────────────────────────────────────────
# The runtime smoke-test proves view_data() RUNS; it does NOT prove the code obeys the isolation/no-network/no-XSS
# house rules (AGENTS.md). A headless agent can still emit innerHTML-with-interpolation (XSS), fetch/WebSocket
# (network from the client), dynamic import()/eval (dynamic code), or a non-stdlib import / hardcoded secret in
# data.py. These are STATIC red lines — enforce them, don't just ask for them in prose.


# stdlib-only is the contract for GENERATED widgets (an LLM-authored data.py must never reach into `connectors/`:
# that's the isolation invariant AGENTS.md/CLAUDE.md rely on). The exceptions are hand-built, human-reviewed
# widgets whose whole job IS a connector, and each one is here because there is no stdlib equivalent of what it
# needs — never because it was convenient. This allowlist is a set of hardcoded ids, never a manifest field,
# precisely so a generated widget can't grant itself the exemption.
#
#   · `musica`   — real playback control has to call connectors.music/connectors.spotify (see its data.py header).
#   · `agenda`   — V2-540 put the calendar connectors in its header; `calendars()` READS the real connector
#                  inventory instead of declaring a state, so the day one is registered it lights up with
#                  nothing else to change. (This entry is a FIX: V2-540 shipped the import without it, which
#                  left `make test-widgets` red for everyone and made the next widget's own failure
#                  indistinguishable from it.)
#   · `archivos` — V2-557. The cloud drive lives behind an OAuth token that is refreshed in the credential
#                  store; there is no stdlib way to reach somebody's Drive. The import stays DEFERRED inside
#                  the functions that need it, so module import — and therefore the catalog, and therefore
#                  every prompt that lists widgets — never pays for `httpx` or the credential store.
#   · `results`  — V2-601 T-10. The errand SHEET is an engine surface, not a generated widget: its audit
#                  trail goes through `voice.observer.emit` (the single log funnel — a parallel one would be
#                  the real violation) and the SUMMARY tab's audit ids come from `observability.identity`
#                  IN the payload, because widget.js may not fetch. Both imports deferred + fail-open.
#                  Until this entry existed the harness sat permanently red on `results`, under which a NEW
#                  violation in any widget was invisible — the exemption is what makes the gate mean something.
_STDLIB_EXEMPT = {"musica", "agenda", "archivos", "fotos", "youtube", "results",
                   # V2-611: the email signature lives in `config/connectors.py` — the SAME store the
                   # connect wizard already writes account credentials to — and reading the effective
                   # signature for view_data needs `connectors.email.config`, lazily, exactly like
                   # `youtube`'s own `_svc()` reaches its connector.
                   "mensajeria",
                   # V2-637 → V2-764: the torrent client's surface now lives INSIDE `archivos`
                   # (already exempt above), deferred so the catalog never imports libtorrent.
                   # V2-644: a report errand binds this sheet to its task, and the Proceso view is derived
                   # per read from `nucleo.dispatch.task_progress` — deferred + fail-open, the same seam
                   # `results` already has for its live view.
                   "documento"}


def _scan_data_py(src: str, wid: str = "") -> str | None:
    import ast
    import sys
    try:
        tree = ast.parse(src)
    except Exception as e:
        return f"data.py does not parse: {e}"
    if wid not in _STDLIB_EXEMPT:
        stdlib = getattr(sys, "stdlib_module_names", set())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    top = a.name.split(".")[0]
                    if top not in stdlib and top != "widgets":
                        return f"data.py imports non-stdlib '{top}' (data.py must be stdlib-only)"
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue                               # relative import (from .. import store) is allowed
                top = (node.module or "").split(".")[0]
                if top and top not in stdlib and top != "widgets":
                    return f"data.py imports non-stdlib '{top}' (data.py must be stdlib-only)"
    for rx in _validator_actions._SECRET_RX:
        if rx.search(src):
            return "data.py contains a hardcoded secret/credential"
    return None


def _validate(wid: str, *, stamp_origin: bool = False) -> tuple[bool, str]:
    """The widget must meet the contract before we trust it in the catalog."""
    d = paths.dir_for(wid) or paths.new_dir(wid)
    man_p, js_p = os.path.join(d, "manifest.json"), os.path.join(d, "widget.js")
    if not os.path.isfile(man_p):
        return False, "no manifest.json produced"
    try:
        man = json.load(open(man_p, encoding="utf-8"))
    except Exception as e:
        return False, f"manifest.json invalid: {e}"
    if not man.get("title") or not isinstance(man.get("keywords"), list) or not man.get("keywords"):
        return False, "manifest missing title/keywords"
    # Keyword anti-collision: if EVERY keyword is already owned by other widgets, this one is unidentifiable by
    # voice (or hijacks an existing identity) -> reject. Partial overlaps are allowed but logged; identify()
    # handles them with disambiguation candidates, and stripping them here would regress older widgets' recall.
    kws = [str(k).strip() for k in man["keywords"] if str(k).strip()]
    coll = _keyword_collisions(wid, kws)
    if kws and len(coll) >= len({k.lower() for k in kws}):
        owners = sorted({o for v in coll.values() for o in v})
        return False, (f"all keywords already belong to other widgets ({', '.join(owners)}) — "
                       f"the widget would be unidentifiable; use distinctive keywords")
    if coll:
        logger.warning(f"widget-agent: '{wid}' keyword collisions (identify() will disambiguate): {coll}")
    # Folder name is authoritative. `origin:"user"` is stamped ONLY when the caller is the generator, i.e. when
    # this widget was JUST created by the operator (V2-083) — that is what the Config Widgets tab reads for its
    # "built-in"/"yours" badge, and built-ins resolve through the curated `registry._BUILTINS` list instead.
    #
    # ⚠️ `stamp_origin` exists because this same validator is ALSO the contract check `make test-widgets` runs over
    # the WHOLE catalog, and there the stamp is plain wrong: measured 2026-08-28, one harness run relabelled 15
    # SHIPPED widgets — `musica`, `youtube`, `navegador`, `results` among them — as user-created, `results` losing
    # an explicit `origin:"builtin"` it already had. Nothing failed; the manifests were simply rewritten on disk,
    # waiting for someone to commit them. A check that MUTATES what it is checking has to be told when it may.
    _dirty = False
    if man.get("id") != wid:
        man["id"] = wid
        _dirty = True
    if stamp_origin and man.get("origin") != "user" and not paths.is_repo_source(d):
        man["origin"] = "user"
        _dirty = True
    # V2-792 — every widget the generator writes carries how it lives on several screens. The agent is asked to
    # decide it; if it did not, the resolved default is written (an output channel ⇒ single), so no widget it
    # touches — new, or an older one being modified — is left without the declaration.
    from . import screen_policy
    if stamp_origin and "screens" not in man:
        man["screens"] = screen_policy.of(man)
        _dirty = True
    if _dirty:
        json.dump(man, open(man_p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    js_src = open(js_p, encoding="utf-8").read() if os.path.isfile(js_p) else ""
    if not js_src or "export function render" not in js_src:
        return False, "widget.js missing or has no `export function render`"
    js_bad = _validator_js._scan_widget_js(paths.client_source(d))                        # static house-rules gate (SEC-3): no XSS/network/dynamic code
    if js_bad:
        return False, js_bad
    dp = os.path.join(d, "data.py")
    data_src = ""
    if os.path.isfile(dp):
        data_src = open(dp, encoding="utf-8").read()
        data_bad = _scan_data_py(data_src, wid)          # stdlib-only + no hardcoded secrets
        if data_bad:
            return False, data_bad
        sync_bad = _validator_actions._validate_actions_sync(man, data_src, d)  # declared actions <-> apply_action must match (V2-025)
        if sync_bad:
            return False, sync_bad
        import py_compile
        try:
            py_compile.compile(dp, doraise=True)
        except Exception as e:
            return False, f"data.py does not compile: {e}"
        # Runtime smoke-test: view_data(q="") must RUN and RETURN a dict — never raise. This is the isolation gate:
        # a widget that blows up at runtime never reaches the catalog (a friendly {"error": ...} state is fine).
        try:
            import importlib
            paths.forget_modules(wid)                   # a cached import may still point at ANOTHER folder (fork)
            mod = importlib.import_module(f"widgets.{wid}.data")
            mod = importlib.reload(mod)                 # test the just-written code, not a cached import (modify)
            if hasattr(mod, "view_data"):
                out = mod.view_data(q="")
                if not isinstance(out, dict):
                    return False, "view_data() must return a dict"
        except Exception as e:
            return False, f"view_data() raised at runtime: {type(e).__name__}: {e}"
    elif (man.get("kind") or "passive") != "backed" and (man.get("actions") or {}):
        return False, "manifest declares actions but the widget has no data.py to handle them"
    bg_bad = _validator_actions._validate_background(man, data_src)         # background cycle valid + passive needs tick() (V2-034)
    if bg_bad:
        return False, bg_bad
    scr_bad = screen_policy.problem(man)                 # V2-792: a value, and never shared with an output channel
    if scr_bad:
        return False, scr_bad
    init_p = os.path.join(d, "__init__.py")
    if not os.path.isfile(init_p):
        open(init_p, "w").close()
    return True, ""
