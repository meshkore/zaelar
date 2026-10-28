#
# owner/lifecycle.py — the owner's LIFECYCLE: its bus subscriptions, start/stop, and the beat that flushes every
# queue each tick while triage runs beside it. `_BATCH` is read through the `owner` facade, so a patch there governs.
#
import asyncio

from loguru import logger

from connectors.messaging import ingest


class _Lifecycle:
    """Subscriptions, start/stop and the consumer beat of `owner._Owner`."""


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
        # No in-memory «seen» set: what he removed is kept from coming back by the DURABLE ledger in the store
        # (`msgstore.taken_ids`), since the provider re-delivers unread mail on every connect (V2-607).

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
            await asyncio.sleep(_f._BATCH)
            try:
                self._apply_status()
            except Exception as e:
                logger.debug(f"mensajeria owner status: {e}")
            # Triage runs BESIDE this loop, one batch at a time, never in front of his orders: its announcement can
            # wait for silence, and the queues below are flushed every tick whatever triage is doing.
            if self._triage_task is None or self._triage_task.done():
                self._triage_task = asyncio.create_task(self._triage_quietly())
            # The real apps moving on their own (V2-546), AFTER triage on purpose: a message he answered from his
            # phone clears the chat in the same tick, never surfaces a tick later as a notification.
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


from .. import owner as _f  # noqa: E402 — the facade: a patch on `owner.<name>` governs the calls above
