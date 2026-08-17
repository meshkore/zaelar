"""Ensamblador de la VENTANA DE AUDITORÍA (V2-053 F1): conversación verbatim + eventos filtrados + estado.

Comprime lo que el auditor necesita para juzgar un tramo en ~2-4k tokens. Fuentes (todas por fachada, cero
acoplamiento): `memory.recent_window` (buffer conversacional persistente, u/a verbatim), el anillo de eventos
filtrados que mantiene el engine (decisiones de turno + fricción del sistema, con trace), y el bloque de ESTADO
compacto. Solo contenido del OPERADOR — nada `untrusted` de cluster entra aquí (invariante §3f).
"""
from __future__ import annotations

_MAX_CHARS_DEF = 14000          # ~3.5k tokens


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def conversation_block(turns: int = 8, *, since_ts: float = 0.0) -> str:
    """Últimos turnos verbatim del buffer conversacional (lectura directa; llamar FUERA del event loop).

    ⚠️ El SHAPE de `memory.recent_window` es `[{"role": "user"|"assistant", "content": …}]` — mensajes de chat,
    NO pares por turno. Esto leía `u`/`user`/`a`/`assistant` (claves que no existen en esa lista) y devolvía SIEMPRE
    cadena vacía, con lo que `has_conversation()` era SIEMPRE False y **Susurro no auditaba nunca** (2026-08-14).
    Fallo silencioso y de los caros: el guarda de «sin conversación no hay auditoría» se añadió el 2026-08-13 para
    impedir que el auditor rellenara el vacío con el ejemplo de su propio prompt, y al leer mal la ventana acabó
    apagando el 100% de las auditorías en vez del caso patológico. Se vio en la sesión b70a45d0, donde Susurro
    detectó SEIS veces el fallo real («data-op fantasma») con las quejas literales del operador como señal, y las
    seis veces se abstuvo — con el timeline diciendo «auditoría OMITIDA (ventana sin conversación)» sobre 16 turnos
    de conversación viva.

    Se lee el shape REAL y se toleran los dos históricos (pares `u`/`a`) por si algún registro viejo los trae.

    `since_ts` (V2-105 follow-up, 2026-08-17): `memory.recent_window` reads the SAME global buffer regardless of
    which conversation/session is asking — it has no session boundary and its 2-day TTL is deliberate (the
    FlashBrain's own continuity across reconnects). `_audit()` in engine.py already computes a recency cutoff for
    `turn_ring`/`event_ring` for exactly this reason ("un escenario diagnosticó el fallo de OTRO anterior"); this
    buffer was the one section of the audit window that gap didn't cover. Confirmed 2026-08-17: an 11-HOUR-old,
    unrelated verbatim exchange (a real operator conversation about a football's price) got pulled into a test
    session's friction audit as if it were "recent", and the auditor escalated a worker_action for it attributed
    to the test's own (unrelated) trace. Passing the caller's cutoff here closes that gap without touching the
    buffer's own TTL — a caller that doesn't care about recency (none exist yet) just passes 0.0."""
    try:
        from memory import api as memory
        win = memory.recent_window(limit=turns) or []
    except Exception:
        return ""
    lines = []
    for t in win:
        # Fail-open on a MISSING ts (mocks/future callers that don't provide one): only skip an entry we
        # actually KNOW is stale, never assume "no timestamp" means "epoch zero, therefore ancient".
        ts = t.get("ts")
        if since_ts and ts and float(ts) < since_ts:
            continue
        # Shape CANÓNICO: mensaje de chat con role/content.
        role = str(t.get("role") or "").strip().lower()
        content = _clip(str(t.get("content") or ""), 400)
        if role and content:
            lines.append(f"OPERADOR: {content}" if role == "user" else f"  ZAELAR: {content}")
            continue
        # Compat: par por turno (u/a). No se ha visto en producción, pero abstenerse por no reconocer un shape es
        # justo el fallo que esto arregla.
        u = _clip(str(t.get("u") or t.get("user") or ""), 400)
        a = _clip(str(t.get("a") or t.get("assistant") or ""), 400)
        if u:
            lines.append(f"OPERADOR: {u}")
        if a:
            lines.append(f"  ZAELAR: {a}")
    return "\n".join(lines)


