"""nucleo/actionmap/executor.py — the CLOSED allowlist of fast-safe direct actions (V2-539).

A matched entry executes through the SAME dispatch seams the FlashBrain's own output uses (the `widget`/
`panel` observer events the frontend already consumes) — never a parallel executor. The vocabulary is
closed and idempotent/reversible by construction: show, close, close-all, panel open/close, move,
fullscreen, and FAST-classified widget data-ops. Anything destructive, content-carrying or credential-
adjacent is not representable here, no matter what a row in the table says: `validate()` refuses it at
load time, loudly (the "a module can be born dead" lesson — a bad seed must alert, not vanish).

Named multi-step WORKFLOWS are deliberately NOT an action kind (V2-539 §7, future scope).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("zaelar.actionmap")

# do → required string fields beyond "do". Kept flat on purpose: the matcher treats `action` as opaque
# JSON; this table is the single place that says what may run.
_ALLOWED: dict[str, tuple[str, ...]] = {
    "show_widget": ("widget",),
    "close_widget": ("widget",),
    "close_all": (),
    "show_panel": ("tab",),      # optional "action": open|close (default open)
    "move": ("widget", "where"),
    "fullscreen": ("widget",),
    "widget_data": ("widget", "action"),   # FAST-classified declared ops only, checked at execute
}

_PANEL_TABS = ("chat", "procesos", "crons", "clusters")
_MOVE_WHERE = ("left", "right", "center", "top", "bottom")


def validate(action: dict) -> str:
    """'' if the action is executable, else the reason it is not. Pure — no I/O, safe at import time."""
    if not isinstance(action, dict):
        return "action is not an object"
    do = action.get("do")
    if do not in _ALLOWED:
        return f"unknown do: {do!r}"
    for field in _ALLOWED[do]:
        if not str(action.get(field) or "").strip():
            return f"{do}: missing {field}"
    if do == "show_panel":
        if action.get("tab") not in _PANEL_TABS:
            return f"show_panel: unknown tab {action.get('tab')!r}"
        if action.get("action", "open") not in ("open", "close"):
            return f"show_panel: bad action {action.get('action')!r}"
    if do == "move" and action.get("where") not in _MOVE_WHERE:
        return f"move: bad where {action.get('where')!r}"
    return ""


def _resolve_widget(name: str) -> str:
    """Stored name → live widget id, through the ONE resolver the rest of the brain uses (V2-082).
    A known id passes through; otherwise name/alias resolution — and NO fuzzy fallback: an entry whose
    target cannot be resolved with certainty does not execute (the turn falls through to the model)."""
    wid = (name or "").strip().lower()
    try:
        from widgets import runtime as _rt
        if _rt.get(wid) is not None:
            return wid
        hit = _rt.identify(wid)
        return hit.get("match") or ""
    except Exception:
        return ""


def describe(action: dict) -> str:
    """Short probe/report string, mirroring `nucleo/flash/probe.py` action naming."""
    do = action.get("do")
    if do == "close_all":
        return "canvas:close"
    if do == "close_widget":
        return f"canvas:close:{action.get('widget')}"
    if do == "show_widget":
        return f"canvas:show:{action.get('widget')}"
    if do == "show_panel":
        return f"panel:{action.get('tab')}"
    if do == "widget_data":
        return f"widget_data:{action.get('widget')}:{action.get('action')}"
    return f"canvas:{do}:{action.get('widget')}"


def execute(action: dict, emit, phrase: str = "") -> bool:
    """Run one allowlisted action through the shared emit funnel. True = executed; False = could not
    (unresolved target, undeclared data-op…) — the caller MUST then fall through to the model, so a
    False here is a routing decision, never an error."""
    if validate(action):
        return False
    do = action["do"]
    # `src` marks provenance and the PHRASE travels with every canvas order — operator rule (2026-08-09):
    # when the wrong widget opens, the first question is always «what text produced this?», and an event
    # without its phrase forces a jump to the neighbouring transcript row to answer it. The model's own
    # orders already carry it (`_tag_emit` in the provider); the map's close/move/fullscreen used to drop it.
    said = (phrase or "")[:160]
    src = {"src": "actionmap", "origin": "actionmap"}
    if do == "close_all":
        emit("widget", "close", text=said, extra=dict(src))
        return True
    if do == "show_panel":
        emit("panel", action.get("action", "open"), text=said, extra={"tab": action["tab"], **src})
        return True
    wid = _resolve_widget(action["widget"])
    if not wid:
        return False
    if do == "show_widget":
        emit("widget", "show", text=said, extra={"id": wid, **src})
        return True
    if do == "close_widget":
        emit("widget", "close", text=said, extra={"id": wid, **src})
        return True
    if do == "move":
        emit("widget", "move", text=said, extra={"id": wid, "where": action["where"], **src})
        return True
    if do == "fullscreen":
        emit("widget", "fullscreen", text=said, extra={"id": wid, **src})
        return True
    if do == "widget_data":
        # Only ops the widget DECLARES as FAST run without the model; everything else falls through.
        # `brain_action` is async and never raises (same funnel as the UI buttons); we schedule it on the
        # running loop — no loop means no live session to act on, so the turn falls through to the model.
        try:
            import asyncio

            from nucleo.flash.frontend import action_is_view, action_mode
            from widgets import server_api as _sapi
            if str(action_mode(wid, action["action"]) or "").lower() != "fast":
                return False
            loop = asyncio.get_running_loop()   # BEFORE any emit: no loop = no live session to act on, and
            #                                     this must fall through WHOLE, not half-executed.
            # A VIEW op brings the card up as well — the same rule the voice rail applies (V2-545). «Ábreme el
            # WhatsApp» is one order with two halves: the card in front and that lens selected. Applying the
            # lens to a card nobody can see would be the mirror of the bug this replaces (a card shown with
            # the lens ignored).
            if action_is_view(wid, action["action"]):
                emit("widget", "show", text=said, extra={"id": wid, **src})
            loop.create_task(_sapi.brain_action(wid, action["action"], dict(action.get("payload") or {})))
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning(f"actionmap widget_data failed ({wid}:{action['action']}): {e!r}")
            return False
    return False
