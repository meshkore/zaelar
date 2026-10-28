#
# service/ — Telegram connector ENGINE integrated into zaelar. Runs IN-PROCESS in the server lifespan
# (gated by TG_ENABLED, always-on), as an asyncio task — Telethon is a pure asyncio client, with NO Node subprocess
# or bridge to vendor (unlike WhatsApp). Telegram is "black-box lib": a third-party library (Telethon), with no Hermes
# dependency.
#
# Flow: QR login (client.qr_login(), QR rendered IN THE WIDGET via segno) -> listen to events.NewMessage -> classify
# with the SHARED LOCAL model (connectors/messaging/triage) -> write the UNIFIED store
# (widgets/_data/mensajeria.json, platform="telegram") -> drain pending_read by marking read (send_read_acknowledge).
# The classifier does NOT go through the Hermes agent (privacy + voice ACP invariant). Read-only + mark-read.
#
# FACADE: the connection, the inboxes and the loop live here; the drains, by concern, in the sibling modules (and the
# account operations in ../account_ops.py), each reading this module back at call time (`_svc.…`) — one source.
#
import asyncio
import base64
import io

from loguru import logger

from connectors.messaging import ingest, store
from connectors.telegram import config

_task: asyncio.Task | None = None
_client = None                   # telethon.TelegramClient once started
_inbox: list[dict] = []          # inbound buffer pending triage (batching)
_outbox: list[dict] = []         # V2-546: messages the OPERATOR sent from his own Telegram (no triage)
_reads: list[dict] = []          # V2-546: chats he read elsewhere ({chatId, maxId})
_seen: set[str] = set()          # already shown messageIds (do not resurrect what the operator removed)
_mark_inbox = None               # v2 stateless: msg.mark_read subscription (created in the loop; see ingest.py)
_reply_inbox = None              # V2-521: msg.reply subscription (created in the loop)
_send_inbox = None               # V2-683: msg.send — writing to somebody who has not written
_history_inbox = None            # V2-546: msg.history subscription (created in the loop)
_fetch_inbox = None              # V2-624: msg.fetch subscription (platform-wide pull)
_contacts_inbox = None           # V2-714: msg.contacts subscription (the ADDRESS BOOK, not the messages)
_chats_inbox = None              # msg.chats: one page of the chat list
_group_inbox = None              # msg.group: creating a group
_unread_inbox = None             # msg.mark_unread: «déjalo como no leído»


def enabled() -> bool:
    return config.enabled()


def _set_status(status: str, qr=None, detail=None) -> None:
    try:
        if ingest.v2_enabled():
            ingest.publish_status("telegram", status, qr, detail)   # stateless: widget reflects state+QR+reason
        else:
            store.set_platform_status("telegram", status, qr, detail)
    except Exception as e:
        logger.debug(f"Telegram set_status: {e}")


def _qr_datauri(url: str) -> str | None:
    """QR (PNG data-URI) for the tg://login URL, with segno (pure Python, native PNG — no PIL). Widget renders <img>."""
    try:
        import segno
        buf = io.BytesIO()
        segno.make(url, error="m").save(buf, kind="png", scale=6, border=2)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        logger.warning(f"Telegram: no pude generar el QR: {e}")
        return None


def _ensure_deps() -> bool:
    """Auto-install telethon+segno if missing (same spirit as WhatsApp bridge self-heal). Best-effort; returns True
    if import works after the attempt."""
    try:
        import telethon  # noqa: F401
        import segno      # noqa: F401
        return True
    except ImportError:
        logger.warning("Telegram: faltan deps (telethon/segno) — intentando instalar (make install-telegram)…")
        try:
            import subprocess
            import sys
            subprocess.run([sys.executable, "-m", "pip", "install", "telethon", "segno"],
                           check=True, capture_output=True)
            import importlib
            importlib.invalidate_caches()
            import telethon  # noqa: F401
            import segno      # noqa: F401
            return True
        except Exception as e:
            logger.error(f"Telegram: no pude instalar deps automáticamente: {e}. Ejecuta: make install-telegram")
            return False


