#
# widgets/validator.py — static + runtime CONTRACT enforcement for a generated/modified widget (V2-098 split).
#
# Extracted from widgets/generator.py: that file mixed job orchestration (spawn the headless Claude Code agent,
# lock/journal it) with this — a static analyzer that has no shared mutable state with the orchestration half and
# is cohesive on its own ("does this widget's code obey the contract?"). generator.py imports `_validate` and the
# other names it calls directly, so existing callers (widgets/harness.py, widgets/server_api.py, and every test
# that does `from widgets import generator; generator._validate(...)`) keep working unchanged.
#
import json
import os
import re

from loguru import logger

from widgets import paths

HERE = paths.BUILTIN_ROOT                                  # …/zaelar/widgets
ZAELAR = os.path.dirname(HERE)                              # …/zaelar


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


# ── static house-rules scan (SEC-3 / INI-007 S-10) ──────────────────────────────────────────────────────────
# The runtime smoke-test proves view_data() RUNS; it does NOT prove the code obeys the isolation/no-network/no-XSS
# house rules (AGENTS.md). A headless agent can still emit innerHTML-with-interpolation (XSS), fetch/WebSocket
# (network from the client), dynamic import()/eval (dynamic code), or a non-stdlib import / hardcoded secret in
# data.py. These are STATIC red lines — enforce them, don't just ask for them in prose.

# widget.js: outright-banned sinks (network / dynamic code — never legitimate in a self-contained widget).
_JS_BANNED = [
    ("fetch(", re.compile(r"\bfetch\s*\(")),
    ("XMLHttpRequest", re.compile(r"\bXMLHttpRequest\b")),
    ("WebSocket", re.compile(r"\bWebSocket\b")),
    ("EventSource", re.compile(r"\bEventSource\b")),
    ("dynamic import()", re.compile(r"\bimport\s*\(")),
    ("eval()", re.compile(r"\beval\s*\(")),
    ("new Function()", re.compile(r"\bnew\s+Function\b")),
    ("external import", re.compile(r'\bimport\b[^\n;]*\bfrom\b\s*["\']')),   # self-contained: no module deps
]
# widget.js: HTML sinks are only dangerous with INTERPOLATION (a static string is fine). Flag assignment/call
# whose RHS on the same line carries a template `${…}` or a `+` string concat.
_JS_HTML_SINK = re.compile(
    r"(?:innerHTML|outerHTML)\s*=\s*(?P<rhs>.+)$|insertAdjacentHTML\s*\(|document\.write\s*\(", re.M)


def _bare_css_classes(css: str) -> set[str]:
    """Class names selected BARE (no ancestor combinator) in a CSS-ish text — i.e. a rule that applies to ANY
    element with that class, regardless of nesting (`.conn{...}`), as opposed to one scoped under another
    selector (`.mfoot .msg{...}`, which only ever matches a `.msg` INSIDE `.mfoot`). Only the bare form leaks
    properties onto an unrelated element elsewhere in the document that happens to reuse the same class name."""
    out = set()
    for sel_list, _ in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        for sel in sel_list.split(","):
            first = re.split(r"[\s>+~:]", sel.strip(), maxsplit=1)[0]
            m = re.fullmatch(r"\.([a-zA-Z][\w-]*)", first)
            if m:
                out.add(m.group(1))
    return out


def _all_css_classes(css: str) -> set[str]:
    """Every class token anywhere in a selector, nested or not (`.hb-msg .conn` → {"hb-msg","conn"}). Used on the
    WIDGET's own stylesheet: even a class it nests under its own wrapper still ends up on a real DOM element,
    which will ALSO match a bare global rule for that same name regardless of the widget's intended scoping."""
    out = set()
    for sel_list, _ in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        out.update(re.findall(r"\.([a-zA-Z][\w-]*)", sel_list))
    return out


_HOUSE_CSS_CACHE = {"mtime": None, "classes": set()}


def _house_global_classes() -> set[str]:
    """Bare classes defined in the app-wide stylesheet (frontend/app/styles.css) — the set a widget must never
    reuse verbatim, or it silently inherits whatever that global rule sets (position/display/etc.), invisibly,
    the moment the app stylesheet is loaded alongside the widget's own. This is exactly how it broke once already:
    mensajeria's own connection-card used the class "conn", which collided with the app's BARE `.conn{position:
    fixed;left:20px;bottom:14px;...}` (the mic/SSE status line) and got yanked out of the widget card entirely."""
    css_path = os.path.join(ZAELAR, "frontend", "app", "styles.css")
    try:
        mtime = os.path.getmtime(css_path)
    except OSError:
        return set()
    if _HOUSE_CSS_CACHE["mtime"] == mtime:
        return _HOUSE_CSS_CACHE["classes"]
    classes = _bare_css_classes(open(css_path, encoding="utf-8").read())
    _HOUSE_CSS_CACHE["mtime"], _HOUSE_CSS_CACHE["classes"] = mtime, classes
    return classes


