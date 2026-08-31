"""Assembler for the AUDIT WINDOW (V2-053 F1): verbatim conversation + filtered events + state.

Compresses what the auditor needs to judge a segment into ~2-4k tokens. Sources (all through facades, zero
coupling): `memory.recent_window` (persistent conversational buffer, u/a verbatim), the filtered event ring
maintained by the engine (turn decisions + system friction, with trace), and the compact STATE block. Only
OPERATOR content—nothing `untrusted` from the cluster enters here (invariant §3f).
"""
from __future__ import annotations

_MAX_CHARS_DEF = 14000          # ~3.5k tokens


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def conversation_block(turns: int = 8, *, since_ts: float = 0.0) -> str:
    """Latest verbatim turns from the conversational buffer (direct read; call OUTSIDE the event loop).

    ⚠️ The SHAPE of `memory.recent_window` is `[{"role": "user"|"assistant", "content": …}]`—chat messages,
    NOT per-turn pairs. This read `u`/`user`/`a`/`assistant` (keys that do not exist in that list) and ALWAYS returned
    an empty string, so `has_conversation()` was ALWAYS False and **Susurro never audited** (2026-08-14).
    A silent and costly failure: the “no conversation, no audit” guard was added on 2026-08-13 to prevent the auditor
    from filling the gap with the example from its own prompt; misreading the window ended up disabling 100% of audits
    instead of only the pathological case. It was seen in session b70a45d0, where Susurro detected the real failure
    (“phantom data-op”) SIX times with the operator’s literal complaints as the signal, and abstained all six times—
    with the timeline saying “audit OMITTED (window without conversation)” over 16 turns of live conversation.

    The REAL shape is read, and both historical forms (`u`/`a` pairs) are tolerated in case an old record contains them.

    `since_ts` (V2-105 follow-up, 2026-08-17): `memory.recent_window` reads the SAME global buffer regardless of
    which conversation/session is asking — it has no session boundary and its 2-day TTL is deliberate (the
    FlashBrain's own continuity across reconnects). `_audit()` in engine.py already computes a recency cutoff for
    `turn_ring`/`event_ring` for exactly this reason ("one scenario diagnosed the failure of an earlier OTHER one"); this
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
        # CANONICAL shape: chat message with role/content.
        role = str(t.get("role") or "").strip().lower()
        content = _clip(str(t.get("content") or ""), 400)
        if role and content:
            lines.append(f"OPERADOR: {content}" if role == "user" else f"  ZAELAR: {content}")
            continue
        # Compat: per-turn pair (u/a). It has not been seen in production, but refusing to recognize a shape is
        # precisely the failure this fixes.
        u = _clip(str(t.get("u") or t.get("user") or ""), 400)
        a = _clip(str(t.get("a") or t.get("assistant") or ""), 400)
        if u:
            lines.append(f"OPERADOR: {u}")
        if a:
            lines.append(f"  ZAELAR: {a}")
    return "\n".join(lines)


def turns_block(turn_ring: list[dict]) -> str:
    """Per-turn decisions (from the `turn.completed` topic): which tools it saw, what it decided, with its trace."""
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
    """The document sent to the auditor. Fixed sections; global truncation to fit the budget.

    `since_ts`: the same recency cutoff already applied to `turn_ring`/`event_ring` in `engine.py::_audit`—
    see the `conversation_block` docstring for the incident this closes."""
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
    """Is there anything to audit? WITHOUT conversation in the window, Susurro has no material and MUST NOT audit.

    Incident from 2026-08-13, and one of the serious ones. The “worker stuck (no events)” friction fired while the
    conversational buffer was empty, so the window came out at 1,643 characters WITHOUT the conversation section
    (the assembler omits empty sections without saying they are missing). Faced with that gap, the auditor **filled
    it with the EXAMPLE in its own system prompt**—the V2-061 vehicle-inspection case—and stated as fact “the
    operator asked to cancel a real appointment.” And because `worker_action` is enabled (F2), it dispatched a real
    worker to CANCEL THE APPOINTMENT. An action in the world born from a hallucination, without the operator having
    said a word.

    It is the same class of failure as [[feedback_visible_state_over_silent_state]]: an incomplete window looked
    identical to a complete window. The root fix is not to let a CONVERSATION auditor weigh in when there is no
    conversation—abstaining is free; inventing costs a canceled appointment."""
    return bool(conversation_block(turns, since_ts=since_ts).strip())
