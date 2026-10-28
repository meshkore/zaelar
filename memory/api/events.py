"""The facade's one signal: every mutation emits `memory.updated` through `bus/` (loop-agnostic, best-effort)."""


def _emit(topic: str, payload=None):
    try:
        import bus
        bus.emit_sync(topic, payload or {})
    except Exception:
        pass
