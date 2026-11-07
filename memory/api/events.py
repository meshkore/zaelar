"""The facade's one signal: every mutation emits `memory.updated` through `bus/` (loop-agnostic, best-effort)."""


def _emit(topic: str, payload=None, piece: str | None = None):
    """`piece` = the architecture piece the mutation belongs to, when the facade speaks for one of the stores behind
    it (state, episodes, sleep); left out, the bus log reads it from this module's path (`m_api`)."""
    try:
        import bus
        payload = dict(payload or {})
        if piece:
            payload["piece"] = piece
        elif topic == "memory.updated":
            from observability import pieces
            pieces.stamp(payload, kind="memory")
        bus.emit_sync(topic, payload)
    except Exception:
        pass
