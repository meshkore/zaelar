#
# service/ — WhatsApp connector ENGINE integrated into zaelar (unified store in connectors/messaging). Runs in the
# server lifespan (gated by WA_ENABLED, always-on). Starts the bridge (observe), then loops: reads state+QR, triages
# new messages with the SHARED LOCAL model, and WRITES the UNIFIED messaging store
# (widgets/_data/mensajeria.json, platform="whatsapp") — the same one Telegram also writes. Also drains operator
# orders (pending_read for its platform) by calling the bridge (actual mark-read).
#
# Boundary: triage runs in this engine and never through an outside agent (privacy + voice ACP invariant).
#
# FACADE: the inboxes, the dedup sets and the loop live here; the drains, by concern, in the sibling modules, each
# reading this module back at call time (`_svc.…`) — one source.
#
import asyncio

from loguru import logger

from connectors.messaging import ingest, store
from connectors.whatsapp import client, config
from connectors.whatsapp.bridge_proc import bridge

PLATFORM = "whatsapp"

_task: asyncio.Task | None = None
_seen: set[str] = set()          # already shown messageIds (to avoid resurrecting what the operator removed)
_published: set[str] = set()     # v2 stateless: messageIds already published to bus (dedup before widget triage)
_mark_inbox = None               # v2 stateless: msg.mark_read subscription (created in the loop; see ingest.py)
_reply_inbox = None              # V2-521: msg.reply subscription (created in the loop)
_send_inbox = None               # V2-683: msg.send — writing to somebody who has not written
_history_inbox = None            # V2-546: msg.history subscription (created in the loop)
_contacts_inbox = None           # V2-714: msg.contacts subscription
_chats_inbox = None              # msg.chats: one page of the chat list
_group_inbox = None              # msg.group: creating a group
_unread_inbox = None             # msg.mark_unread: «déjalo como no leído»


def enabled() -> bool:
    # UI-MANAGED CONFIG: store (written by the UI when clicking "Connect WhatsApp") wins; if it says nothing, fall
    # back to WA_ENABLED (back-compat / power-user). See config/connectors.py.
    from config import connectors as _store
    return _store.enabled("whatsapp")


def _set_status(status: str, qr=None, detail=None) -> None:
    try:
        if ingest.v2_enabled():
            ingest.publish_status(PLATFORM, status, qr, detail)   # stateless: widget reflects state+QR+reason
        else:
            store.set_platform_status(PLATFORM, status, qr, detail)
    except Exception as e:
        logger.debug(f"WhatsApp set_status: {e}")


def _note(text: str) -> None:
    try:
        from voice import brain_notes
        brain_notes.push(text)
    except Exception:
        pass


async def _loop() -> None:
    global _mark_inbox, _reply_inbox, _send_inbox, _history_inbox, _contacts_inbox, _chats_inbox, _group_inbox
    global _unread_inbox
    _set_status("starting", None)
    if _contacts_inbox is None:
        _contacts_inbox = ingest.ContactsInbox(PLATFORM)   # V2-714: the address book
    if _chats_inbox is None:
        _chats_inbox = ingest.ChatsInbox(PLATFORM)         # the chat list
    if _group_inbox is None:
        _group_inbox = ingest.GroupInbox(PLATFORM)         # new groups
    if _unread_inbox is None:
        _unread_inbox = ingest.MarkUnreadInbox(PLATFORM)   # back to unread
    if ingest.v2_enabled() and _mark_inbox is None:
        _mark_inbox = ingest.MarkReadInbox(PLATFORM)     # subscription in THIS loop (server) -> direct delivery
        _reply_inbox = ingest.ReplyInbox(PLATFORM)       # V2-521: dictated replies, same delivery path
        _send_inbox = ingest.SendInbox(PLATFORM)         # V2-683: opening a conversation
        _history_inbox = ingest.HistoryAskInbox(PLATFORM)  # V2-546: "load previous"
    try:
        await bridge.start()
    except Exception as e:
        # The reason travels to the card. An «off» with no reason is how a bridge that could never start in a
        # container stayed invisible: the card said «Preparando la conexión…» forever.
        logger.error(f"WhatsApp: no se pudo arrancar el bridge: {e}")
        _set_status("error", None, str(e))
        return
    connected = False
    while True:
        try:
            if bridge.proc is not None and bridge.proc.returncode is not None:
                # The bridge died under us. Nothing else restarts it, and the card would wait on a QR that no
                # process is going to produce — relaunch it; the paired session on disk makes that silent.
                logger.warning(f"WhatsApp: el bridge murió (exit {bridge.proc.returncode}) — lo relanzo")
                connected = False
                _set_status("connecting", None)
                await bridge.start()
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
                for what, fn in (("sends", _drain_sends),
                                 ("read marks", _drain_external_reads), ("history", _drain_history),
                                 ("contacts", _drain_contacts), ("chats", _drain_chats),
                                 ("groups", _drain_groups), ("unread", _drain_unread), ("sync", _drain_sync)):
                    try:
                        await fn()
                    except Exception as e:  # noqa: BLE001
                        logger.debug(f"WhatsApp {what} tick: {e}")
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


# The drains by concern; the loop and the tests reach them here.
from connectors.whatsapp.service.inbound import (  # noqa: E402
    _drain_external_reads, _drain_history, _history_entry, _ingest_new, _origin)
from connectors.whatsapp.service.directory import (  # noqa: E402
    _chat_row, _drain_chats, _drain_contacts, _drain_groups, _drain_reads, _drain_sync, _drain_unread, _wa_person)
from connectors.whatsapp.service.outbound import _drain_replies, _drain_sends, _echo_sent, _jid, _send  # noqa: E402
