"""nucleo/worker_policy.py — the pure ALLOW/CONFIRM/DENY policy for Brain Worker requests (split out of
worker_api.py, 2026-08-17 modularization pass). This is the decision logic only: given an action + payload,
what's allowed, what needs confirmation, what's denied, and why (in terms the worker can act on). No I/O, no
FastAPI, no asyncio — everything here is independently unit-testable without the request/response plumbing
that stays in worker_api.py (which re-exports these names; existing callers, including tests that do
`from nucleo.worker_api import deny_reason, _PRESTABLE_TOOLS`, needed no changes)."""
from __future__ import annotations

# ── policy by action (§v3·J) ────────────────────────────────────────────────────────────────────────────────
ALLOW, CONFIRM, DENY = "allow", "confirm", "deny"
# FlashBrain tools AVAILABLE TO LEND to workers (FILTERED catalog, not all of router.TOOLS — anti prompt-injection
# from hostile web content, §v3·B/J). Grows only with an explicit designation, never by accident.
_PRESTABLE_TOOLS = {"web_search"}
# Never available to lend (operator-only by semantics).
_DENY_TOOLS = {"authenticate_web", "login_done", "confirm_widget_delete", "set_style_directive", "delete_widget",
               "restore_widget"}

# Actions understood by the request/response layer. Declared HERE, next to the policy, so the denial message
# cannot become out of date with respect to what `classify_act` actually accepts.
_KNOWN_ACTS = ("ask_user", "use_tool", "read_widget", "show_widget", "close_widget", "widget_data",
               "spawn", "push_channel", "schedule")

def deny_reason(action: str, payload: dict) -> str:
    """Why the request is denied, IN TERMS THE WORKER CAN CORRECT.

    It stems from a failure observed live (2026-08-12, sailboat search): with the provider's search quota
    exhausted, the worker tried to borrow the brain's `web_search` —which IS available to lend— but requested it in
    the wrong form: `act web_search {"query":…}` instead of `act use_tool {"tool":"web_search","args":{…}}`.
    `classify_act` fell into its unknown-action branch and always returned the SAME phrase, «action not permitted
    for a worker». The worker read it as literally stated —that this capability is not permitted to a worker— and
    ABANDONED its only fallback route («the bridge's web_search action is not permitted for workers»), leaving the
    search without a search engine. A MALFORMED CALL and a FORBIDDEN capability cannot produce the same error: the
    first is fixed by retrying correctly, the second is not, and confusing them costs the entire task."""
    a = (action or "").strip()
    if a not in _KNOWN_ACTS:
        hint = ""
        if a in _PRESTABLE_TOOLS or a in _DENY_TOOLS:
            # the exact incident case: supplied the TOOL NAME where the ACTION belongs
            hint = (f' — «{a}» es una TOOL, no una acción: pídela con use_tool, '
                    f'p.ej. act use_tool {{"tool":"{a}","args":{{…}}}}')
        return (f"acción DESCONOCIDA «{a}»{hint}. Acciones válidas: {', '.join(_KNOWN_ACTS)}. "
                f"Esto NO es una prohibición: es una llamada mal formada, corrígela y reintenta.")
    if a == "use_tool":
        tool = str((payload or {}).get("tool") or "")
        if tool in _DENY_TOOLS:
            return (f"la tool «{tool}» no se presta a un worker (es del operador). No insistas por esta vía; "
                    f"si necesitas que él decida, usa ask_user.")
        return (f"la tool «{tool}» no está en el catálogo prestable. Prestables: "
                f"{', '.join(sorted(_PRESTABLE_TOOLS))}.")
    if a == "widget_data":
        return ("data-op no permitida: o la acción no está DECLARADA en el manifest de ese widget, o el widget no "
                "existe. LEE el widget primero (read_widget) y usa una de sus acciones declaradas.")
    return "acción no permitida para un worker"


def classify_act(action: str, payload: dict) -> str:
    a = (action or "").strip()
    if a == "ask_user":
        return ALLOW
    if a == "use_tool":
        tool = (payload or {}).get("tool", "")
        if tool in _DENY_TOOLS:
            return DENY
        return ALLOW if tool in _PRESTABLE_TOOLS else DENY
    if a in ("read_widget", "show_widget", "close_widget"):
        return ALLOW
    if a == "widget_data":
        # V2-061: DATA-OP on a widget (reflect in the local MIRROR what happened in reality — e.g. remove from the
        # agenda an appointment already canceled on the web). The gate is the CANONICAL CATALOG (widgets/actions.py
        # via frontend.action_mode), the SAME one as FlashBrain: FAST→ALLOW, CONFIRM(irreversible)→CONFIRM.
        # ESCALATE/None (undeclared action) → DENY: a worker does not escalate a data-op or invent actions — have it
        # READ the widget first.
        try:
            from nucleo.flash.frontend import action_mode
            from widgets import actions as _wa
            m = action_mode(str((payload or {}).get("widget_id") or (payload or {}).get("id") or ""),
                            str((payload or {}).get("action") or ""))
        except Exception:
            m = None
        if m == _wa.FAST:
            return ALLOW
        if m == _wa.CONFIRM:
            return CONFIRM
        return DENY
    if a == "spawn":
        return ALLOW           # la cuota/profundidad se comprueba aparte
    if a == "push_channel":
        return CONFIRM
    if a == "schedule":
        # V2-249 — SCHEDULE A REMINDER. A worker tasked with «remind them on Wednesday» could not do it: the
        # capability did not exist, and it would SAY that it had done so and write it durably to memory (the
        # «self-scoring pill» that the harness has been measuring over several rounds). It was a gap, not a pending
        # decision: a Brain Worker already operates widgets, drives the browser, and writes to memory — this
        # system's security is a FILTER, not a short permission list.
        #
        # ALLOW rather than CONFIRM, for comparison with its neighbors: `push_channel` asks because it goes
        # OUTWARD and cannot be undone; a scheduled reminder is internal, visible in its panel, and canceled with
        # one gesture. Its filter is the one used by `spawn`: grant the capability and enforce the LIMIT when it is
        # executed (per-task cap, `schedule` must parse, and the reminder remains attributed to whoever created it).
        return ALLOW
    return DENY                # unknown → deny (fail-safe)


def _confirm_question(action: str, payload: dict) -> str:
    if action == "push_channel":
        ch = (payload or {}).get("channel", "")
        return f"El worker quiere enviar algo al canal «{ch}». ¿Lo hago?"
    if action == "widget_data":
        wid = (payload or {}).get("widget_id") or (payload or {}).get("id") or ""
        act = (payload or {}).get("action") or ""
        return f"El worker quiere hacer «{act}» en el widget «{wid}» (acción irreversible). ¿Lo autorizas?"
    return f"El worker quiere ejecutar «{action}». ¿Lo autorizas?"
