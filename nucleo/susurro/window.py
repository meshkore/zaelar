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


def conversation_block(turns: int = 8) -> str:
    """Últimos turnos verbatim del buffer conversacional (lectura directa; llamar FUERA del event loop)."""
    try:
        from memory import api as memory
        win = memory.recent_window(limit=turns) or []
    except Exception:
        return ""
    lines = []
    for t in win:
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
                         max_chars: int = _MAX_CHARS_DEF) -> str:
    """El documento que se manda al auditor. Secciones fijas; recorte global al presupuesto."""
    parts = [
        "=== FRICCIÓN DETECTADA ===",
        f"motivo: {reason}",
    ]
    if signals:
        parts.append("señales: " + "; ".join(_clip(s, 80) for s in signals[:6]))
    conv = conversation_block(turns)
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
