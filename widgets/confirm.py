"""widgets/confirm.py — puerta de CONFIRMACIÓN para acciones IRREVERSIBLES de widget (V2-017 · V2-025).

Costura reutilizable para cualquier acción que exija OK explícito antes de ejecutarse. Antes de ejecutar, se
registra una confirmación PENDIENTE y se pinta un overlay «¿…? Sí / No» en la propia tarjeta del canvas (a nivel
del host, sirve para cualquier widget — no toca su `widget.js`). El operador confirma de dos formas, ambas
resuelven la MISMA pendiente:
  - **botón** de la tarjeta → `POST /widgets/{id}/confirm {ok}` → `resolve()`;
  - **voz** ("sí, bórralo" / "no, déjalo") → detección DETERMINISTA es/en en el provider (`classify_reply`),
    respaldada por una tool (`confirm_widget_delete`) que el modelo llama.
Sin "sí" (o pasado el TTL) NO se ejecuta nada. DOS clases de pendiente hoy:
  - **`delete`** — borrar el widget entero (V2-017); la ejecución la hace `lifecycle.delete_widget`.
  - **`data`** — una data-op IRREVERSIBLE marcada `confirm:true` en el manifest (V2-025, hermano de
    `nucleo/danger.py`): al confirmar, el provider DESPACHA la mutación (`op` = {action, payload}) por el MISMO
    `apply_action` — **sin escalar a código**. Ese es el punto: irreversible ≠ trabajo de código.

Registro en memoria de proceso (una confirmación por widget). El provider/endpoint hacen la EJECUCIÓN al
resolver (loop-agnóstico): `resolve()` es solo bookkeeping + señal SSE.
"""
from __future__ import annotations

import re
import time
import unicodedata

_PENDING: dict[str, dict] = {}     # widget_id -> {action, question, ts}
_TTL = 90.0                        # una confirmación caduca a los 90s (no se queda colgada para siempre)


def _emit(action: str, wid: str, extra: dict | None = None) -> None:
    try:
        from voice.observer import emit
        emit("widget", action, extra={"id": wid, **(extra or {})})
    except Exception:
        pass


def _sweep() -> None:
    now = time.time()
    for k in [k for k, v in _PENDING.items() if now - v["ts"] > _TTL]:
        _PENDING.pop(k, None)


# Id RESERVADO de una superficie NATIVA que también pide confirmación (V2-086). No es un widget del catálogo: es
# la pestaña «Clusters» del ChatWall. El almacén de este módulo siempre fue genérico (un dict por clave), así que
# reutilizarlo evita un segundo mecanismo de confirmación paralelo — lo único específico es dónde se PINTA el
# Sí/No (la pestaña, no una tarjeta) y quién lo RESUELVE (`/api/meshkore/confirm`, no `/widgets/{id}/confirm`).
NATIVE_CLUSTERS = "clusters"


def request(action: str, widget_id: str, question: str = "", op: dict | None = None) -> str | None:
    """Registra una confirmación pendiente para `widget_id` y pide el overlay en su tarjeta (SSE). Devuelve el id
    normalizado, o None si el id es inválido.

    `action` = la CLASE de confirmación: `"delete"` (borrar el widget) o `"data"` (una data-op irreversible).
    Para `"data"`, `op` lleva la mutación real ({"action": <nombre>, "payload": {...}}) que el que resuelve
    despachará por `apply_action` al confirmar — nunca se escala a código."""
    _sweep()
    wid = (widget_id or "").strip().lower()
    if not wid:
        return None
    _PENDING[wid] = {"action": (action or "delete").strip(), "question": (question or "").strip(),
                     "op": op if isinstance(op, dict) else None, "ts": time.time()}
    _emit("confirm", wid, {"action": _PENDING[wid]["action"], "question": _PENDING[wid]["question"]})
    return wid


def pending() -> dict[str, dict]:
    _sweep()
    return dict(_PENDING)


def pending_line() -> str:
    """Línea para el estado vivo del FlashBrain: hay una confirmación en el aire → el modelo debe interpretar el
    "sí/no" del operador como respuesta a ESO (y llamar a `confirm_widget_delete`), no como charla. Cubre tanto
    el borrado de un widget como una data-op irreversible pendiente."""
    _sweep()
    if not _PENDING:
        return ""
    def _what(v: dict) -> str:
        if v.get("action") == "data" and isinstance(v.get("op"), dict):
            return f"la acción «{v['op'].get('action')}»"
        return "el borrado"
    bits = "; ".join(f"«{wid}» — {_what(v)}" for wid, v in _PENDING.items())
    return ("CONFIRMACIÓN PENDIENTE — le pediste al operador que confirme " + bits + ". Si dice que SÍ, llama a "
            "`confirm_widget_delete(confirmed=true)`; si dice que NO, `confirm_widget_delete(confirmed=false)`. "
            "No lo trates como charla nueva.")


def resolve(widget_id: str = "", ok: bool = True) -> dict | None:
    """Resuelve UNA confirmación pendiente: la de `widget_id`, o —si no se da id— la única/última pendiente
    (la voz no siempre nombra el widget). Devuelve {'widget_id', 'action', ...} o None si no había ninguna.
    Solo bookkeeping: la EJECUCIÓN (borrar) la hace el llamador en su loop. Si `ok` es False, avisa a la
    tarjeta para que quite el overlay."""
    _sweep()
    wid = (widget_id or "").strip().lower()
    p = None
    if wid and wid in _PENDING:
        p = _PENDING.pop(wid)
    elif not wid and len(_PENDING) == 1:
        wid, p = _PENDING.popitem()
    elif not wid and _PENDING:                        # varias pendientes, sin id → la más reciente
        wid = max(_PENDING, key=lambda k: _PENDING[k]["ts"])
        p = _PENDING.pop(wid)
    if p is None:
        return None
    if not ok:
        _emit("confirm-cancel", wid)
    return {"widget_id": wid, **p}


# ── detección DETERMINISTA de sí/no (es/en) — no depende del LLM (mismo espíritu que attention.hard_interrupt) ──
_YES_RE = re.compile(r"\b(si|sip|claro|vale|venga|dale|adelante|hazlo|hazla|borralo|borrala|"
                     r"confirmo|confirmado|ok|okey|okay|perfecto|yes|yeah|yep|do it|go ahead|confirm)\b")
_NO_RE = re.compile(r"\b(no|nop|cancela|cancelar|cancelalo|dejalo|dejala|para|olvidalo|mejor no|"
                    r"nada|cancel|stop|nevermind|never mind|dont|do not)\b")


def _norm(text: str) -> str:
    n = unicodedata.normalize("NFKD", text or "")
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    return n.replace("'", "").replace("’", "")


def classify_reply(text: str) -> str | None:
    """'yes' | 'no' | None para un turno cuando hay confirmación pendiente. NO se prioriza ninguno a ciegas:
    si aparecen ambos ('no, mejor sí') gana el ÚLTIMO mencionado; si ninguno, None (no es una respuesta)."""
    n = _norm(text)
    y = _YES_RE.search(n)
    no = _NO_RE.search(n)
    if y and no:
        return "yes" if y.start() > no.start() else "no"
    if y:
        return "yes"
    if no:
        return "no"
    return None


def reset() -> None:
    """Limpia el registro (tests)."""
    _PENDING.clear()
