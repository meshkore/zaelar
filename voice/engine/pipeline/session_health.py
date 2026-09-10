"""session_health.py — a session that closes ON AN ERROR is a DEATH, not a goodbye (V2-656, 2026-09-10).

Measured live: an unrecoverable LLM error closed the AgentSession while the room, the mic and the server
stayed up — the operator talked to a grey orb for two minutes with the ◉ panel green and nothing trying to
recover. Three duties, none of which may depend on the others: say it where the monitor looks
(`health_state` → /api/status turns the voice row RED), say it on the timeline (alert), and ask homeostasis
to recycle the embedded worker so the next page connect gets a living engine. Extracted from `agent.py`'s
close handler to pay the newborn-size ratchet — the CALLER stays the session's `close` event.
"""
from __future__ import annotations


def on_session_dead(error, emit) -> None:
    """The close event carried an error → record, announce, and request recovery. Every duty fail-soft."""
    reason = str(error)[:160]
    try:
        from voice import health_state
        health_state.record("voice", "dead", reason)
    except Exception:
        pass
    try:
        emit("alert", "⚠️ la sesión de voz MURIÓ por un error irrecuperable — reciclando el motor",
             text=reason, role="system")
    except Exception:
        pass
    try:
        from nucleo import homeostasis
        homeostasis.request_recycle(f"voice session died: {reason}")
    except Exception:
        pass


def on_session_alive() -> None:
    """A session that just STARTED supersedes any recorded death — otherwise the ◉ row stays red for the
    record's whole TTL over a working voice."""
    try:
        from voice import health_state
        health_state.clear("voice")
    except Exception:
        pass
