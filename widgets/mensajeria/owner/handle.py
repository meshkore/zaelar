#
# owner/handle.py — operator and brain ACTIONS through the supervisor mailbox, and the flush that pushes every
# queued order onto the bus for the connectors (the one door a model-composed text is scanned at before it leaves).
#
from loguru import logger

from connectors.messaging import ingest
from connectors.messaging import store as msgstore


class _Handle:
    """The action door and the queue flush of `owner._Owner`."""


    # Operator / brain actions through the supervisor mailbox.
    async def handle(self, action: str, payload: dict) -> None:
        """Apply an action and, if something was marked read, publish msg.mark_read so the correct connector marks
        it in its app. Reuses the same mutation logic as the UI (data.apply_action). The owner is the only writer,
        so applying it here does not compete with anyone."""
        from .. import data
        # Mutation using the same vocabulary as UI buttons and [[msg.*]] tags.
        try:
            data.apply_action(action, payload or {})
        except Exception as e:
            logger.warning(f"mensajeria handle {action!r}: {e}")
            # V2-819 — a send the card is waiting on is answered even when applying it broke.
            if (payload or {}).get("ref") and action == "send_draft":
                _f._settle(payload["ref"], False, f"{type(e).__name__}")
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
                clean, leaked = _f._scrub(order.get("text") or "")
                if leaked:
                    ingest.publish_send_failed(order, f"contenía {leaked} — no se ha enviado")
                    _f._note(f"[SISTEMA] NO he enviado el mensaje a {order.get('name') or order.get('to')}: el "
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
            from .. import mailbox as _mbx
            db = msgstore.load()
            orders = _mbx.take_pending(db)
            if orders:
                msgstore.save(db)
            for order in orders:
                ingest.publish_mailbox_ask(order)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"mensajeria mailbox flush: {e}")


from .. import owner as _f  # noqa: E402 — the facade: a patch on `owner.<name>` governs the calls above
