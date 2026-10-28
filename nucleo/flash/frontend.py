"""nucleo/flash/frontend.py — FlashBrain frontend/widget manager (V2-004 · T62).

Translates reflective-layer decisions into the tag protocol already understood by the frontend
(`voice/tag_protocol.py`): `[[show:<id>]]`, `[[close:<id>]]` / `[[close]]`, `[[move:<id>:<where>]]`. El modelo
rápido emite estas tags como texto; `voice.tag_protocol.strip_tags` las saca de la voz y las despacha al canvas
(el provider `nucleo.py` es quien conecta el `emit`). Aquí viven los helpers que COMPONEN esas tags y, sobre
todo, el **gate de gobernanza de widgets** (V2-025): TODA acción DECLARADA en el `manifest.json` es una data-op
que la capa rápida ejecuta ELLA MISMA (nunca se escala a un agente de código — ese era el bug de `add_meeting`
`safe:false`). Lo único que se separa es si la acción es IRREVERSIBLE (→ confirmación, `widgets/confirm.py`) o
no. La semántica canónica (FAST/CONFIRM/ESCALATE) vive en `widgets/actions.py`; aquí solo se consulta el catálogo
cacheado. El refresco de datos sigue por `widgets/store.save()` → SSE.
"""
from __future__ import annotations

from loguru import logger

_ALLOWED_WHERE = {"izquierda", "derecha", "centro", "arriba", "abajo",
                  "left", "right", "center", "top", "bottom"}


def show(widget_id: str) -> str:
    """Tag for opening a widget on the canvas."""
    return f"[[show:{(widget_id or '').strip().lower()}]]"


def close(widget_id: str | None = None) -> str:
    """Tag for closing a widget (or ALL if `widget_id` is empty)."""
    wid = (widget_id or "").strip().lower()
    return f"[[close:{wid}]]" if wid else "[[close]]"


def move(widget_id: str, where: str) -> str:
    """Tag for repositioning a widget. `where` must be a known direction; otherwise it is ignored (empty string)."""
    wid = (widget_id or "").strip().lower()
    w = (where or "").strip().lower()
    if not wid or w not in _ALLOWED_WHERE:
        return ""
    return f"[[move:{wid}:{w}]]"


# CANVAS verbs the small model slips in as a `widget_data` action (diag 2026-07-15: clock, action="show").
# Not data-ops: the CANVAS vs DATA boundary (V2-027), only when NOT declared (a declared one wins). es/en.
_CANVAS_SHOW = {"show", "open", "display", "view", "reveal", "unhide", "mostrar", "abrir", "abre", "muestra",
                "ensenar", "ensena", "ver"}
_CANVAS_CLOSE = {"close", "hide", "cerrar", "cierra", "ocultar", "oculta", "esconder"}


def canvas_verb(action: str) -> str | None:
    """If `action` is a CANVAS VERB (show/close the card) rather than a data op, return the canonical tag
    ('show'|'close'); None otherwise. Shared by voice (`providers/nucleo.py`) and the probe (same
    semantics in both channels). The caller must check FIRST that the action is NOT declared in the manifest."""
    import unicodedata
    a = "".join(c for c in unicodedata.normalize("NFKD", (action or "").strip().lower())
                if not unicodedata.combining(c))
    if a in _CANVAS_SHOW:
        return "show"
    if a in _CANVAS_CLOSE:
        return "close"
    return None


ACTION_INSTRUCTIONS = (
    "Name the widget action the user wants. "
    "The assistant guessed an action the widget does not declare; "
    "pick the declared action the user's message means, or none."
)


def identify(text: str) -> str | None:
    """Best-effort: id del widget al que se refiere una frase (delegado en `widgets/runtime.py`). None si nada
    casa. Sirve al safety-net del provider (el modelo dijo "abre X" sin emitir la tag)."""
    try:
        from widgets import runtime
        return (runtime.identify(text) or {}).get("match")
    except Exception:
        return None

from nucleo.acts.card_repair import (  # noqa: E402,F401
    repair_action, repair_action_from_brief, _the_sibling_with_content)
from nucleo.acts.card_target import (  # noqa: E402,F401
    _takes, _screen_now, _players_floor, which_card, payload_ref, absent_widget_misroute, card_decision,
    resolve_undeclared_action)
from nucleo.acts.act_policy import (  # noqa: E402,F401
    action_mode, declared_actions, action_verdict, _policy_key, _declared_radius, _scope, action_mode_now,
    _his_rule_holds, at_least_sensitive, action_is_view, is_safe_action)
