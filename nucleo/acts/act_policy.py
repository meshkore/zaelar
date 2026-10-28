"""How much an act on a card may do on its own: its declared mode (view / safe / sensitive), his standing rule over
it, the verdict that licenses it.
Moved from `nucleo/flash/frontend.py` (refactor2710-05 T-05); its names are read through `_fe`."""
from __future__ import annotations

from nucleo.flash import frontend as _fe


def action_mode(widget_id: str, action: str) -> str | None:
    """Modo de ejecución de una acción de widget: `FAST` (la capa rápida la hace ya), `CONFIRM` (la hace pero
    pide OK antes, irreversible) o `ESCALATE` (vía de escape explícita al SlowBrain). Devuelve **None** si la
    acción NO está DECLARADA en el manifest (el modelo se la inventó → el llamante decide, hoy: escalar).
    Consulta el catálogo cacheado (`widgets/runtime.py`) — sin I/O por llamada. La semántica vive en
    `widgets/actions.py`; cualquier error cae a None (fail-safe)."""
    try:
        from widgets import actions, runtime
        wid = (widget_id or "").split("::", 1)[0].strip().lower()   # the BASE declares; an instance is one card of it
        name = (action or "").strip()
        if not wid or not name:
            return None
        declared = (runtime.get(wid) or {}).get("actions") or {}
        if name not in declared:
            return None
        return actions.classify(declared.get(name), name)
    except Exception as e:  # noqa: BLE001
        # Testing marathon 2026-07-22: `add_meeting` escalated intermittently live (~1 in 4-5 identical calls);
        # suspected a transient exception swallowed here as «undeclared action». Now it leaves a trace.
        try:
            import logging
            logging.getLogger("zaelar.widgets").warning(
                "action_mode(%r, %r) reventó, fail-safe a None (→ posible escalada espuria): %s", widget_id, action, e)
        except Exception:
            pass
        return None


def declared_actions(widget_id: str) -> dict:
    """The widget's DECLARED manifest actions (name -> spec), {} when unknown.

    The same cached catalog `action_mode` reads, so a repair candidate can never be an
    invented action. Read-only; any error yields {} (fail-safe toward today's path)."""
    try:
        from widgets import runtime
        wid = (widget_id or "").split("::", 1)[0].strip().lower()   # the BASE declares; an instance is one card of it
        if not wid:
            return {}
        return dict((runtime.get(wid) or {}).get("actions") or {})
    except Exception:  # noqa: BLE001
        return {}


def action_verdict(widget_id: str, action: str, payload: dict | None = None, *, his_yes: bool = False) -> dict:
    """What the ONE consent rule says about running this data-op RIGHT NOW (V2-712).

    `action_mode` above answers «how much friction does this action carry», which is a property of the
    action and knows nothing about the call. This answers the question the operator actually asked for —
    «¿tengo la suficiente información como para ejecutar la tarea con garantías?» — and to do that it needs
    the CALL: which item, whether the selector arrived filled, which facts the action declares it needs.

    Everything it reads is DECLARED data: the widget's `security` (all shipped widgets: standard), the
    action's `sensitivity` (or today's `confirm:true`, read as `sensitive`), its `requires` list and its
    `consent_class`. No verb is matched anywhere in this path.

    Fails toward the OLD behaviour: anything unreadable returns the verdict the manifest flag alone would
    have produced, so a malformed widget loses the improvement rather than the guard.
    """
    from nucleo import consent
    from widgets import actions as _wa, runtime
    wid, name = (widget_id or "").strip().lower(), (action or "").strip()
    man = runtime.get(wid) or {}
    spec = (man.get("actions") or {}).get(name)
    spec = spec if isinstance(spec, dict) else {}
    level = consent.level_of(spec, widget_security=str(man.get("security") or ""), action=name)
    bounded, radius = _fe._scope(wid, name, spec, payload)
    return consent.decide(level=level, missing=consent.missing_facts(spec.get("requires")),
                          radius=radius, bounded=bounded,
                          policy_key=_fe._policy_key(wid, name, spec, payload), his_yes=his_yes,
                          scope={"widget": wid, "action": name})