def _note(text: str) -> None:
    try:
        from voice import brain_notes
        brain_notes.push(text)
    except Exception:
        pass


async def _login_qr() -> bool:
    """QR login (Telethon). Render QR in the widget and refresh it on expiry. Returns True if authorized.
    2FA (password) is out of scope -> log it and ask the operator to disable it or log in manually."""
    from telethon.errors import SessionPasswordNeededError
    qr = await _client.qr_login()
    while True:
        _set_status("connecting", _qr_datauri(qr.url))
        try:
            await qr.wait(timeout=30)
            return True
        except asyncio.TimeoutError:
            try:
                await qr.recreate()                                 # QR expired -> new one
            except Exception:
                qr = await _client.qr_login()
        except SessionPasswordNeededError:
            logger.error("Telegram: la cuenta tiene 2FA (contraseña). El login por QR no la cubre — "
                         "desactívala temporalmente o loguea a mano una vez; luego la sesión persiste.")
            # Its own reason, not «no_creds»: the card read «missing credentials» to someone whose credentials
            # were fine and whose account simply has a password.
            from i18n import runtime as _rt
            _set_status("error", None, _rt.text("config.cxw.tg_2fa", default=(
                "Your Telegram account has a two-step password, which the QR login does not cover. Turn it off "
                "for a moment, scan again, and turn it back on: the session is kept.")))
            return False
        except Exception as e:
            logger.warning(f"Telegram QR login: {e}")
            await asyncio.sleep(3)


