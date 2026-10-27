#
# owner.py: live backend for the messaging widget (V2-008, kind:"backed", gate:"nucleo"). This closes the v2
# central-diagram reshape: connectors (WhatsApp/Telegram) publish incoming messages to the bus (connector.msg) and
# their link status (connector.status); this owner consumes them, triages with its internal agent (LOCAL model,
# privacy), dumps durable content to central memory, proactively notifies only relevant items, and reflects
# everything into the widget UI store. It is the ONLY WRITER of widgets/_data/mensajeria/ (backed contract:
# data.py/widget.js become read + enqueue faces; operator/brain actions arrive through the supervisor mailbox ->
# handle()).
#
# Mark-read is symmetrical: a read/clear/readchat action does NOT talk to any app directly. It publishes
# msg.mark_read to the bus, which the connector for the correct platform drains and executes in its app. The owner
# does not know WhatsApp or Telegram, only the bus. Connectors are genuinely stateless.
#
# STRANGLER-FIG: the supervisor only starts this owner with BRAIN=nucleo (manifest gate). Under duo/hermes, the
# widget behaves as the previous passive version (owner does NOT run -> actions fall to data.apply_action and
# connectors write the store through their direct path). Zero regression until burial (V2-009).
#
import asyncio
import os

from loguru import logger

from connectors.messaging import config as msgcfg
from connectors.messaging import ingest, notify
from connectors.messaging import store as msgstore

_LABEL = {"whatsapp": "WhatsApp", "telegram": "Telegram", "email": "Email"}
_BATCH = float(os.getenv("MSG_TRIAGE_BATCH", "2.0"))   # seconds between triage batches; groups bursts into one call


def _note(text: str) -> None:
    """Tell the operator through the brain's inbox. Used for the failures he cannot see any other way — the
    same seam the connectors use for a send that did not go out."""
    try:
        from voice import brain_notes
        brain_notes.push(text)
    except Exception:
        pass


def _scrub(text: str) -> tuple[str, str]:
    """V2-683 — the last door before a MODEL-composed text leaves toward somebody outside. Returns
    `(text, "")` when it is clean and `(text, what)` when it is not, and the caller does not send.

    It FAILS CLOSED, and deliberately does not redact-and-send: a reply's text is dictated by the operator
    and goes to a conversation he is already in, but this one was written by a model for a third party, so a
    secret inside it is either a mistake or an injection, and both are answered by stopping rather than by
    delivering a redacted version he never got to read. `memory/secrets.py` is the same detector the worker
    bridge already runs on anything leaving through `push_channel`."""
    try:
        from memory import secrets as _secrets
        found = _secrets.detect(text or "")
    except Exception as e:  # noqa: BLE001 — a scan that could not run is not a licence to send
        logger.warning(f"mensajeria: no pude revisar el texto saliente ({e!r}) — no se envía")
        return (text, "un texto que no he podido revisar")
    if found:
        kinds = sorted({str(getattr(f, "kind", "") or "un secreto") for f in found})
        return (text, ", ".join(kinds))
    return (text, "")


def _origin(m: dict) -> tuple[str, str | None]:
    if m.get("isGroup"):
        return (m.get("senderName") or "?", m.get("chatName") or "grupo")
    return (m.get("senderName") or "?", None)