def _policy_key(wid: str, name: str, spec: dict, payload: dict | None) -> str:
    """Which consent CLASS this call belongs to, letting the widget refine its own manifest (V2-718).

    The manifest names the class an action belongs to IN THE ABSTRACT, and for most actions that is the
    whole truth. For some it is not, and the operator said exactly where the line falls:

    > «Esto por ejemplo que no nos hace ningún daño no necesita permiso. Añadir a otra persona, cambiar de
    > hora o hacer otras cosas sí que obviamente necesitan permiso.»

    That distinction cannot be read from the action's name, from its payload keys, or from the words of the
    request: it is whether THIS call stays inside a commitment already made with the people already in it.
    Only the widget holds the data to answer — its own guest list, its own roster — so a widget's data
    module may expose `consent_scope(action, payload, db) -> {"class": ...}` and say so. It REFINES, never
    invents: a widget that does not offer the hook, or whose hook raises, keeps the manifest's own class,
    which is the behaviour every action had before this seam existed.

    ⚠️ Which way the manifest leans decides what the hook can do. A class DECLARED there is the floor the
    hook cannot lower — `_policy_key` falls back to it — so an action that is free by default and asks only
    in some calls (moving an hour: free when only he holds it) must declare NO class and let the hook add
    one. Measured 2026-09-17: `move_meeting` declared the «ask» class and every move asked, his dentist
    included, while its test checked the hook's answer and never the verdict.
    """
    declared = str((spec or {}).get("consent_class") or "")
    try:
        import importlib
        mod = importlib.import_module(f"widgets.{wid}.data")
        hook = getattr(mod, "consent_scope", None)
        if not callable(hook):
            return declared
        out = hook(name, dict(payload or {}))
        key = str((out or {}).get("class") or "").strip()
        return key or declared
    except Exception:  # noqa: BLE001
        return declared


def _declared_radius(wid: str, name: str, payload: dict | None) -> int | None:
    """What the widget says this call will touch, or None (V2-720). Same shape as `_policy_key`'s hook."""
    try:
        import importlib
        hook = getattr(importlib.import_module(f"widgets.{wid}.data"), "radius", None)
        if not callable(hook):
            return None
        n = hook(name, dict(payload or {}))
        return int(n) if isinstance(n, int) and not isinstance(n, bool) and n >= 0 else None
    except Exception:  # noqa: BLE001
        return None


def _scope(wid: str, name: str, spec: dict, payload: dict | None) -> tuple[bool, int | None]:
    """Does this call NAME what it acts on, and how many things will it touch?

    The V2-707 rail in its general form. `contract.selector_for` already owns the «which key names the item»
    question (including the aliases a model spells its own way and the selectors a manifest itself calls
    optional), so this reuses it rather than growing a second opinion about the same manifest — the V2-708
    defect, one layer down, was exactly two layers disagreeing about whether a selector was optional.

    An action that declares NO selector at all is a whole-wipe (`clear_all`, `dedupe_meetings`): unbounded by
    construction, which is what keeps «vacía la agenda» asking.
    """
    try:
        from widgets import contract as _contract
        # THE WIDGET MAY COUNT ITS OWN ROWS (V2-720). The CALL measures nothing for a WINDOW selector: «clear today»
        # (`clear_range`, selector `from`) read as «one thing» and ran `fast` over `confirm:true` (2026-09-17).
        # A widget may give `radius(action, payload) -> int | None`; like `consent_scope` it REFINES (None = as before).
        n = _fe._declared_radius(wid, name, payload)
        if n is not None:
            # ZERO IS NOT «ONE NAMED THING» (V2-726 A4 T0): `n <= 1` folded one row with an empty widget, so
            # «vacía la agenda» came back FAST in the empty sandbox. A no-op that asks costs a question; a sweep
            # that doesn't is the incident: an empty count refines NOTHING and falls to `confirm: true` below.
            if n > 0:
                return (n <= 1, n)
        # An action may DECLARE that one selector fans out (`agenda:drop_project`: ONE project, all its tasks).
        if spec.get("fans_out") is True:
            return False, None
        # …and the mirror: no selector because there is ONE target (`musica:disconnect`) vs every one
        # (`agenda:clear_all`) — the manifest says which, rather than «no selector» = «unbounded».
        if spec.get("singleton") is True:
            return True, 1
        field = _contract.selector_for(wid, name, spec)
        if not field:
            return (not _contract.is_destructive(spec, name), None)
        folded = _contract.fold_aliases(wid, name, payload) or {}
        val = folded.get(field, (payload or {}).get(field))
        if isinstance(val, (list, tuple, set)):
            return (len(val) > 0, len(val))
        return (str(val or "").strip() != "", 1 if str(val or "").strip() else None)
    except Exception:  # noqa: BLE001
        return True, 1


