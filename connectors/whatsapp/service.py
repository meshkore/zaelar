#
# service.py — WhatsApp connector ENGINE integrated into zaelar (INI-014; unified store in INI-015). Runs in the
# server lifespan (gated by WA_ENABLED, always-on). Starts the bridge (observe), then loops: reads state+QR, triages
# new messages with the SHARED LOCAL model, and WRITES the UNIFIED messaging store
# (widgets/_data/mensajeria.json, platform="whatsapp") — the same one Telegram also writes. Also drains operator
# orders (pending_read for its platform) by calling the bridge (actual mark-read).
#
# Boundary: none of this touches ~/.hermes/hermes-agent (vendored bridge). Triage does NOT go through the Hermes
# agent (privacy + voice ACP invariant). See .meshkore/docs/architecture/zaelar-hermes-federation.md.
#
import asyncio

from loguru import logger

from connectors.messaging import ingest, notify, store, triage
from connectors.whatsapp import client, config
from connectors.whatsapp.bridge_proc import bridge

PLATFORM = "whatsapp"

_task: asyncio.Task | None = None
_seen: set[str] = set()          # already shown messageIds (to avoid resurrecting what the operator removed)
_published: set[str] = set()     # v2 stateless: messageIds already published to bus (dedup before widget triage)
_mark_inbox = None               # v2 stateless: msg.mark_read subscription (created in the loop; see ingest.py)
_reply_inbox = None              # V2-521: msg.reply subscription (created in the loop)


def enabled() -> bool:
    # UI-MANAGED CONFIG: store (written by the UI when clicking "Connect WhatsApp") wins; if it says nothing, fall
    # back to WA_ENABLED (back-compat / power-user). See config/connectors.py.
    from config import connectors as _store
    return _store.enabled("whatsapp")


def _set_status(status: str, qr=None) -> None:
    try:
        if ingest.v2_enabled():
            ingest.publish_status(PLATFORM, status, qr)     # stateless: widget reflects state+QR
        else:
            store.set_platform_status(PLATFORM, status, qr)
    except Exception as e:
        logger.debug(f"WhatsApp set_status: {e}")


def _origin(m: dict) -> tuple[str, str | None]:
    if m.get("isGroup"):
        return (m.get("senderName") or "?", m.get("chatName") or "grupo")
    return (m.get("senderName") or "?", None)


async def _ingest_new() -> None:
    msgs = await client.get_messages()
    if not msgs:
        return
    if ingest.v2_enabled():
        # STATELESS: publish NEW messages to the bus (dedup by messageId before triage) — the messaging widget
        # triages, stores, and notifies. The connector does not triage or store state.
        for m in msgs:
            mid = m.get("messageId")
            if mid and mid not in _published:
                _published.add(mid)
                ingest.publish_msg(PLATFORM, m)
        return
    verdicts = await triage.classify(msgs, config.operator_name() or None)
    surfaced = notify.surface(verdicts, _seen)
    if not surfaced:
        return
    for v in surfaced:
        _seen.add(v.get("messageId"))
        who, group = _origin(v)
        v["from"], v["group"] = who, group          # normalize to unified-store shape
    store.upsert_items(PLATFORM, surfaced)
    logger.info(f"WhatsApp: +{len(surfaced)} para ti")
    await notify.announce("WhatsApp", surfaced)


async def _drain_reads() -> None:
    v2 = ingest.v2_enabled()
    keys = (_mark_inbox.drain() if _mark_inbox else []) if v2 else store.take_pending_read(PLATFORM)
    if not keys:
        return
    # The bridge expects {chatId, messageId, senderId}; the key adds `platform` -> remove it before sending.
    payload = [{"chatId": k.get("chatId"), "messageId": k.get("messageId"), "senderId": k.get("senderId")}
               for k in keys]
    try:
        await client.mark_read(payload)
    except Exception as e:
        logger.warning(f"WhatsApp mark-read falló (reintento luego): {e}")
        if v2:
            for k in keys:                       # re-publish to bus -> retry on next tick
                ingest.publish_mark_read(k)
        else:
            store.requeue_pending_read(keys)


async def _drain_replies() -> None:
    """Drain dictated replies (V2-521 — the email connector had this since V2-051; WhatsApp only ever read).
    The widget's reply action already enqueued mark-read for the original, so this only SENDS. A failure is
    TOLD to the operator through brain_notes and not requeued: a bad send retried forever is worse than one
    honest "no pude enviarlo"."""
    if not ingest.v2_enabled() or _reply_inbox is None:
        return
    for r in _reply_inbox.drain():
        chat_id = str(r.get("chatId") or r.get("to") or "").strip()
        text = (r.get("text") or "").strip()
        if not chat_id or not text:
            continue
        try:
            await client.send_message(chat_id, text, reply_to=r.get("messageId") or None)
            logger.info(f"WhatsApp: respuesta enviada a {chat_id}")
            _note(f"[SISTEMA] WhatsApp enviado a {r.get('to') or chat_id}. Confírmaselo al operador de forma natural.")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"WhatsApp: fallo al enviar a {chat_id}: {e}")
            _note(f"[SISTEMA] No se pudo enviar el WhatsApp a {r.get('to') or chat_id} ({e}). Avísale al operador.")


def _note(text: str) -> None:
    try:
        from voice import brain_notes
        brain_notes.push(text)
    except Exception:
        pass


async def _loop() -> None:
    global _mark_inbox, _reply_inbox
    _set_status("starting", None)
    if ingest.v2_enabled() and _mark_inbox is None:
        _mark_inbox = ingest.MarkReadInbox(PLATFORM)     # subscription in THIS loop (server) -> direct delivery
        _reply_inbox = ingest.ReplyInbox(PLATFORM)       # V2-521: dictated replies, same delivery path
    try:
        await bridge.start()
    except Exception as e:
        logger.error(f"WhatsApp: no se pudo arrancar el bridge: {e}")
        _set_status("off", None)
        return
    connected = False
    while True:
        try:
            h = await client.health()
            st = (h or {}).get("status", "connecting")
            if st == "connected":
                if not connected:
                    logger.info("WhatsApp conectado — escuchando tu buzón")
                connected = True
                _set_status("connected", None)
                await _ingest_new()
                await _drain_reads()
                await _drain_replies()
            else:
                connected = False
                _set_status("connecting", (h or {}).get("qr"))
        except Exception as e:
            logger.debug(f"WhatsApp tick: {e}")
        await asyncio.sleep(config.poll_interval())


def start() -> None:
    """Start the engine as a background task (call from server lifespan if WA_ENABLED=1)."""
    global _task
    if not enabled():
        _set_status("off", None)
        logger.info("WhatsApp: desactivado (WA_ENABLED!=1)")
        return
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    logger.info("WhatsApp: motor arrancado")


async def stop() -> None:
    global _task
    if _task:
        _task.cancel()
        _task = None
    await bridge.stop()
