#
# owner/apply.py — what the owner does with what the bus BROUGHT: messages he sent or read in his own app, failed
# sends, older history, chat-list and mailbox pages, the media sweep, the triage batch and the autoresponder.
#
from loguru import logger

from connectors.messaging import config as msgcfg
from connectors.messaging import ingest, notify
from connectors.messaging import store as msgstore


class _Apply:
    """The bus-event appliers and the triage half of `owner._Owner`."""


    def _apply_outbound(self) -> None:
        """A message the OPERATOR wrote in his own app. It joins the conversation and clears that chat's pending
        items — answering somewhere else IS having dealt with it, which is the whole report this came from."""
        for ev in self._drain(self._out_sub):
            platform = (ev or {}).get("platform")
            if not platform or ev.get("chatId") is None:
                continue
            body = dict(ev)
            body["from"] = ev.get("from") or ev.get("senderName") or ""
            # In a one-to-one chat the bridge names his own message after himself — never the chat's name (V2-819).
            chat_name = ev.get("chatName") or ""
            if not ev.get("isGroup") and chat_name and chat_name == (ev.get("senderName") or ""):
                chat_name = ""
            msgstore.record_outbound(platform, ev.get("chatId"), body, name=chat_name)
            # INFO, the far end of the trace the connector's log line starts: the message landed in the store (V2-616).
            logger.info(f"mensajeria: outbound {platform} message joined its thread ({ev.get('chatId')})")
            _f._record_left(ev)
            if ev.get("ref"):
                _f._settle(ev.get("ref"), True)
            # The directory learns WHO that conversation is (V2-693): the handle → chat id mapping the connector
            # resolved exists nowhere else, and dropping it makes one person two contacts.
            if ev.get("contactId"):
                try:
                    from widgets import directory
                    directory.note_reached(platform, ev.get("chatId"), str(ev.get("contactId")))
                except Exception as e:  # noqa: BLE001
                    logger.debug(f"mensajeria: no pude anotar el contacto del envío: {e}")

    def _apply_send_failures(self) -> None:
        """A send that did not leave (`msg.send_failed`, V2-819) settles the card's outbox row — the card keeps his
        text and says why — and the brain hears it once."""
        for ev in self._drain(self._failed_sub):
            ev = ev if isinstance(ev, dict) else {}
            reason = str(ev.get("reason") or "")
            logger.warning(f"mensajeria: a {ev.get('platform')} send did not leave ({ev.get('ref')}): {reason[:120]}")
            if ev.get("ref"):
                _f._settle(ev.get("ref"), False, reason)

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
                _f._note(f"[SISTEMA] No pude traer los mensajes anteriores de ese chat de "
                      f"{_f._LABEL.get(platform, platform)} ({ev['error']}). Díselo al operador.")
                continue
            msgstore.add_history(platform, ev.get("chatId"), ev.get("msgs") or [],
                                 complete=bool(ev.get("complete")),
                                 name=ev.get("name") or "", is_group=ev.get("isGroup"))

    def _sweep_media(self) -> None:
        """Once an hour: downloaded media older than the operator's window leaves this device (media.py)."""
        from widgets import store as _wstore
        from .. import media as _media
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
        from .. import mailbox as _mbx
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
        from .. import triage_agent

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
        # STORING IS NOT NOTIFYING (V2-607), two questions in this order:
        #   1. what is NEW  → all of it goes into its channel's section, unread, whatever the policy says
        #   2. of that, what may INTERRUPT → the policy decides (silent by default)
        db = msgstore.load()
        by_platform: dict[str, list[dict]] = {}
        for v in verdicts:
            who, group = _f._origin(v)
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
                await notify.announce(_f._LABEL.get(platform, platform), notice)

    def _auto_reply(self, platform: str, items: list[dict]) -> int:
        """The autoresponder (V2-624). The DECISION lives whole in `autorespond.py`: never a group, email only when
        addressed to him, inside the configured hours, once per chat per 24 h against a DURABLE ledger. The reply
        travels the same `msg.reply` seam a dictated reply uses. The original item is NOT marked read nor removed:
        an automatic «estoy fuera» announces the absence, the message still waits for him."""
        try:
            import time as _time
            from datetime import datetime
            from .. import autorespond
            # His standing rule is a FLOOR under the per-platform switch (V2-712): default no autoreply, read HERE
            # because this writes to people in his name with nobody in the loop. `autorespond.set_config` is the
            # release — enabling the responder writes `allow`; one half without the other breaks the feature.
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


from .. import owner as _f  # noqa: E402 — the facade: a patch on `owner.<name>` governs the calls above
