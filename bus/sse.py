"""bus/sse.py — puente SSE al frontend sobre el Sistema Nervioso (V2-001, T36).

`voice/observer.py` se RE-EXPRESA sobre el bus: sus eventos de timeline (VAD/turnos, transcripciones,
prompts/replies del cerebro, latencias, TTS, errores) se publican en el topic **`observer`**, y el endpoint
`GET /events` los consume suscribiéndose a ese topic. El observer pasa así a ser **un suscriptor más** del
bus, no un sistema de colas aparte — y de paso hereda la entrega loop-safe de `emit_sync` (antes el observer
hacía `put_nowait` cross-loop a pelo desde el job-thread de LiveKit).

**Back-compat estricta:** el payload publicado ES el mismo dict `ev` que construía `observer.emit()`, sin
envoltura — `GET /events` emite exactamente lo de siempre. Este módulo es un puente fino; toda la lógica
de construcción del evento (ring, dedup, ficheros por-sesión, latencias) sigue en `voice/observer.py`.
"""
import bus as _bus

TOPIC = "observer"


def publish(ev: dict):
    """Publica un evento de observer en el bus. Loop-agnóstico (lo llama el job-thread de LiveKit)."""
    _bus.emit_sync(TOPIC, ev)


def subscribe():
    """Suscripción al stream de observer (para `GET /events`). Devuelve una `bus.Subscription` que expone
    `.get()` — compatible con el viejo `observer.subscribe()` que devolvía una `asyncio.Queue`."""
    return _bus.subscribe(TOPIC)


def unsubscribe(sub):
    _bus.unsubscribe(sub)
