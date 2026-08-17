"""nucleo/worker_policy.py — the pure ALLOW/CONFIRM/DENY policy for Brain Worker requests (split out of
worker_api.py, 2026-08-17 modularization pass). This is the decision logic only: given an action + payload,
what's allowed, what needs confirmation, what's denied, and why (in terms the worker can act on). No I/O, no
FastAPI, no asyncio — everything here is independently unit-testable without the request/response plumbing
that stays in worker_api.py (which re-exports these names; existing callers, including tests that do
`from nucleo.worker_api import deny_reason, _PRESTABLE_TOOLS`, needed no changes)."""
from __future__ import annotations

# ── política por acción (§v3·J) ────────────────────────────────────────────────────────────────────────────
ALLOW, CONFIRM, DENY = "allow", "confirm", "deny"
# Tools del FlashBrain PRESTABLES a los workers (catálogo FILTRADO, no todo router.TOOLS — anti prompt-injection
# desde contenido web hostil, §v3·B/J). Crece con marca explícita, nunca por accidente.
_PRESTABLE_TOOLS = {"web_search"}
# Nunca prestables (operator-only por semántica).
_DENY_TOOLS = {"authenticate_web", "login_done", "confirm_widget_delete", "set_style_directive", "delete_widget"}

# Acciones que el plano request/response entiende. Se declara AQUÍ, junto a la política, para que el mensaje de
# denegación no pueda quedarse desactualizado respecto a lo que `classify_act` admite de verdad.
_KNOWN_ACTS = ("ask_user", "use_tool", "read_widget", "show_widget", "close_widget", "widget_data",
               "spawn", "push_channel")

def deny_reason(action: str, payload: dict) -> str:
    """Por qué se deniega, EN TÉRMINOS QUE EL WORKER PUEDA CORREGIR.

    Nace de un fallo observado en vivo (2026-08-12, búsqueda de veleros): con la cuota del buscador de su proveedor
    agotada, el worker fue a pedir prestada la `web_search` del cerebro —que SÍ es prestable— pero la pidió con la
    forma equivocada: `act web_search {"query":…}` en vez de `act use_tool {"tool":"web_search","args":{…}}`.
    `classify_act` cayó en su rama de acción desconocida y devolvía siempre la MISMA frase, «acción no permitida
    para un worker». El worker la leyó como lo que literalmente decía —que esa capacidad no está permitida a un
    worker— y ABANDONÓ su única vía de reserva («la acción web_search del puente no está permitida para workers»),
    dejando la búsqueda sin buscador. Una llamada MAL ESCRITA y una capacidad PROHIBIDA no pueden dar el mismo
    error: la primera se arregla reintentando bien, la segunda no, y confundirlas cuesta la tarea entera."""
    a = (action or "").strip()
    if a not in _KNOWN_ACTS:
        hint = ""
        if a in _PRESTABLE_TOOLS or a in _DENY_TOOLS:
            # el caso exacto del incidente: pasó el NOMBRE DE LA TOOL donde va la ACCIÓN
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
        # V2-061: DATA-OP sobre un widget (reflejar en el ESPEJO local lo hecho en la realidad — p.ej. borrar de la
        # agenda una cita ya cancelada en la web). El gate es el CATÁLOGO CANÓNICO (widgets/actions.py vía
        # frontend.action_mode), MISMO que el FlashBrain: FAST→ALLOW, CONFIRM(irreversible)→CONFIRM. ESCALATE/None
        # (acción no declarada) → DENY: un worker no escala una data-op ni inventa acciones — que LEA el widget antes.
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
    return DENY                # desconocido → denegar (fail-safe)


def _confirm_question(action: str, payload: dict) -> str:
    if action == "push_channel":
        ch = (payload or {}).get("channel", "")
        return f"El worker quiere enviar algo al canal «{ch}». ¿Lo hago?"
    if action == "widget_data":
        wid = (payload or {}).get("widget_id") or (payload or {}).get("id") or ""
        act = (payload or {}).get("action") or ""
        return f"El worker quiere hacer «{act}» en el widget «{wid}» (acción irreversible). ¿Lo autorizas?"
    return f"El worker quiere ejecutar «{action}». ¿Lo autorizas?"
