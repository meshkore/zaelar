"""widgets/validator_actions.py — the action-contract checks of a widget: declared vs implemented actions, background hooks, confirm questions."""
from __future__ import annotations

import json
import os
import re
from loguru import logger
from widgets import paths


# data.py: stdlib-only. Allow the standard library, relative imports, and the widgets package (store/planner).
_SECRET_RX = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r'(?i)\b(?:api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*["\'][^"\']{8,}["\']'),
]


def _literal_actions(fn, param: str, follow_aliases: bool = False) -> set[str]:
    """Action literals a function body compares its `param` against — `if action == "x"`, `elif action in
    ("a","b")`, `action.strip() == "x"`. The scanning half shared by the two functions below, so a delegate
    module is read by exactly the same rules as apply_action itself."""
    import ast

    def _refers_to(node, names: set[str]) -> bool:
        # `action`, or a chained call/attr on it: `action.strip()`, `action.lower().strip()`.
        while isinstance(node, ast.Call):
            node = node.func
        while isinstance(node, ast.Attribute):
            node = node.value
        return isinstance(node, ast.Name) and node.id in names

    # V2-778 F1-12 — in a DELEGATE, a local alias of the parameter counts as the parameter: `act = str(action or
    # "")` is how `widgets/agenda/tasklists.apply` normalizes it, and without following it every task action the
    # agenda delegates read as a dead manifest entry (`make test-widgets` red since V2-744). Only plain aliases:
    # a name assigned from an expression whose every Name is the parameter or `str`. Not applied to
    # `apply_action` itself yet: there it would turn two fail-open widgets (archivos, imagenes) into verdicts
    # that need a decision first (V2-778 §Log).
    aliases = {param}
    for node in (ast.walk(fn) if follow_aliases else ()):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            ids = {x.id for x in ast.walk(node.value) if isinstance(x, ast.Name)}
            if param in ids and ids <= {param, "str"}:
                aliases.add(node.targets[0].id)

    def _is_action_ref(node) -> bool:
        return _refers_to(node, aliases)

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


def _delegated_actions(fn, param: str, tree, wdir: str) -> set[str]:
    """Actions `apply_action` hands to a SIBLING module of the same widget — `library.apply(action, …)`.

    Without this the gate and the architecture ratchet pull in opposite directions: the ratchet pays a
    growing file by EXTRACTING a module, and the gate would then call every extracted action a dead manifest
    entry — so the only way to stay green would be to keep every widget's whole dispatch in one god file. The
    delegate is read by the same rules as apply_action; anything that cannot be resolved statically is simply
    not counted, so the gate keeps failing closed on real drift and never on a structure it does not know.
    """
    import ast
    if not wdir:
        return set()
    local = set()                                        # names bound by `from . import x` at module level
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and not node.module:
            local.update(a.asname or a.name for a in node.names)
    out: set[str] = set()
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id in local
                and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == param):
            continue
        path = os.path.join(wdir, node.func.value.id + ".py")
        if not os.path.isfile(path):
            continue
        try:
            sub = ast.parse(open(path, encoding="utf-8").read())
        except Exception:
            continue
        target = next((n for n in sub.body
                       if isinstance(n, ast.FunctionDef) and n.name == node.func.attr), None)
        if target is None or not target.args.args:
            continue
        out |= _literal_actions(target, target.args.args[0].arg, follow_aliases=True)
    return out


def _table_actions(fn, tree) -> set[str]:
    """The keys of a module-level `ACTIONS = {"name": handler, …}` table that `apply_action` consults.

    V2-778 F1-12 turns the widgets' if-chains into this table, and without reading it the gate would have
    fail-opened on every converted widget — the contract check switched off without a sound. Only a dict
    literal whose every key is a string, and only when `apply_action` names `ACTIONS`: anything else is not
    a dispatch this gate knows, and stays not counted.

    The table may also be READ OFF the module's `_a_<action>` names (`ACTIONS = {n[3:]: f for n, f in
    globals().items() if n.startswith("_a_")}`, refactor2710-12): then the handled actions are those names, bound
    at module level by a `def`, an assignment or an import."""
    import ast
    if not any(isinstance(n, ast.Name) and n.id == "ACTIONS" for n in ast.walk(fn)):
        return set()
    for node in getattr(tree, "body", []):
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "ACTIONS"):
            continue
        if (isinstance(node.value, ast.Dict) and node.value.keys
                and all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in node.value.keys)):
            return {k.value for k in node.value.keys}
        if isinstance(node.value, ast.DictComp):
            return {name[3:] for name in _bound_names(tree) if name.startswith("_a_")}
    return set()