async def _loop() -> None:
    global _client
    if not _ensure_deps():
        _set_status("error", None, "telethon missing")
        return
    from telethon import TelegramClient, events

    config.session_dir().mkdir(parents=True, exist_ok=True)
    _set_status("starting", None)
    # `catch_up`: what arrived while this process was not running is fetched on reconnect. An instance that is
    # stopped while idle and started on the next visit would otherwise never see those messages.
    # How this session is named in the operator's Telegram («Active sessions»): Zaelar, never the library's default.
    from version import VERSION as _ver
    _client = TelegramClient(config.session_path(), config.api_id(), config.api_hash(), catch_up=True,
                             device_model="Zaelar Agent", system_version="Zaelar", app_version=str(_ver))
    try:
        await _client.connect()
    except Exception as e:
        logger.error(f"Telegram: no pude conectar: {e}")
        _set_status("error", None, str(e))
        return

    if not await _client.is_user_authorized():
        if not await _login_qr():
            return
    logger.info("Telegram conectado — escuchando tu buzón")

    @_client.on(events.NewMessage(incoming=True))
    async def _on_msg(event):                                       # noqa: ANN001
        try:
            _inbox.append(await _normalize(event))
        except Exception as e:
            logger.debug(f"Telegram normalize: {e}")

    # V2-546 — the account is the SAME account the operator uses on his phone, so Telethon already sees
    # everything he does there. These two updates were simply never subscribed to.
    @_client.on(events.NewMessage(outgoing=True))
    async def _on_msg_out(event):                                   # noqa: ANN001
        try:
            m = await _normalize(event)
            m["from"] = ""                                          # the thread module names the operator
            _outbox.append(m)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Telegram normalize (saliente): {e}")

    @_client.on(events.MessageRead(inbox=True))
    async def _on_read(event):                                      # noqa: ANN001
        # inbox=True is "I read THEIR messages" (on any device). The outbox variant — someone read MINE — is
        # deliberately not subscribed: it says nothing about what still wants the operator's attention.
        try:
            _reads.append({"chatId": event.chat_id, "maxId": int(getattr(event, "max_id", 0) or 0)})
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Telegram read receipt: {e}")

    global _mark_inbox, _reply_inbox, _send_inbox, _history_inbox, _fetch_inbox, _contacts_inbox, _chats_inbox
    global _group_inbox, _unread_inbox
    if ingest.v2_enabled() and _mark_inbox is None:
        _mark_inbox = ingest.MarkReadInbox("telegram")   # subscription in THIS loop (server) -> direct delivery
    if ingest.v2_enabled() and _reply_inbox is None:
        _reply_inbox = ingest.ReplyInbox("telegram")     # V2-521: dictated replies, same delivery path
    if ingest.v2_enabled() and _send_inbox is None:
        _send_inbox = ingest.SendInbox("telegram")       # V2-683: opening a conversation
    if ingest.v2_enabled() and _history_inbox is None:
        _history_inbox = ingest.HistoryAskInbox("telegram")   # V2-546: "load previous"
    if ingest.v2_enabled() and _fetch_inbox is None:
        _fetch_inbox = ingest.FetchInbox("telegram")     # V2-624: platform-wide pull
    if _contacts_inbox is None:
        _contacts_inbox = ingest.ContactsInbox("telegram")    # V2-714: the address book
    if _chats_inbox is None:
        _chats_inbox = ingest.ChatsInbox("telegram")          # the chat list
    if _group_inbox is None:
        _group_inbox = ingest.GroupInbox("telegram")          # new groups
    if _unread_inbox is None:
        _unread_inbox = ingest.MarkUnreadInbox("telegram")    # back to unread
    _set_status("connected", None)
    # Telethon dispatches updates only while the loop runs; this batching task coexists with that delivery.
    while True:
        await asyncio.sleep(config.batch_interval())
        if not _client.is_connected():
            try:
                await _client.connect()
            except Exception:
                _set_status("connecting", None)
                continue
        try:
            await _drain_inbox()
        except Exception as e:
            logger.debug(f"Telegram inbox tick: {e}")
        try:
            await _drain_reads()
        except Exception as e:
            logger.debug(f"Telegram reads tick: {e}")
        try:
            await _drain_replies()
        except Exception as e:
            logger.debug(f"Telegram replies tick: {e}")
        for what, fn in (("sends", _drain_sends), ("outbox", _drain_outbox),
                         ("read marks", _drain_read_marks),
                         ("history", _drain_history), ("fetch", _drain_fetch),
                         ("contacts", _drain_contacts), ("chats", _drain_chats), ("groups", _drain_groups),
                         ("unread", _drain_unread),
                         ("history walk", _walk_tick)):
            try:
                await fn()
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Telegram {what} tick: {e}")


def start() -> None:
    """Start the engine as a background task (call from server lifespan if TG_ENABLED=1)."""
    global _task
    if not enabled():
        _set_status("off", None)
        logger.info("Telegram: desactivado (TG_ENABLED!=1)")
        return
    if not config.has_credentials():
        _set_status("no_creds", None)
        logger.warning("Telegram: faltan TG_API_ID/TG_API_HASH en .env (sácalos de my.telegram.org). "
                       "El widget mostrará 'faltan credenciales'.")
        return
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    logger.info("Telegram: motor arrancado")


async def stop() -> None:
    global _task, _client
    if _task:
        _task.cancel()
        _task = None
    if _client is not None:
        try:
            await _client.disconnect()
        except Exception:
            pass
        _client = None


# The drains by concern, and the account operations (../account_ops.py); the loop and the tests reach them here.
from connectors.telegram.service.inbound import (  # noqa: E402
    _drain_inbox, _drain_outbox, _drain_read_marks, _normalize, _tg_media_type)
from connectors.telegram.service.history import (  # noqa: E402
    _drain_fetch, _drain_history, _drain_reads, _history_entry, _tg_msg_id)
from connectors.telegram.service.directory import _drain_contacts  # noqa: E402
from connectors.telegram.service.outbound import _drain_replies, _drain_sends  # noqa: E402
from connectors.telegram.account_ops import (  # noqa: E402
    _dialog_row, _drain_chats, _drain_groups, _drain_unread, _send, _walk_tick)
