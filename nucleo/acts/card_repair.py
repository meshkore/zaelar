"""A declared ACTION the model got wrong, repaired from what he said: the action his words name instead, or the
sibling card that holds the content.
Moved from `nucleo/flash/frontend.py` (refactor2710-05 T-05); its names are read through `_fe`."""
from __future__ import annotations

from nucleo.flash import frontend as _fe


def repair_action(widget_id: str, invented_action: str, text: str,
                  *, timeout_s: float | None = None) -> str | None:
    """Jev Choice over the widget's DECLARED actions (+ `none`) for an action name the model
    invented (T-jev-action). Returns the declared winner, else None — `none`, unsure, slow,
    failed, disabled, or unknown widget all keep today's path (escalate).

    The winner must be a criteria key, so an invented name can never come back: `_parse`
    constrains the verdict to the keys enumerated here. Fires ONLY on the invented-action
    path, never per turn, so the common path pays no latency."""
    from nucleo import jev as _jev
    declared = _fe.declared_actions(widget_id)
    if not declared or not _jev.enabled():
        return None
    criteria = {name: str((spec if isinstance(spec, dict) else {}).get("desc") or name)[:160]
                for name, spec in declared.items()}
    criteria["none"] = "none of the declared actions matches what the user asked"
    verdict = _jev.choose_sync(
        "widget_action", text, instructions=_fe.ACTION_INSTRUCTIONS, criteria=criteria,
        context=f"widget {(widget_id or '').strip().lower()}; "
                f"the assistant guessed undeclared action {(invented_action or '').strip()!r}",
        timeout_s=timeout_s, question_id="widget-action")
    if not verdict:
        return None
    choice = str(verdict.get("choice") or "")
    if not choice or choice == "none" or choice not in declared:
        return None
    if float(verdict.get("confidence") or 0.0) < _jev.MIN_CONFIDENCE:
        return None
    return choice


def repair_action_from_brief(widget_id: str, brief) -> str | None:
    """The invented-action repair READ from the turn's brief (V2-726 F2) — no socket, no wait.

    The brief's `screen_action` question is already enumerated over the declared actions of every
    OPEN widget, keyed `widget:action`, so a verdict for THIS widget is exactly the repair that
    `repair_action` below opens its own blocking call to get. Returns the declared action name, or
    None for anything else: a verdict about another open card, `none`, unsure, or no brief at all.
    """
    from nucleo.flash import turn_brief as _tb
    choice, _info = _tb.read(brief, _tb.TARGET_KEY, "")
    wid = (widget_id or "").strip().lower()
    if not choice or ":" not in str(choice):
        return None
    # Key is `<instance>:<action>` (V2-726 A4); the ACTION follows the LAST colon (`results::t7:open_row`) —
    # the first one made «results» own «:t7:open_row».
    owner, _, name = str(choice).rpartition(":")
    if not owner or not name:
        return None
    if owner != wid and _tb._base_of(owner) != wid:
        return None                      # the order was aimed at ANOTHER open card: not a repair
    if not _tb.owner_still_open(brief, owner):
        return None                      # it was open when we asked and is not now: a stale verdict
    # Actions are declared by the BASE widget: `results::t7` has no manifest, so a verbatim id check said
    # «declares nothing» for every instance — the half A4 exists to reach.
    return name if name in (_fe.declared_actions(_tb._base_of(wid)) or {}) else None


#: The screen-verdict confidence needed to move an order to another card; below it is «I do not know» (ASK).
def _the_sibling_with_content(base: str, open_ids) -> str:
    """The one open instance of `base` that has something on it, when the bare `base` card is blank — else "".
    Reads the open set from the canvas report when none is handed in. Never raises."""
    try:
        from widgets import instances as _inst
        ids = list(open_ids or ())
        if not ids:
            from memory import api as _memapi
            ids = list(((_memapi.state() or {}).get("open_widgets") or []))
        sibs = [w for w in _inst.instances_of(base, ids) if "::" in str(w)]
        if not sibs:
            return ""

        def _blank(w: str) -> bool:
            if _inst.card_face(w).get("blank"):
                return True
            from nucleo import truth as _truth
            v = _truth.widget_view(w)
            return isinstance(v, dict) and v.get("empty") is True

        if not _blank(base):
            return ""                                   # the bare card has content of its own: no evidence
        live = [w for w in sibs if not _blank(w)]
        return live[0] if len(live) == 1 else ""
    except Exception:  # noqa: BLE001
        return ""