_FULL_LINE_COMMENT_RE = re.compile(r"^\s*//.*$", re.M)


def _scan_widget_js(js: str) -> str | None:
    # False positive found in the marathon 2026-07-22/23: a full-line comment DESCRIBING the contract ("NO
    # fetch") tripped the ban on its own prose. Strip whole-line `//` comments before matching the banned sinks —
    # trailing same-line comments are left alone (lower risk, not the shape that caused this).
    banned_scan = _FULL_LINE_COMMENT_RE.sub("", js)
    for label, rx in _JS_BANNED:
        if rx.search(banned_scan):
            return f"widget.js uses banned {label} (widgets are self-contained; no network/dynamic code)"
    for m in _JS_HTML_SINK.finditer(js):
        rhs = m.groupdict().get("rhs")
        if rhs is None:                                    # insertAdjacentHTML / document.write → always flagged
            return "widget.js uses insertAdjacentHTML/document.write (use textContent + createElement)"
        if "${" in rhs or re.search(r"\+\s*[A-Za-z_$]", rhs):   # interpolated/concatenated HTML → XSS sink
            return "widget.js assigns interpolated innerHTML/outerHTML (XSS: build DOM with textContent)"
    # Class-name collision with the app-wide stylesheet: scan only the widget's OWN injected <style> (template
    # literal bodies) so JS property-access chains (e.g. `document.body`) can never produce a false positive.
    house = _house_global_classes()
    if house:
        style_text = "\n".join(re.findall(r"`([^`]*)`", js, re.S))
        used = _all_css_classes(style_text)
        bad = sorted(c for c in used if c in house and not c.startswith(("hbk-", "hb-")))
        if bad:
            names = ", ".join("." + c for c in bad)
            return (f"widget.js styles a class name also defined GLOBALLY in frontend/app/styles.css ({names}) — "
                    f"rename it to something widget-specific; the global rule's properties (position/display/etc.) "
                    f"silently apply to your element too, regardless of your own CSS")
    # A WIDTH NO PHONE CAN HONOUR (V2-574). The mobile shell gives every widget a 390px card, and a `min-width`
    # larger than that is the one CSS declaration a scroll container CANNOT absorb: the box refuses to shrink, so
    # the card scrolls sideways and the operator gets a widget he has to drag around to read. A plain `width` is
    # not flagged — a wide element inside an `overflow-x:auto` wrapper is the CORRECT way to show a wide table,
    # and rejecting it would push authors toward truncating data instead of letting it scroll in its own box.
    # Measured before choosing the threshold: all 14 system widgets pass at 390px, and none declares a min-width
    # over 360 (tests/browser/e2e/mobile/render_widgets_on_a_phone.py is the behavioural half of this rule).
    style_text = "\n".join(re.findall(r"`([^`]*)`", js, re.S))
    for m in re.finditer(r"min-width\s*:\s*(\d+(?:\.\d+)?)px", style_text, re.I):
        if float(m.group(1)) > _PHONE_SAFE_MIN_WIDTH_PX:
            return (f"widget.js declares min-width:{m.group(1)}px — wider than a phone card can hold "
                    f"({_PHONE_SAFE_MIN_WIDTH_PX}px is the limit). Let the layout be FLUID (%, minmax, flex-wrap); "
                    f"if the content is genuinely wide (a table), keep it in its own overflow-x:auto wrapper so "
                    f"it scrolls INSIDE the card instead of pushing the card sideways")
    return None


# The widest a widget may REFUSE to shrink below. The mobile card is 390px minus 12px of padding on each side
# (366px of content), so 360 leaves a hair of tolerance and still fails anything designed for a desk.
_PHONE_SAFE_MIN_WIDTH_PX = 360


# data.py: stdlib-only. Allow the standard library, relative imports, and the widgets package (store/planner).
_SECRET_RX = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r'(?i)\b(?:api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*["\'][^"\']{8,}["\']'),
]