def turns_block(turn_ring: list[dict]) -> str:
    """Decisiones por turno (del topic `turn.completed`): qué tools vio, qué decidió, con su trace."""
    lines = []
    for t in turn_ring:
        d = t.get("decision") or {}
        flags = " ".join(f"{k}={v}" for k, v in d.items() if v) or "charla"
        lines.append(f"[{t.get('trace', '')}] «{_clip(t.get('user', ''), 160)}» → {flags}")
    return "\n".join(lines)


def events_block(event_ring: list[dict]) -> str:
    lines = []
    for e in event_ring:
        extra = e.get("extra") or {}
        detail = _clip(str(e.get("text") or extra.get("reason") or extra.get("kind") or ""), 160)
        lines.append(f"[{e.get('trace', '')}] {e.get('kind', '')}/{_clip(e.get('label', ''), 60)}"
                     + (f" — {detail}" if detail else ""))
    return "\n".join(lines)


def state_block() -> str:
    try:
        from memory import api as memory
        blk, _op, _stats = memory.compose_state()
        return _clip(blk, 1500)
    except Exception:
        return ""


def compose_audit_window(*, reason: str, signals: list[str], turn_ring: list[dict],
                         event_ring: list[dict], turns: int = 8,
                         max_chars: int = _MAX_CHARS_DEF, since_ts: float = 0.0) -> str:
    """El documento que se manda al auditor. Secciones fijas; recorte global al presupuesto.

    `since_ts`: mismo cutoff de recencia que ya se aplica a `turn_ring`/`event_ring` en `engine.py::_audit` —
    ver el docstring de `conversation_block` para el incidente que esto cierra."""
    parts = [
        "=== FRICCIÓN DETECTADA ===",
        f"motivo: {reason}",
    ]
    if signals:
        parts.append("señales: " + "; ".join(_clip(s, 80) for s in signals[:6]))
    conv = conversation_block(turns, since_ts=since_ts)
    if conv:
        parts += ["", "=== CONVERSACIÓN RECIENTE (viejo→nuevo, verbatim) ===", conv]
    tb = turns_block(turn_ring)
    if tb:
        parts += ["", "=== DECISIONES POR TURNO (qué hizo el cerebro rápido) ===", tb]
    eb = events_block(event_ring)
    if eb:
        parts += ["", "=== EVENTOS DEL SISTEMA (filtrados) ===", eb]
    st = state_block()
    if st:
        parts += ["", "=== ESTADO ACTUAL (lo que el cerebro ve en su prompt) ===", st]
    doc = "\n".join(parts)
    return doc if len(doc) <= max_chars else doc[:max_chars] + "\n…(recortado)"


def has_conversation(turns: int = 8, *, since_ts: float = 0.0) -> bool:
    """¿Hay algo que auditar? SIN conversación en la ventana, Susurro no tiene material y NO debe auditar.

    Incidente 2026-08-13, y es de los graves. Saltó la fricción «worker encallado (sin eventos)» mientras el buffer
    conversacional estaba vacío, así que la ventana salió de 1.643 caracteres SIN la sección de conversación (el
    ensamblador omite las secciones vacías, sin decir que faltan). El auditor, ante ese vacío, **rellenó el hueco
    con el EJEMPLO que lleva en su propio prompt de sistema** —el caso de la ITV de V2-061— y afirmó como hecho
    «el operador pidió cancelar una cita real». Y como `worker_action` está habilitado (F2), despachó un worker de
    verdad a CANCELAR LA CITA. Una acción sobre el mundo nacida de una alucinación, sin que el operador hubiera
    dicho una palabra.

    Es la misma clase de fallo que [[feedback_visible_state_over_silent_state]]: una ventana incompleta se veía
    igual que una ventana completa. La corrección de raíz es no dejar que un auditor de CONVERSACIONES opine
    cuando no hay conversación — abstenerse es gratis; inventar cuesta una cita cancelada."""
    return bool(conversation_block(turns, since_ts=since_ts).strip())