class _Owner:
    """Owner of the messaging widget. Lifecycle governed by widgets/supervisor.py (start/stop/handle + restart)."""

    def __init__(self):
        self._msg_sub = None
        self._status_sub = None
        self._out_sub = None              # V2-546: what the operator sent from his own app
        self._read_sub = None             # V2-546: what he read there
        self._history_sub = None          # V2-546: older messages a connector went and fetched
        self._chats_sub = None            # one page of a platform's chat list
        self._mailbox_sub = None          # one page of a mail folder, or one message read whole
        self._failed_sub = None           # V2-819: a send that did not leave, with the reason
        self._task: asyncio.Task | None = None
        self._triage_task: asyncio.Task | None = None
        # NOTE (V2-607): the in-memory `_seen` set that used to live here is gone. It claimed to stop resurrecting
        # what the operator removed and could not: it started empty on every boot, while the mail it was meant to
        # suppress is still UNREAD at the provider and gets re-delivered on every connect. The ledger that
        # actually holds that promise is durable, in the store — `msgstore.taken_ids`.

    # Lifecycle.
    async def start(self) -> None:
        """Cheap: only subscribe to the bus and launch the consumer. Idempotent; the supervisor may restart us."""
        import bus
        if self._msg_sub is None:
            self._msg_sub = bus.subscribe(ingest.TOPIC_MSG)
        if self._status_sub is None:
            self._status_sub = bus.subscribe(ingest.TOPIC_STATUS)
        if self._out_sub is None:
            self._out_sub = bus.subscribe(ingest.TOPIC_MSG_OUT)
        if self._read_sub is None:
            self._read_sub = bus.subscribe(ingest.TOPIC_READ)
        if self._history_sub is None:
            self._history_sub = bus.subscribe(ingest.TOPIC_HISTORY)
        if self._chats_sub is None:
            self._chats_sub = bus.subscribe(ingest.TOPIC_CHATS)
        if self._mailbox_sub is None:
            self._mailbox_sub = bus.subscribe(ingest.TOPIC_MAILBOX)
        if self._failed_sub is None:
            self._failed_sub = bus.subscribe(ingest.TOPIC_SEND_FAILED)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._consume())
        logger.info("mensajeria owner started (triage in widget; stateless connectors)")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        if self._triage_task:
            self._triage_task.cancel()
            self._triage_task = None
        for sub in (self._msg_sub, self._status_sub, self._out_sub, self._read_sub, self._history_sub,
                    self._chats_sub, self._mailbox_sub, self._failed_sub):
            try:
                if sub is not None:
                    sub.close()
            except Exception:
                pass
        self._msg_sub = self._status_sub = None
        self._out_sub = self._read_sub = self._history_sub = self._chats_sub = self._mailbox_sub = None
        self._failed_sub = None

    # Bus consumption: incoming messages + status.
    async def _consume(self) -> None:
        while True:
            await asyncio.sleep(_BATCH)
            try:
                self._apply_status()
            except Exception as e:
                logger.debug(f"mensajeria owner status: {e}")
            # Triage runs BESIDE this loop, one batch at a time — never in front of the operator's orders. Demo pass
            # 45 (2026-09-29): «did inworld send me something?» queued the receipt's history fetch, and it left two
            # minutes later, with E2 and E3 already failed on a card that did not hold it — the loop was parked in
            # `_triage_batch`, whose announcement waits for silence in a conversation that had none. The queues
            # below are flushed every tick whatever triage is doing.
            if self._triage_task is None or self._triage_task.done():
                self._triage_task = asyncio.create_task(self._triage_quietly())
            # V2-546 — the real apps moving on their own. These run AFTER triage on purpose: a message the
            # operator answered from his phone should reach the conversation and clear the chat in the same
            # tick it would otherwise have been surfaced in, not one tick later as a notification he has
            # already dealt with.
            for what, fn in (("outbound", self._apply_outbound), ("failed", self._apply_send_failures),
                             ("read", self._apply_external_reads),
                             ("history", self._apply_history), ("chats", self._apply_chats),
                             ("mailbox", self._apply_mailbox),
                             ("media", self._sweep_media), ("queues", self._flush_queues)):
                try:
                    fn()
                except Exception as e:  # noqa: BLE001
                    logger.debug(f"mensajeria owner {what}: {e}")

    @staticmethod
    def _drain(sub) -> list[dict]:
        q = sub.queue if sub else None
        if q is None:
            return []
        out = []
        while True:
            try:
                out.append(q.get_nowait())
            except Exception:
                break
        return out

    def _apply_outbound(self) -> None:
        """A message the OPERATOR wrote in his own app. It joins the conversation and clears that chat's pending
        items — answering somewhere else IS having dealt with it, which is the whole report this came from."""
        for ev in self._drain(self._out_sub):
            platform = (ev or {}).get("platform")
            if not platform or ev.get("chatId") is None:
                continue
            body = dict(ev)
            body["from"] = ev.get("from") or ev.get("senderName") or ""
            # V2-819 — in a one-to-one chat, the bridge names a message HE sent after its sender: himself. That is
            # not the conversation's name, and storing it titled the chat with his own name.
            chat_name = ev.get("chatName") or ""
            if not ev.get("isGroup") and chat_name and chat_name == (ev.get("senderName") or ""):
                chat_name = ""
            msgstore.record_outbound(platform, ev.get("chatId"), body, name=chat_name)
            # V2-616 — INFO, the far end of the same trace the connector's own log line starts: the operator
            # reported his own reply never reaching the widget, and the whole pipeline was silent on success
            # end to end. This confirms the message actually landed in the store, not just that the bus saw it.
            logger.info(f"mensajeria: outbound {platform} message joined its thread ({ev.get('chatId')})")
            _record_left(ev)
            if ev.get("ref"):
                _settle(ev.get("ref"), True)
            # V2-693 — and the directory learns WHO that conversation is. The connector resolved a handle
            # into a chat id to make this send; that mapping exists nowhere else, and dropping it is what
            # let one person become two contacts.
            if ev.get("contactId"):
                try:
                    from widgets import directory
                    directory.note_reached(platform, ev.get("chatId"), str(ev.get("contactId")))
                except Exception as e:  # noqa: BLE001
                    logger.debug(f"mensajeria: no pude anotar el contacto del envío: {e}")

    def _apply_send_failures(self) -> None:
        """V2-819 — `msg.send_failed` had publishers and no reader: a send that did not leave was told to nobody.
        It settles the card's outbox row (the card keeps his text and says why) and the brain hears it once."""
        for ev in self._drain(self._failed_sub):
            ev = ev if isinstance(ev, dict) else {}
            reason = str(ev.get("reason") or "")
            logger.warning(f"mensajeria: a {ev.get('platform')} send did not leave ({ev.get('ref')}): {reason[:120]}")
            if ev.get("ref"):
                _settle(ev.get("ref"), False, reason)

    def _apply_external_reads(self) -> None:
        for ev in self._drain(self._read_sub):
            platform = (ev or {}).get("platform")
            if not platform or ev.get("chatId") is None:
                continue
            msgstore.apply_external_read(platform, ev.get("chatId"),
                                         upto_ts=ev.get("uptoTs"), ids=ev.get("ids"))

    def _apply_history(self) -> None:
        """Older messages a connector fetched. An `error` is NOT swallowed: the operator pressed a button and a
        request that could not be served has to say so, or a silent no-op reads as 'there is nothing older'."""
        for ev in self._drain(self._history_sub):
            platform = (ev or {}).get("platform")
            if not platform or ev.get("chatId") is None:
                continue
            if ev.get("error"):
                _note(f"[SISTEMA] No pude traer los mensajes anteriores de ese chat de "
                      f"{_LABEL.get(platform, platform)} ({ev['error']}). Díselo al operador.")
                continue
            msgstore.add_history(platform, ev.get("chatId"), ev.get("msgs") or [],
                                 complete=bool(ev.get("complete")),
                                 name=ev.get("name") or "", is_group=ev.get("isGroup"))

    def _sweep_media(self) -> None:
        """Once an hour: downloaded media older than the operator's window leaves this device (media.py)."""
        from widgets import store as _wstore
        from . import media as _media
        db = msgstore.load()
        if not _media.due(db):
            return
        res = _media.sweep(db, _wstore.data_dir("mensajeria"))
        msgstore.save(db)
        if res["files"] or res["messages"]:
            logger.info(f"mensajeria: media older than {_media.days(db)} d removed — {res['files']} file(s), "
                        f"{res['bytes'] / 1e6:.0f} MB, {res['messages']} message(s) now point to the phone")

    def _apply_chats(self) -> None:
        """One page of a platform's chat list. An error is kept on the index, so the list can say why it is
        short instead of looking like an account with no conversations."""
        for ev in self._drain(self._chats_sub):
            platform = (ev or {}).get("platform")
            if platform:
                msgstore.add_chats(platform, ev)
                if ev.get("error"):
                    logger.warning(f"mensajeria: {platform} chat list page failed: {ev['error']}")

    def _apply_mailbox(self) -> None:
        """A mail folder page, or one message read whole, for the email section (mailbox.py)."""
        events = [ev for ev in self._drain(self._mailbox_sub) if (ev or {}).get("platform") == "email"]
        if not events:
            return
        from . import mailbox as _mbx
        db = msgstore.load()
        for ev in events:
            _mbx.fold(db, ev)
            if ev.get("error"):
                logger.warning(f"mensajeria: mail folder {ev.get('folder')!r} answered with {ev['error']}")
        msgstore.save(db)

    def _apply_status(self) -> None:
        """Reflect pending connector.status events into the UI store; the owner is the only writer."""
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

    async def _triage_quietly(self) -> None:
        try:
            await self._triage_batch()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"mensajeria owner triage: {e}")

    async def _triage_batch(self) -> None:
        """Drain the accumulated incoming-message batch, triage it, surface relevant items, save them to UI store
        and memory, and notify. Grouped by platform for upsert and notification."""
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
        # V2-607 — STORING IS NOT NOTIFYING. This used to be one decision: `notify.surface` filtered by the
        # notification policy and whatever survived was BOTH saved and announced, so anything the policy did not
        # care about never reached his inbox at all. With the policy now defaulting to silence (his direction,
        # 2026-09-07) that single gate would have emptied the widget completely — the exact failure V2-606 had
        # just fixed. So the two questions are asked separately, in this order:
        #   1. what is NEW  → everything of it goes into its channel's section, unread, whatever the policy says
        #   2. of that, what may INTERRUPT → almost always nothing, until he asks to be told
        db = msgstore.load()
        by_platform: dict[str, list[dict]] = {}
        for v in verdicts:
            who, group = _origin(v)
            v["from"], v["group"] = who, group
            by_platform.setdefault(v.get("platform") or "?", []).append(v)
        for platform, batch_items in by_platform.items():
            if platform == "?":
                continue
            items = msgstore.new_among(db, platform, batch_items)
            if not items:
                continue
            msgstore.upsert_items(platform, items)   # UI store + memory dump (kind='msg')
            self._auto_reply(platform, items)        # V2-624: the autoresponder, AFTER storing, never instead
            notice = notify.deserving(items)
            logger.info(f"mensajeria: +{len(items)} from {platform} ({len(notice)} avisan)")
            if notice:
                await notify.announce(_LABEL.get(platform, platform), notice)

    def _auto_reply(self, platform: str, items: list[dict]) -> int:
        """V2-624 — the autoresponder (the 'Phase 4' the WhatsApp client has long named, now with its
        go-ahead). The DECISION lives whole in `widgets/mensajeria/autorespond.py` (zero-import, like policy.py):
        never a group, email only when addressed to him, inside the configured hours, once per chat per 24 h
        against a DURABLE ledger. The reply travels the SAME `msg.reply` seam a dictated reply uses — each
        connector's already-tested send path, echoed into the thread by the existing outbound-capture seams.
        Deliberately: the original item is NOT marked read and NOT removed — an automatic «estoy fuera» does
        not deal with the message, it announces the absence; the message still waits for him."""
        try:
            import time as _time
            from datetime import datetime
            from . import autorespond
            # V2-712 — THE OPERATOR'S STANDING RULE IS A FLOOR UNDER THE PER-PLATFORM SWITCH. His words,
            # 2026-09-16: «por defecto no autorrespondemos ningún mensaje de ningún tipo. Eso es una regla de
            # usuario que viene preseteada en el Génesis. Pero si el usuario decide cambiarla, que la cambie.»
            # This is the engine writing to real people in his name with nobody in the loop, so the rule is
            # read HERE and not only where the switch is flipped. The other half is in `autorespond.set_config`:
            # enabling the responder IS him changing the rule, so it writes `allow` — both halves ship
            # together, because a floor without its release silently kills a feature he already turned on.
            from nucleo import consent as _consent
            if _consent.class_policy(_consent.act_key("messaging.autorespond", platform)) == "never":
                return 0
            db = msgstore.load()
            if not autorespond.config_for(db, platform)["enabled"]:
                return 0
            now_ts = _time.time()
            now = datetime.now()
            sent = 0
            for it in items:
                text = autorespond.should_reply(db, it, now_ts, (now.hour, now.minute))
                if not text:
                    continue
                ingest.publish_reply({
                    "platform": platform, "chatId": it.get("chatId"),
                    "to": it.get("senderId") or it.get("chatId"),
                    "messageId": it.get("messageId"), "subject": it.get("subject", ""),
                    "msgid": it.get("msgid", ""), "text": text,
                })
                autorespond.note_replied(db, platform, it.get("chatId"), now_ts)
                sent += 1
            if sent:
                msgstore.save(db)      # the ledger is durable ON PURPOSE (V2-607: memory guards cannot dedupe)
                logger.info(f"mensajeria: autoresponder replied to {sent} chat(s) on {platform}")
            return sent
        except Exception as e:  # noqa: BLE001
            logger.warning(f"mensajeria autoresponder: {e}")
            return 0

    # Operator / brain actions through the supervisor mailbox.
    async def handle(self, action: str, payload: dict) -> None:
        """Apply an action and, if something was marked read, publish msg.mark_read so the correct connector marks
        it in its app. Reuses the same mutation logic as the UI (data.apply_action). The owner is the only writer,
        so applying it here does not compete with anyone."""
        from . import data
        # Mutation using the same vocabulary as UI buttons and [[msg.*]] tags.
        try:
            data.apply_action(action, payload or {})
        except Exception as e:
            logger.warning(f"mensajeria handle {action!r}: {e}")
            # V2-819 — a send the card is waiting on is answered even when applying it broke.
            if (payload or {}).get("ref") and action == "send_draft":
                _settle(payload["ref"], False, f"{type(e).__name__}")
            return
        self._flush_queues()

    def _flush_queues(self) -> None:
        """Push everything the store has queued onto the bus, for the connectors to execute.

        ⚠️ Called from BOTH the action door and the owner's own beat, and the second caller is the fix for a
        defect the V2-684 arc found (2026-09-13): an errand composes its reply through `wake._send`, which
        queues it here exactly as a dictated reply is queued — and this flush only ever ran inside
        `handle()`. With no operator action on the messaging widget, the reply sat in `pending_send`
        forever, so an ARMED errand would have answered nobody. It was invisible because the feature ships
        in SHADOW, where there is nothing to flush.

        The flush deliberately stays HERE and is not moved next to the errand: this is the one door where
        `memory/secrets.py` reads a text written by a MODEL for somebody outside the house.
        """
        try:
            for key in msgstore.take_pending_read():
                ingest.publish_mark_read(key)
        except Exception as e:
            logger.debug(f"mensajeria mark_read flush: {e}")
        try:
            for key in msgstore.take_pending_unread():
                ingest.publish_mark_unread(key)
        except Exception as e:
            logger.debug(f"mensajeria mark_unread flush: {e}")
        # Same for replies to send (V2-051): that platform's connector, today email, sends them.
        try:
            for rep in msgstore.take_pending_reply():
                ingest.publish_reply(rep)
        except Exception as e:
            logger.debug(f"mensajeria reply flush: {e}")
        # And for a message to a PERSON (V2-683) — the order that OPENS a conversation instead of answering
        # one. Same shape, one door later: the last thing it passes through before leaving the engine is the
        # secret scan, because unlike every other queue here the text was composed by a MODEL and its
        # destination is somebody outside.
        try:
            for order in msgstore.take_pending_send():
                clean, leaked = _scrub(order.get("text") or "")
                if leaked:
                    ingest.publish_send_failed(order, f"contenía {leaked} — no se ha enviado")
                    _note(f"[SISTEMA] NO he enviado el mensaje a {order.get('name') or order.get('to')}: el "
                          f"texto llevaba dentro {leaked}. Díselo al operador y no lo reintentes.")
                    continue
                ingest.publish_send({**order, "text": clean})
        except Exception as e:
            logger.debug(f"mensajeria send flush: {e}")
        # And for archive/delete orders (V2-543): the platform's connector executes them in the real mailbox.
        try:
            for key in msgstore.take_pending_disposal("archive"):
                ingest.publish_archive(key)
            for key in msgstore.take_pending_disposal("trash"):
                ingest.publish_trash(key)
        except Exception as e:
            logger.debug(f"mensajeria disposal flush: {e}")
        # And for "load previous" orders (V2-546): the platform's connector goes and fetches them.
        try:
            for order in msgstore.take_pending_history():
                ingest.publish_history_ask(order)
        except Exception as e:
            logger.debug(f"mensajeria history flush: {e}")
        # And for platform-wide pull orders (V2-624): «chupar más mensajes» / the activity-window fetch.
        try:
            for order in msgstore.take_pending_fetch():
                ingest.publish_fetch(order)
        except Exception as e:
            logger.debug(f"mensajeria fetch flush: {e}")
        # And for new groups (create_group).
        try:
            for order in msgstore.take_pending_group():
                ingest.publish_group(order)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"mensajeria group flush: {e}")
        # And for chat-list pages: entering a platform, or «Cargar más» at the bottom of its list.
        try:
            for order in msgstore.take_pending_chats():
                ingest.publish_chats_ask(order)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"mensajeria chats flush: {e}")
        # And for the email section's folder pages and opened messages.
        try:
            from . import mailbox as _mbx
            db = msgstore.load()
            orders = _mbx.take_pending(db)
            if orders:
                msgstore.save(db)
            for order in orders:
                ingest.publish_mailbox_ask(order)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"mensajeria mailbox flush: {e}")