def _apply_action_names(src: str) -> set[str] | None:
    """The action names an `apply_action(action, …)` actually HANDLES, by scanning the comparisons against its
    first parameter (`if action == "x"`, `elif action in ("a","b")`, `action.strip() == "x"`). Returns the set
    of handled literals, an EMPTY set if apply_action exists but uses a dispatch style we can't parse statically
    (e.g. a dict table — caller then fail-opens), or None if there is no apply_action at all. Stdlib AST, no
    execution. This is the enforcement half of "declared actions must match apply_action" (V2-025)."""
    import ast
    try:
        tree = ast.parse(src)
    except Exception:
        return None
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "apply_action"), None)
    if fn is None:
        return None
    param = fn.args.args[0].arg if fn.args.args else "action"

    def _is_action_ref(node) -> bool:
        # `action`, or a chained call/attr on it: `action.strip()`, `action.lower().strip()`.
        while isinstance(node, ast.Call):
            node = node.func
        while isinstance(node, ast.Attribute):
            node = node.value
        return isinstance(node, ast.Name) and node.id == param

    names: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Compare) or not _is_action_ref(node.left):
            continue
        for op, comp in zip(node.ops, node.comparators):
            if isinstance(op, ast.Eq) and isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                names.add(comp.value)
            elif isinstance(op, ast.In) and isinstance(comp, (ast.Tuple, ast.List, ast.Set)):
                names.update(e.value for e in comp.elts
                             if isinstance(e, ast.Constant) and isinstance(e.value, str))
    return names


def _defines_function(src: str, name: str) -> bool:
    """True if the module defines top-level `def <name>(`, checked by AST without executing it."""
    import ast
    try:
        tree = ast.parse(src)
    except Exception:
        return False
    return any(isinstance(n, ast.FunctionDef) and n.name == name for n in tree.body)


def _validate_background(man: dict, src: str) -> str | None:
    """A widget declaring `background` (cyclic off-screen execution, V2-034) must be valid: `every` must parse to a
    period (>=1s), and a PASSIVE widget with background MUST have `def tick()` in data.py, the function called by the
    scheduler each cycle. A `backed` widget with background is served by its owner (`tick` command in the mailbox),
    so tick() is not required in data.py."""
    if man.get("background") is None:
        return None
    from . import background as _bg
    period = _bg.parse_period(man.get("background"))
    if not period:
        return (f"'background' invalid ({man.get('background')!r}); use \"1s\"/\"5m\"/\"1h\", a number of seconds, "
                f"or {{\"every\":\"1m\"}} (minimum 1s)")
    if (man.get("kind") or "passive") != "backed" and not _defines_function(src, "tick"):
        return ("manifest declares 'background' (off-screen cycle) but data.py does not define `def tick()`; "
                "add tick() to refresh data and write to memory, or remove 'background'")
    return None


def _validate_actions_sync(man: dict, src: str) -> str | None:
    """Declared `actions` (the widget's DATA API the brain drives) must MATCH what `apply_action` really handles.
    A declared action with no handler is a dead entry; a handled action not declared is invisible to the brain —
    both are rejected (V2-025). Only for PASSIVE widgets: a `backed` widget routes actions through its owner's
    mailbox, not data.py:apply_action (the supervisor owns that contract), so skip it here."""
    if (man.get("kind") or "passive") == "backed":
        return None
    declared = {str(k).strip() for k in (man.get("actions") or {}) if str(k).strip()}
    if not declared:
        return None                                     # nothing declared → nothing to keep in sync
    handled = _apply_action_names(src)
    if handled is None:
        return (f"manifest declares actions {sorted(declared)} but data.py has no apply_action() to handle them "
                f"(declare them only if the widget can perform them)")
    if not handled:
        return None                                     # dispatch style we can't parse statically → fail-open
    dead = sorted(declared - handled)
    invisible = sorted(handled - declared)
    if dead:
        return (f"manifest declares action(s) {dead} that apply_action does NOT handle — remove them or add the "
                f"branch (declared actions must match apply_action)")
    if invisible:
        return (f"apply_action handles action(s) {invisible} not declared in manifest 'actions' — the brain can't "
                f"see them; declare each one (name/desc/payload) so the widget's data API is complete")
    return None


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
_STDLIB_EXEMPT = {"musica", "agenda", "archivos", "fotos"}


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
    for rx in _SECRET_RX:
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
    if _dirty:
        json.dump(man, open(man_p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    js_src = open(js_p, encoding="utf-8").read() if os.path.isfile(js_p) else ""
    if not js_src or "export function render" not in js_src:
        return False, "widget.js missing or has no `export function render`"
    js_bad = _scan_widget_js(js_src)                        # static house-rules gate (SEC-3): no XSS/network/dynamic code
    if js_bad:
        return False, js_bad
    dp = os.path.join(d, "data.py")
    data_src = ""
    if os.path.isfile(dp):
        data_src = open(dp, encoding="utf-8").read()
        data_bad = _scan_data_py(data_src, wid)          # stdlib-only + no hardcoded secrets
        if data_bad:
            return False, data_bad
        sync_bad = _validate_actions_sync(man, data_src)   # declared actions <-> apply_action must match (V2-025)
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
    bg_bad = _validate_background(man, data_src)         # background cycle valid + passive needs tick() (V2-034)
    if bg_bad:
        return False, bg_bad
    init_p = os.path.join(d, "__init__.py")
    if not os.path.isfile(init_p):
        open(init_p, "w").close()
    return True, ""
