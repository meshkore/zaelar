"""nucleo/flash/frontend.py — gestor de frontend/widgets del FlashBrain (V2-004 · T62).

Traduce las decisiones de la capa refleja al protocolo de tags que ya entiende el frontend
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

_ALLOWED_WHERE = {"izquierda", "derecha", "centro", "arriba", "abajo",
                  "left", "right", "center", "top", "bottom"}


def show(widget_id: str) -> str:
    """Tag para abrir un widget en el canvas."""
    return f"[[show:{(widget_id or '').strip().lower()}]]"


def close(widget_id: str | None = None) -> str:
    """Tag para cerrar un widget (o TODOS si `widget_id` es vacío)."""
    wid = (widget_id or "").strip().lower()
    return f"[[close:{wid}]]" if wid else "[[close]]"


def move(widget_id: str, where: str) -> str:
    """Tag para reposicionar un widget. `where` debe ser una dirección conocida, si no se ignora (cadena vacía)."""
    wid = (widget_id or "").strip().lower()
    w = (where or "").strip().lower()
    if not wid or w not in _ALLOWED_WHERE:
        return ""
    return f"[[move:{wid}:{w}]]"


# Verbos de CANVAS que el modelo pequeño a veces cuela como "acción" de `widget_data` en sesiones largas
# (diag 2026-07-15: `widget_data(widget_id="clock", action="show")` ante "muéstrame un reloj"). NO son data-ops:
# son la frontera CANVAS vs DATOS (V2-027). Solo aplican cuando la acción NO está declarada en el manifest (una
# acción declarada que se llame "show" es del widget y manda). es/en, acento-insensible.
_CANVAS_SHOW = {"show", "open", "display", "view", "reveal", "unhide", "mostrar", "abrir", "abre", "muestra",
                "ensenar", "ensena", "ver"}
_CANVAS_CLOSE = {"close", "hide", "cerrar", "cierra", "ocultar", "oculta", "esconder"}


def canvas_verb(action: str) -> str | None:
    """Si `action` es un VERBO DE CANVAS (mostrar/cerrar la tarjeta) y no una data-op, devuelve la tag canónica
    ('show'|'close'); None si no lo es. Compartido por la voz (`providers/nucleo.py`) y el probe (misma
    semántica en ambos canales). El llamante debe comprobar ANTES que la acción NO está declarada en el manifest."""
    import unicodedata
    a = "".join(c for c in unicodedata.normalize("NFKD", (action or "").strip().lower())
                if not unicodedata.combining(c))
    if a in _CANVAS_SHOW:
        return "show"
    if a in _CANVAS_CLOSE:
        return "close"
    return None


def action_mode(widget_id: str, action: str) -> str | None:
    """Modo de ejecución de una acción de widget: `FAST` (la capa rápida la hace ya), `CONFIRM` (la hace pero
    pide OK antes, irreversible) o `ESCALATE` (vía de escape explícita al SlowBrain). Devuelve **None** si la
    acción NO está DECLARADA en el manifest (el modelo se la inventó → el llamante decide, hoy: escalar).
    Consulta el catálogo cacheado (`widgets/runtime.py`) — sin I/O por llamada. La semántica vive en
    `widgets/actions.py`; cualquier error cae a None (fail-safe)."""
    try:
        from widgets import actions, runtime
        wid = (widget_id or "").strip().lower()
        name = (action or "").strip()
        if not wid or not name:
            return None
        declared = (runtime.get(wid) or {}).get("actions") or {}
        if name not in declared:
            return None
        return actions.classify(declared.get(name), name)
    except Exception as e:  # noqa: BLE001
        # Hallazgo maratón de testing 2026-07-22: `add_meeting` en `agenda` escalaba de forma INTERMITENTE
        # (~1 de cada 4-5 llamadas idénticas) en vivo, pero resolvía bien en aislado — sospecha de una excepción
        # transitoria tragada en silencio por este except, disfrazada de "acción no declarada" (→ escala). Antes
        # NO había ninguna traza; con esto, la próxima vez que ocurra queda en el timeline/log en vez de invisible.
        try:
            import logging
            logging.getLogger("zaelar.widgets").warning(
                "action_mode(%r, %r) reventó, fail-safe a None (→ posible escalada espuria): %s", widget_id, action, e)
        except Exception:
            pass
        return None


def is_safe_action(widget_id: str, action: str) -> bool:
    """Compat: True si la acción es una data-op que la capa rápida ejecuta SIN confirmación (modo `FAST`). Se
    conserva para llamantes/tests antiguos; el gate real usa `action_mode` para distinguir FAST/CONFIRM/ESCALATE."""
    try:
        from widgets import actions
        return action_mode(widget_id, action) == actions.FAST
    except Exception:
        return False


def widget_action_tag(widget_id: str, action: str, payload: dict | None = None) -> str | None:
    """Compone `[[widget.data:ID]]{...}[[/widget.data]]` para una data-op DECLARADA (modo FAST o CONFIRM). Devuelve
    None si la acción no está declarada o es una vía de escape a código (ESCALATE). El mismo `apply_action` lo
    aplica el despacho del canvas."""
    from widgets import actions
    mode = action_mode(widget_id, action)
    if mode not in (actions.FAST, actions.CONFIRM):
        return None
    import json
    body = {"action": (action or "").strip(), "payload": payload or {}}
    wid = (widget_id or "").strip().lower()
    return f"[[widget.data:{wid}]]{json.dumps(body, ensure_ascii=False)}[[/widget.data]]"


def identify(text: str) -> str | None:
    """Best-effort: id del widget al que se refiere una frase (delegado en `widgets/runtime.py`). None si nada
    casa. Sirve al safety-net del provider (el modelo dijo "abre X" sin emitir la tag)."""
    try:
        from widgets import runtime
        return (runtime.identify(text) or {}).get("match")
    except Exception:
        return None
