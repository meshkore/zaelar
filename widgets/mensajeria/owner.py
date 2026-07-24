#
# owner.py — backend VIVO del widget mensajería (V2-008, kind:"backed", gate:"nucleo"). Es la pieza que cierra el
# reshape v2 del diagrama central: los conectores (WhatsApp/Telegram) publican mensajes entrantes al bus
# (connector.msg) y su estado de vínculo (connector.status); ESTE owner los consume, los TRÍA con su agente
# interno (modelo LOCAL, privacidad), vuelca el contenido durable a la MEMORIA central, avisa proactivamente solo
# lo relevante, y refleja todo en el store de UI del widget. Es el ÚNICO ESCRITOR de widgets/_data/mensajeria/
# (contrato backed: la cara data.py/widget.js pasa a leer + encolar; las acciones del operador/brain llegan por el
# buzón del supervisor → handle()).
#
# Marcar leído es simétrico: una acción read/clear/readchat NO habla con ninguna app directamente — publica
# msg.mark_read al bus, que el conector de la plataforma correcta drena y ejecuta en su app. El owner no conoce
# WhatsApp ni Telegram: solo el bus. Conectores STATELESS de verdad.
#
# STRANGLER-FIG: el supervisor solo arranca este owner con BRAIN=nucleo (gate del manifest). Bajo duo/hermes el
# widget se comporta como el passive de siempre (owner NO corre → las acciones caen a data.apply_action y los
# conectores escriben el store por su camino directo). Cero regresión hasta el entierro (V2-009).
#
import asyncio
import os

from loguru import logger

from connectors.messaging import config as msgcfg
from connectors.messaging import ingest, notify
from connectors.messaging import store as msgstore

_LABEL = {"whatsapp": "WhatsApp", "telegram": "Telegram", "email": "Email"}
_BATCH = float(os.getenv("MSG_TRIAGE_BATCH", "2.0"))   # s entre lotes de triaje (agrupa ráfagas → 1 sola llamada)


def _origin(m: dict) -> tuple[str, str | None]:
    if m.get("isGroup"):
        return (m.get("senderName") or "?", m.get("chatName") or "grupo")
    return (m.get("senderName") or "?", None)


class _Owner:
    """El dueño del widget mensajería. Vida gobernada por widgets/supervisor.py (start/stop/handle + reinicio)."""

    def __init__(self):
        self._msg_sub = None
        self._status_sub = None
        self._task: asyncio.Task | None = None
        self._seen: set[str] = set()      # messageIds ya sacados a flote (no resucitar lo que el operador quitó)

    # ── ciclo de vida ────────────────────────────────────────────────────────────────────────────────────
    async def start(self) -> None:
        """Barato: solo suscribe al bus y lanza el consumidor. Idempotente (el supervisor puede reiniciarnos)."""
        import bus
        if self._msg_sub is None:
            self._msg_sub = bus.subscribe(ingest.TOPIC_MSG)
        if self._status_sub is None:
            self._status_sub = bus.subscribe(ingest.TOPIC_STATUS)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._consume())
        logger.info("mensajeria owner arrancado (triaje en el widget · conectores stateless)")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        for sub in (self._msg_sub, self._status_sub):
            try:
                if sub is not None:
                    sub.close()
            except Exception:
                pass
        self._msg_sub = self._status_sub = None

    # ── consumo del bus (entrantes + estado) ───────────────────────────────────────────────────────────────
    async def _consume(self) -> None:
        while True:
            await asyncio.sleep(_BATCH)
            try:
                self._apply_status()
            except Exception as e:
                logger.debug(f"mensajeria owner status: {e}")
            try:
                await self._triage_batch()
            except Exception as e:
                logger.debug(f"mensajeria owner triage: {e}")

    def _apply_status(self) -> None:
        """Refleja los connector.status pendientes en el store de UI (el owner es el único escritor)."""
        q = self._status_sub.queue if self._status_sub else None
        if q is None:
            return
        while True:
            try:
                ev = q.get_nowait()
            except Exception:
                break
            platform = (ev or {}).get("platform")
            if platform:
                msgstore.set_platform_status(platform, ev.get("status", "off"), ev.get("qr"), ev.get("detail"))

    async def _triage_batch(self) -> None:
        """Drena el lote de mensajes entrantes acumulados, los tría, saca a flote los relevantes, los guarda
        (store de UI + memoria) y avisa. Agrupado por plataforma para el upsert y el aviso."""
        from . import triage_agent

        q = self._msg_sub.queue if self._msg_sub else None
        if q is None:
            return
        batch: list[dict] = []
        while True:
            try:
                batch.append(q.get_nowait())
            except Exception:
                break
        if not batch:
            return

        verdicts = await triage_agent.classify(batch, msgcfg.operator_name() or None)
        surfaced = notify.surface(verdicts, self._seen)
        if not surfaced:
            return
        # Normaliza a la forma del store y agrupa por plataforma.
        by_platform: dict[str, list[dict]] = {}
        for v in surfaced:
            self._seen.add(v.get("messageId"))
            who, group = _origin(v)
            v["from"], v["group"] = who, group
            by_platform.setdefault(v.get("platform") or "?", []).append(v)
        for platform, items in by_platform.items():
            if platform == "?":
                continue
            msgstore.upsert_items(platform, items)   # store de UI + volcado a memoria (kind='msg')
            logger.info(f"mensajeria: +{len(items)} de {platform} para ti")
            await notify.announce(_LABEL.get(platform, platform), items)

    # ── acciones del operador / brain (buzón del supervisor) ─────────────────────────────────────────────────
    async def handle(self, action: str, payload: dict) -> None:
        """Aplica una acción y, si marcó algo como leído, publica msg.mark_read para que el conector correcto lo
        marque en su app. Reusa la MISMA lógica de mutación que la UI (data.apply_action) — el owner es el único
        escritor, así que aplicarla aquí no compite con nadie."""
        from . import data
        # Mutación (mismo vocabulario que los botones de la UI y las tags [[msg.*]]).
        try:
            data.apply_action(action, payload or {})
        except Exception as e:
            logger.warning(f"mensajeria handle {action!r}: {e}")
            return
        # Todo lo que la mutación encoló como "marcar leído" sale al bus (los conectores lo drenan por plataforma).
        try:
            for key in msgstore.take_pending_read():
                ingest.publish_mark_read(key)
        except Exception as e:
            logger.debug(f"mensajeria mark_read flush: {e}")
        # Idem para las RESPUESTAS a enviar (V2-051): el conector de esa plataforma (hoy email) las envía.
        try:
            for rep in msgstore.take_pending_reply():
                ingest.publish_reply(rep)
        except Exception as e:
            logger.debug(f"mensajeria reply flush: {e}")


# Instancia única que el supervisor gobierna (contrato: async start()/stop()/handle(action,payload)).
_OWNER = _Owner()


async def start() -> None:
    await _OWNER.start()


async def stop() -> None:
    await _OWNER.stop()


async def handle(action: str, payload: dict) -> None:
    await _OWNER.handle(action, payload)
