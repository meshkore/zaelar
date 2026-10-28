#
# connectors/email/service — Email connector ENGINE integrated into zaelar (V2-051). Runs IN PROCESS in the server
# lifespan (UI-gated), as an asyncio task. Email is the CLEANEST of the three connectors: pure stdlib
# (imaplib/smtplib), NO Node bridge (WhatsApp), and no third-party lib (Telethon). Network logic lives in `mailbox/`
# and ALWAYS runs in asyncio.to_thread (IMAP/SMTP block) → never clogs the server event loop.
#
# Flow (stateless v2 production path, BRAIN=nucleo): IMAP/SMTP login → poll INBOX (BODY.PEEK, does not mark read)
# → publish NEW emails to the messaging widget (connector.msg), which triages/saves/notifies. Drains:
#   · msg.mark_read (MarkReadInbox) → mailbox.mark_seen (marks \Seen in IMAP).
#   · msg.reply      (ReplyInbox)   → mailbox.send_reply (SMTP with In-Reply-To/References threading).
# Direct duo/hermes path (fallback): triages with the shared classifier and writes the store like WhatsApp/Telegram.
#
# This module is the FACADE (refactor2710-13): state, loop and lifecycle live here; the drains (`inbound`, `orders`,
# `history`) are imported back and called through these globals, so patching `service._drain_fetch` governs the loop.
#
import asyncio

from loguru import logger

from connectors.email import config
from connectors.messaging import ingest, store

PLATFORM = "email"

_task: asyncio.Task | None = None
_seen: set[str] = set()          # already-seen IMAP UIDs (seeded on connect → only triage NEW email)
_published: set[str] = set()     # v2: UIDs already published to the bus (dedup before triage in the widget)

#: How many of the UNREAD backlog are handed to the widget on connect. A triage surface is a list somebody
#: READS; the rest of the mailbox stays in the mailbox, and the total travels as a fact instead (V2-606).
BACKFILL = 30

_unread_total: int = -1          # UNSEEN in INBOX at the last connect. -1 = not measured (never guessed as 0).


def _set_unread_total(n: int) -> None:
    global _unread_total
    _unread_total = int(n)


def seed_from_mailbox(mb) -> int:
    """Decide what the widget may EVER see, and record how much mail is really waiting. Returns the unread total.

    V2-606. This used to be `_seen.update(mb.all_uids())` inline in `_loop`, under the comment «only triage email
    that arrives AFTER connecting» — so the widget could only ever show mail that arrived after the connector
    started, and `_seen` lives in memory, so every restart moved that line forward again. Measured on the
    operator's real mailbox: **1110 in INBOX, 1088 UNSEEN**, all 1110 declared already-seen on connect. The
    connector authenticated, reported «Conectado» and showed him nothing, forever.

    The line is drawn where the operator already draws it: mail he has READ is dealt with and does not come back;
    mail he has NOT read is the thing he is asking to see.

    A triage surface is not a mailbox, so only the most recent `BACKFILL` unread are handed over — and that is
    exactly why the TOTAL is recorded. Silently hiding the other thousand is the failure being replaced; the
    count is what lets the agent say «tienes 1088 sin leer» instead of «no tienes mensajes nuevos sin leer»,
    which is what it said, over a full inbox (session `43b7bf79`).

    A FUNCTION and not four lines inside `_loop` because `_loop` connects to a real server: with the decision in
    there, a test can only re-implement it, and a re-implementation proves the test works, not the product. Three
    disarms came back green before this was extracted.
    """
    read, unread = mb.inbox_split()
    _seen.update(read)
    if len(unread) > BACKFILL:
        _seen.update(unread[:-BACKFILL])
    _set_unread_total(len(unread))
    logger.info(f"Email: {len(unread)} sin leer en INBOX; entran los {min(len(unread), BACKFILL)} más recientes")
    return len(unread)


def unread_total() -> int:
    """UNSEEN messages in the operator's INBOX as of the last connect, or -1 if we have not measured it.

    -1 and 0 are DIFFERENT and the difference is the whole point: «no lo sé» must never render as «no tienes
    ninguno», which is the sentence the agent said over 1088 unread mails.
    """
    return _unread_total