def _bound_names(tree) -> set[str]:
    """Every name bound at module level: `def`, assignment targets (chained ones too) and imports."""
    import ast
    out = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            out |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.ImportFrom):
            out |= {a.asname or a.name for a in node.names}
    return out


def _apply_action_names(src: str, wdir: str = "") -> set[str] | None:
    """The action names an `apply_action(action, …)` actually HANDLES: the literals it compares against its
    own first parameter, plus those it delegates to a sibling module of the same widget. Returns the set of
    handled literals, an EMPTY set if apply_action exists but uses a dispatch style we can't parse statically
    (a computed dispatch — caller then fail-opens; an `ACTIONS` dict literal IS read), or None if there is no
    apply_action at all. Stdlib AST, no execution. This is the enforcement half of "declared actions must
    match apply_action" (V2-025)."""
    import ast
    try:
        tree = ast.parse(src)
    except Exception:
        return None
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "apply_action"), None)
    if fn is None:
        return None
    param = fn.args.args[0].arg if fn.args.args else "action"
    names = _literal_actions(fn, param) | _table_actions(fn, tree)
    if names:                    # an unparsable dispatch stays empty (fail-open); a parsable one may delegate
        names |= _delegated_actions(fn, param, tree, wdir)
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


def _validate_actions_sync(man: dict, src: str, wdir: str = "") -> str | None:
    """Declared `actions` (the widget's DATA API the brain drives) must MATCH what `apply_action` really handles.
    A declared action with no handler is a dead entry; a handled action not declared is invisible to the brain —
    both are rejected (V2-025). Only for PASSIVE widgets: a `backed` widget routes actions through its owner's
    mailbox, not data.py:apply_action (the supervisor owns that contract), so skip it here."""
    if (man.get("kind") or "passive") == "backed":
        return None
    declared = {str(k).strip() for k in (man.get("actions") or {}) if str(k).strip()}
    if not declared:
        return None                                     # nothing declared → nothing to keep in sync
    handled = _apply_action_names(src, wdir)
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
    return _validate_confirm_questions(man)


def _validate_confirm_questions(man: dict) -> str | None:
    """An action that ASKS the operator must carry the sentence he hears (`confirm_q`) — V2-665.

    `desc` is written FOR THE MODEL, and the fallback that quotes it read our own tool prose out loud:
    «Ojo, esto es permanente: "BUSCAR vídeos para elegir: pinta hasta n resultados NUMERADOS en el INICIO
    del widget…"». Nine of the seventeen confirming actions in the catalog had no `confirm_q` at all, so
    that fallback was the NORMAL path, not the rare one. A rule each widget author has to remember is not a
    rule: the gate enforces it, and `confirm_gate` keeps its desc branch as the last resort for a widget
    that never came through here.

    It also refuses the contradiction `view` + `confirm`: a view action changes only what is displayed and
    writes nothing to undo, so asking about one is a manifest that disagrees with itself.
    """
    from widgets import actions as _wa
    bare, both = [], []
    for name, spec in (man.get("actions") or {}).items():
        if not isinstance(spec, dict):
            continue
        if spec.get("view") is True and (spec.get("confirm") is True or spec.get("irreversible") is True):
            both.append(str(name))
        if _wa.classify(spec, str(name)) == _wa.CONFIRM and not str(spec.get("confirm_q") or "").strip():
            bare.append(str(name))
    if both:
        return (f"action(s) {sorted(both)} declare BOTH 'view' and 'confirm' — a view action only changes what "
                f"is displayed and writes nothing to undo, so it can never be irreversible; drop one")
    if bare:
        return (f"action(s) {sorted(bare)} ask the operator for a yes/no but declare no 'confirm_q' — add the "
                f"SENTENCE he hears ('¿Borro «{{item}}»? Es permanente.'); 'desc' is written for the model and "
                f"reading it aloud is what V2-665 fixed")
    return None
