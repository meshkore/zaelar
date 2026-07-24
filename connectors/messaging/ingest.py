#
# ingest.py — capa STATELESS de mensajería v2 «Colmena» (EPIC-v2, V2-008). El reshape del diagrama central:
# los conectores dejan de TRIAR y de GUARDAR estado; solo LEEN su fuente y PUBLICAN eventos al bus/ (Sistema
# Nervioso). El triaje y el store de UI suben al widget `mensajeria` (owner backed), y el CONTENIDO durable va a
# la memoria central. Aquí viven las tres señales que unen conector ↔ widget:
#
#   • connector.msg     — un mensaje entrante NORMALIZADO (payload agnóstico de plataforma), que el widget tría.
#   • connector.status  — estado de vínculo + QR de una plataforma, que el widget refleja en su tarjeta.
#   • msg.mark_read     — orden del widget al conector correcto para marcar leído en su app (enrutada por platform).
#
# STRANGLER-FIG: gated en BRAIN=nucleo. Bajo duo/hermes (el default hasta el entierro, V2-009) los conectores
# siguen su camino DIRECTO de siempre (service.py → triage+store+notify), intacto y verificado en vivo. El
# camino v2 corre en paralelo, sin regresión, hasta el cutover. Ver EPIC §2 (invariantes de la migración).
#
import os

import bus

TOPIC_MSG = "connector.msg"
TOPIC_STATUS = "connector.status"
TOPIC_MARK_READ = "msg.mark_read"
TOPIC_REPLY = "msg.reply"          # V2-051: el widget pide ENVIAR una respuesta; el conector de esa plataforma la envía


def v2_enabled() -> bool:
    """¿Ruta stateless v2 activa? Sigue al cerebro (nucleo → sí) salvo override explícito por env
    (`ZAELAR_MSG_V2=0|1`, fallback power-user, NUNCA lo configura el usuario final). Los conectores y el owner
    del widget consultan este único predicado para elegir camino — cero divergencia entre piezas."""
    env = os.getenv("ZAELAR_MSG_V2")
    if env is not None:
        return env == "1"
    try:
        from config.v2 import active_brain
        return active_brain() == "nucleo"
    except Exception:
        return False


def publish_msg(platform: str, msg: dict) -> None:
    """Publica un mensaje entrante normalizado. `msg` = {senderName, chatName?, isGroup, body, messageId,
    chatId, senderId} (la MISMA forma que ya entendía el triaje). Loop-agnóstico (emit_sync). Nunca lanza."""
    try:
        bus.emit_sync(TOPIC_MSG, {"platform": platform, **(msg or {})})
    except Exception:
        pass


def publish_status(platform: str, status: str, qr=None, detail=None) -> None:
    """Publica el estado de vínculo + QR + mensaje humano (`detail`) de una plataforma (el widget lo refleja en su
    tarjeta: loader con detalle mientras conecta, card de error con el motivo si falla)."""
    try:
        bus.emit_sync(TOPIC_STATUS, {"platform": platform, "status": status, "qr": qr, "detail": detail})
    except Exception:
        pass


def publish_mark_read(key: dict) -> None:
    """El widget pide marcar leído: {platform, chatId, messageId, senderId}. El conector de esa plataforma
    lo drena de su `MarkReadInbox` y lo marca en su app."""
    try:
        bus.emit_sync(TOPIC_MARK_READ, dict(key or {}))
    except Exception:
        pass


def publish_reply(key: dict) -> None:
    """El widget pide ENVIAR una respuesta (V2-051): {platform, chatId, to, messageId, subject, msgid, text}. El
    conector de esa plataforma (hoy email) lo drena de su `ReplyInbox` y lo envía en su app (SMTP)."""
    try:
        bus.emit_sync(TOPIC_REPLY, dict(key or {}))
    except Exception:
        pass


class _PlatformInbox:
    """Base: suscripción por-plataforma a un topic; drain() devuelve (y consume) SOLO los eventos de SU plataforma.
    Cada conector crea la suya EN SU LOOP (dentro de `_loop()`) y la drena en cada tick — el estado no vive en el
    conector (v2 stateless). Los eventos de otras plataformas se descartan al drenar (no fugan)."""

    _TOPIC = ""

    def __init__(self, platform: str):
        self.platform = platform
        self._sub = bus.subscribe(self._TOPIC)

    def drain(self) -> list[dict]:
        out: list[dict] = []
        q = self._sub.queue
        while True:
            try:
                ev = q.get_nowait()
            except Exception:
                break
            if (ev or {}).get("platform") == self.platform:
                out.append(ev)
        return out

    def close(self) -> None:
        try:
            self._sub.close()
        except Exception:
            pass


class MarkReadInbox(_PlatformInbox):
    """Suscripción por-plataforma a `msg.mark_read`. Reemplaza a `store.take_pending_read(platform)` en la ruta v2."""
    _TOPIC = TOPIC_MARK_READ


class ReplyInbox(_PlatformInbox):
    """Suscripción por-plataforma a `msg.reply` (V2-051). El conector drena y ENVÍA la respuesta en su app."""
    _TOPIC = TOPIC_REPLY