# Single instance governed by the supervisor (contract: async start()/stop()/handle(action,payload)).
_OWNER = _Owner()


async def start() -> None:
    await _OWNER.start()


async def stop() -> None:
    await _OWNER.stop()


async def handle(action: str, payload: dict) -> None:
    await _OWNER.handle(action, payload)


def _settle(ref, ok: bool, reason: str = "") -> None:
    """Settle the card's outbox row for the send `ref` (V2-819). Never raises: bookkeeping is not the send."""
    try:
        from . import sent as _sent
        db = msgstore.load()
        if _sent.outbox_settle(db, ref, ok, reason):
            msgstore.save(db)
    except Exception as e:  # noqa: BLE001
        logger.info(f"mensajeria: outbox row {ref} not settled ({type(e).__name__}: {e})")


def _record_left(ev: dict) -> None:
    """V2-807 T-12 — the body a send of this card LEFT with, on the timeline (`sent.left_event`): what was sent is
    then read from the record, never rebuilt from the conversation that wrote it."""
    from . import sent as _sent
    rec = _sent.left_event(ev)
    if rec is None:
        return
    try:
        from voice.observer import emit
        emit("widget", "sent", text=rec["text"], extra={"id": "mensajeria", **rec["extra"]})
    except Exception as e:  # noqa: BLE001 — bookkeeping never breaks the owner's loop
        logger.info(f"mensajeria: the sent body was not recorded ({type(e).__name__}: {e})")