async def reseed() -> int:
    """Forget this connector's own memory of what it already delivered — called when Reset blanks the widget's
    store, so mail this connector handed over once does not become invisible FOREVER.

    `_seen`/`_published` are populated once at connect (`seed_from_mailbox`) and again on every real delivery
    (`_ingest_new`), and are otherwise cleared ONLY by `stop()` (a full disconnect). Reset
    (`widgets/reset.py` → `widgets/mensajeria/data.py::blank()`) wipes the widget's `items` AND its durable
    `taken` ledger, but it is a WIDGET-side operation and never touches a connector's own process state — so a
    message this connector already delivered once stays in `_seen` forever, and `fetch_new(seen=_seen, ...)`
    (`mailbox/reads.py`) skips it on every future poll. The widget forgot it; the connector still insists it was
    already handed over — genuinely unread mail vanishes from view until the engine restarts (which is the only
    thing that currently calls `stop()`).

    Measured live on the operator's engine: 1081 real unread in Gmail, zero reaching the widget, `taken` holding
    no `email:*` entry at all — exactly this. Releases only the most recent `BACKFILL` unread, the SAME shape
    `seed_from_mailbox` already produces on a fresh connect, so this cannot flood the widget with the whole
    backlog at once; the next poll tick's `_ingest_new` redelivers them normally, straight into the
    freshly-blanked store."""
    if not (_task and not _task.done()):
        return -1
    mb = config.mailbox()
    if mb is None:
        return -1
    ok, why = await asyncio.to_thread(mb.test_connection)
    if not ok:
        return -1
    read, unread = await asyncio.to_thread(mb.inbox_split)
    recent = set(unread[-BACKFILL:])
    _seen.difference_update(recent)
    _published.difference_update(recent)
    _set_unread_total(len(unread))
    return len(unread)
_shown: set[str] = set()         # direct path: messageIds already surfaced
_mark_inbox = None               # v2: msg.mark_read subscription (created in THIS loop)
_reply_inbox = None              # v2: msg.reply subscription (created in THIS loop)
_send_inbox = None               # V2-683: msg.send — writing to somebody who has not written
_unread_inbox = None             # msg.mark_unread — put a mail back to unread (the rehearsal rule)
_archive_inbox = None            # V2-543: msg.archive subscription
_trash_inbox = None              # V2-543: msg.trash subscription
_history_inbox = None            # V2-546: msg.history subscription ("load previous")
_fetch_inbox = None              # V2-624: msg.fetch subscription (platform-wide pull)
_mailbox_inbox = None            # msg.mailbox subscription (a folder page, or one message, for the card)


def enabled() -> bool:
    return config.enabled()


def _set_status(status: str, qr=None, detail=None) -> None:
    try:
        if ingest.v2_enabled():
            ingest.publish_status(PLATFORM, status, qr, detail)
        else:
            store.set_platform_status(PLATFORM, status, qr, detail)
    except Exception as e:
        logger.debug(f"Email set_status: {e}")


# The drains, imported back under their names (see the header): `_loop` and `_serve_demands` call these GLOBALS.
from .errors import _auth_failure_hint, _friendly_error  # noqa: E402,F401
from .history import _drain_fetch, _drain_history, _drain_mailbox  # noqa: E402
from .inbound import (  # noqa: E402,F401
    MIRROR_RECENT_S, _ingest_new, _media_dir, _poll_external_flags, _reread_first_page, on_screen, pages_to_reread)
from .orders import _drain_disposals, _drain_reads, _drain_replies, _drain_sends, _drain_unreads  # noqa: E402


async def _loop() -> None:
    global _mark_inbox, _reply_inbox, _send_inbox, _archive_inbox, _trash_inbox, _history_inbox, _fetch_inbox
    global _unread_inbox, _mailbox_inbox
    _set_status("starting", None, "Conectando con el servidor de correo…")
    mb = config.mailbox()
    if mb is None:
        _set_status("no_creds", None, "Faltan datos: dirección de correo y contraseña de aplicación.")
        logger.warning("Email: faltan credenciales (dirección/app-password/IMAP/SMTP) — el widget lo indicará")
        return
    _set_status("starting", None, f"Verificando IMAP y SMTP de {config.imap_host()}… (puede tardar unos segundos)")
    ok, why = await asyncio.to_thread(mb.test_connection)
    if not ok:
        logger.error(f"Email: no pude conectar: {why}")
        _set_status("error", None, _friendly_error(why))     # 'error' (not 'no_creds'): configured but failed → card with reason + retry
        return
    await asyncio.to_thread(seed_from_mailbox, mb)
    if ingest.v2_enabled():
        if _mark_inbox is None:
            _mark_inbox = ingest.MarkReadInbox(PLATFORM)
        if _reply_inbox is None:
            _reply_inbox = ingest.ReplyInbox(PLATFORM)
        if _send_inbox is None:
            _send_inbox = ingest.SendInbox(PLATFORM)
        if _unread_inbox is None:
            _unread_inbox = ingest.MarkUnreadInbox(PLATFORM)
        if _archive_inbox is None:
            _archive_inbox = ingest.ArchiveInbox(PLATFORM)
        if _trash_inbox is None:
            _trash_inbox = ingest.TrashInbox(PLATFORM)
        if _history_inbox is None:
            _history_inbox = ingest.HistoryAskInbox(PLATFORM)
        if _fetch_inbox is None:
            _fetch_inbox = ingest.FetchInbox(PLATFORM)
        if _mailbox_inbox is None:
            _mailbox_inbox = ingest.MailboxInbox(PLATFORM)
    _set_status("connected", None, f"Conectado como {config.address()}.")
    logger.info(f"Email conectado ({config.address()}) — escuchando tu buzón")
    global _demand_task
    if _demand_task is None or _demand_task.done():
        _demand_task = asyncio.create_task(_serve_demands(mb))
    while True:
        # What the OPERATOR is waiting for goes first (demo pass 48, 2026-09-29: the receipt's history order,
        # asked at E1, landed 43 s later — after this tick's new-mail fetch, flag poll and the rest, each its own
        # IMAP login — with «open it» and the forward already failed). `_nap` wakes on these same three orders.
        for what, fn in (("sends", _drain_sends), ("history", _drain_history), ("fetch", _drain_fetch),
                         ("mailbox", _drain_mailbox)):
            try:
                await fn(mb)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Email {what} tick (first): {e}")
        try:
            await _ingest_new(mb)
        except Exception as e:
            logger.debug(f"Email ingest tick: {e}")
        try:
            await _drain_reads(mb)
        except Exception as e:
            logger.debug(f"Email reads tick: {e}")
        try:
            await _drain_replies(mb)
        except Exception as e:
            logger.debug(f"Email reply tick: {e}")
        try:
            await _drain_disposals(mb)
        except Exception as e:
            logger.debug(f"Email disposal tick: {e}")
        for what, fn in (("sends", _drain_sends), ("unreads", _drain_unreads), ("flags", _poll_external_flags),
                         ("history", _drain_history), ("fetch", _drain_fetch)):
            try:
                await fn(mb)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Email {what} tick: {e}")
        await _nap(config.poll_interval())