def action_mode_now(widget_id: str, action: str, payload: dict | None = None) -> str | None:
    """`action_mode`, but decided for THIS call instead of for the action in the abstract (V2-712).

    The one seam the voice provider calls. A declared action whose target resolved to one thing, with the
    data to act and nothing sensitive about its class, comes back `FAST` — it runs, with no second question
    after the one `refs.resolve` already asked. Everything else comes back exactly what it came back before.

    `ESCALATE` and «not declared» are untouched: this decides friction, never whether something is code work.
    """
    from nucleo import consent
    from widgets import actions as _wa
    mode = _fe.action_mode(widget_id, action)
    if mode == _wa.FAST and _fe._his_rule_holds(widget_id, action, payload):
        return _wa.CONFIRM
    if mode != _wa.CONFIRM:
        return mode
    try:
        return _wa.CONFIRM if consent.asks(_fe.action_verdict(widget_id, action, payload)) else _wa.FAST
    except Exception:  # noqa: BLE001 — an unreadable verdict keeps the friction it had
        return _wa.CONFIRM


def _his_rule_holds(widget_id: str, action: str, payload: dict | None) -> bool:
    """An act that LEAVES (`external.send`) and runs FAST by its manifest still reads his standing rule for its
    class and channel (V2-805): «pregúntame antes de mandar correos» reaches `send_to` too. Only HIS rule is read
    here — the radius and the class defaults keep the friction the manifest gave, so no default moves."""
    try:
        from nucleo import consent
        from widgets import effects as _fx
        if not _fx.carries(widget_id, action, _fx.EXTERNAL_SEND):
            return False
        wid, name = (widget_id or "").split("::", 1)[0].strip().lower(), (action or "").strip()
        from widgets import runtime
        spec = ((runtime.get(wid) or {}).get("actions") or {}).get(name)
        key = _fe._policy_key(wid, name, spec if isinstance(spec, dict) else {}, payload)
        return consent.class_policy(key, {"widget": wid, "action": name}) in ("ask", "never")
    except Exception as e:  # noqa: BLE001 — unreadable: the manifest's friction stands, as before
        from loguru import logger
        logger.info(f"frontend: his rule unreadable for {widget_id}:{action} ({e})")
        return False


def at_least_sensitive(widget_id: str, action: str) -> bool:
    """Is this action's declared consent level `sensitive` or above (a message that leaves, a payment…)?

    …or does it declare `external.send`: a message to a person that the operator deliberately runs without a
    question (V2-692) still LEAVES, and the gate this feeds only ever adds friction (demo pass 2026-09-28, full19
    C2-C3: two Telegrams to Rowan nobody asked for, over a verdict that read the turn as a question to the agenda)."""
    try:
        from widgets import effects as _fx
        if _fx.carries(widget_id, action, _fx.EXTERNAL_SEND):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        from nucleo import consent
        from widgets import runtime
        wid = (widget_id or "").split("::", 1)[0].strip().lower()
        man = runtime.get(wid) or {}
        spec = (man.get("actions") or {}).get((action or "").strip())
        spec = spec if isinstance(spec, dict) else {}
        lvl = consent.level_of(spec, widget_security=str(man.get("security") or ""), action=action)
        return consent.LEVELS.index(lvl) >= consent.LEVELS.index("sensitive")
    except Exception:  # noqa: BLE001 — unreadable: treat as sensitive, the guard it feeds only ever adds friction
        return True


def action_is_view(widget_id: str, action: str) -> bool:
    """True if the action is DECLARED by that widget and only changes what is DISPLAYED (V2-545).

    The catalog-side half of the pure-show rule: a «muéstrame/ábreme X» may drive a widget's own view (switch a
    lens, open an element, go back to its list) but never a mutation the model invented. The semantics live in
    `widgets/actions.py::is_view`; this is the cached-catalog lookup, shared by the voice provider and the probe
    exactly like `action_mode`. Fails CLOSED (False = only show the card) on anything it cannot read."""
    try:
        from widgets import actions, runtime
        wid = (widget_id or "").split("::", 1)[0].strip().lower()   # the BASE declares; an instance is one card of it
        name = (action or "").strip()
        if not wid or not name:
            return False
        declared = (runtime.get(wid) or {}).get("actions") or {}
        if name not in declared:
            return False
        return actions.is_view(declared.get(name), name)
    except Exception:  # noqa: BLE001
        return False


def is_safe_action(widget_id: str, action: str) -> bool:
    """Compat: True si la acción es una data-op que la capa rápida ejecuta SIN confirmación (modo `FAST`). Se
    conserva para llamantes/tests antiguos; el gate real usa `action_mode` para distinguir FAST/CONFIRM/ESCALATE."""
    try:
        from widgets import actions
        return _fe.action_mode(widget_id, action) == actions.FAST
    except Exception:
        return False