_NAP_STEP_S = 0.5


def _on_demand() -> tuple:
    """The queues an operator waits on: a send, a history order, a pull, a folder page."""
    return (_history_inbox, _send_inbox, _fetch_inbox, _mailbox_inbox)
_demand_task: "asyncio.Task | None" = None


async def _serve_demands(mb) -> None:
    """The operator's on-demand orders — a send, a history fetch, a pull — served the moment they arrive, beside the
    poll loop instead of inside it (demo pass 48: an order that arrives while a tick is mid-housekeeping waited for
    the whole tick, 43 s, and the next two turns failed). Each drain opens its own IMAP/SMTP connection, so running
    beside the housekeeping costs nothing but a second login; a queue is taken once, so nothing is done twice."""
    while True:
        try:
            if any(i is not None and i.pending() for i in _on_demand()):
                for what, fn in (("sends", _drain_sends), ("history", _drain_history), ("fetch", _drain_fetch),
                                ("mailbox", _drain_mailbox)):
                    try:
                        await fn(mb)
                    except Exception as e:  # noqa: BLE001
                        logger.debug(f"Email {what} (on demand): {e}")
            await asyncio.sleep(_NAP_STEP_S)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Email demand loop: {e}")
            await asyncio.sleep(_NAP_STEP_S)


async def _nap(total: float) -> None:
    """Sleep until the next poll — or until an ON-DEMAND order arrives (demo pass 31, E2: «did inworld send me
    something?» asked the mailbox for the receipt, «open it» came 14 s later, and the mail landed 3 s after that:
    the history order had waited out the 20 s poll). A send, a history or a fetch order is the operator waiting."""
    loop = asyncio.get_running_loop()
    end = loop.time() + max(0.0, float(total))
    while loop.time() < end:
        if any(i is not None and i.pending() for i in _on_demand()):
            return
        await asyncio.sleep(min(_NAP_STEP_S, max(0.0, end - loop.time())))


def start() -> None:
    """Start the engine as a background task (server lifespan, if the connector is enabled from the UI)."""
    global _task
    if not enabled():
        _set_status("off", None)
        logger.info("Email: desactivado")
        return
    if not config.has_credentials():
        _set_status("no_creds", None, "Faltan datos: dirección de correo y contraseña de aplicación.")
        logger.warning("Email: activado pero faltan credenciales — el widget mostrará el formulario")
        return
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    logger.info("Email: motor arrancado")


async def stop() -> None:
    global _task, _mark_inbox, _reply_inbox, _send_inbox, _archive_inbox, _trash_inbox, _unread_inbox
    global _demand_task
    if _task:
        _task.cancel()
        _task = None
    if _demand_task:
        _demand_task.cancel()
        _demand_task = None
    for inbox in (_mark_inbox, _reply_inbox, _send_inbox, _archive_inbox, _trash_inbox, _unread_inbox):
        try:
            if inbox is not None:
                inbox.close()
        except Exception:
            pass
    _mark_inbox = _reply_inbox = _send_inbox = _archive_inbox = _trash_inbox = _unread_inbox = None
    _seen.clear()
    _set_unread_total(-1)
    _published.clear()
    _shown.clear()
