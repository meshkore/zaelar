"""A fake WORLD for an errand — one double, at the transport, and nothing else (V2-684).

An errand is the longest-lived thing the engine has: it is born from a confirmed order, it is bound to a
conversation by the connector's echo, it sleeps until somebody answers — now or in ten hours — and it
closes itself against the product's own truth. Every piece of that has unit coverage (V2-683, nodes 3.41
and 3.42) and the ARC has never run once, which is where all of its interesting behaviour lives.

## What is fake here, and what is deliberately not

FAKE: the transport. `World` stands exactly where a connector stands — it hears `msg.send`, it decides
whether the message really went out, it echoes the conversation it created, and it can make the other
person say something. That is the whole double.

REAL: everything above it. The widget's `send_to` action, the owner's flush (the secret scan included),
`watch.tick`'s three signals, `errands.start/bind/for_thread`, the wake, `party.parse`, `verify` and the
expiry sweep. A test that re-implements any of those measures the mirror rather than the product
(«un test que re-implementa no prueba el producto»).

The ONE other double belongs to the caller, not here: `wake._ask_model`, standing in for the party turn's
model with real-shaped JSON — because what is under test is what the ENGINE does with an answer, never
whether a model writes a good sentence.

## The clock

`advance()` moves the world's clock and nothing else. It is what makes «he answers in ten hours» cost no
seconds, and it is passed explicitly into `watch.tick(now)` so no test ever depends on the wall clock.
"""
from __future__ import annotations

import asyncio
import time


class World:
    """The outside of the engine: a transport that can deliver, fail, echo and answer."""

    def __init__(self, *, now: float | None = None):
        import bus
        from connectors.messaging import ingest
        self._ingest = ingest
        self._send_sub = bus.subscribe(ingest.TOPIC_SEND)
        self._failed_sub = bus.subscribe(ingest.TOPIC_SEND_FAILED)
        self.now = float(time.time() if now is None else now)
        self._sent: list[dict] = []          #: every order that really left, in order
        self._refused: list[dict] = []       #: every order the engine itself refused to publish
        self._n = 0

    # ── the clock ───────────────────────────────────────────────────────────────────────────────────────
    def advance(self, seconds: float) -> float:
        """Ten hours cost nothing. Returns the new now."""
        self.now += float(seconds)
        return self.now

    # ── the engine's side of the wire ───────────────────────────────────────────────────────────────────
    def act(self, action: str, payload: dict) -> None:
        """Run a messaging action through the REAL owner — the mutation AND every flush it performs.

        This is the product's only door out of the outbox: `_Owner.handle` is what applies the action and
        then pushes `pending_send` onto the bus, with `memory/secrets.py` scanning the text on the way.

        Synchronous on purpose, like `beat()`: an arc reads as a story, and every await in it would be
        ceremony around a coroutine that holds no loop state of its own.
        """
        from widgets.mensajeria import owner
        asyncio.run(owner._Owner().handle(action, payload or {}))

    def outbox(self) -> list[dict]:
        """Drain what the engine published as `msg.send` since the last call, and remember it as sent."""
        out = _drain(self._send_sub)
        self._sent.extend(out)
        return out

    def refusals(self) -> list[dict]:
        """Drain `msg.send_failed` — an order the engine itself refused (a leaked secret, a dead transport)."""
        out = _drain(self._failed_sub)
        self._refused.extend(out)
        return out

    def sent(self) -> list[dict]:
        """Everything that has left the engine so far, oldest first. Call `outbox()` first to catch up."""
        self.outbox()
        return list(self._sent)

    def texts(self) -> list[str]:
        return [str(o.get("text") or "") for o in self.sent()]

    # ── the transport's own moves ───────────────────────────────────────────────────────────────────────
    def deliver(self, order: dict, chat_id: str = "") -> str:
        """The message really went out, and the transport resolved which conversation it created.

        This is the echo that BIRTHS the errand (`connector.msg_out` carrying the order's `ref`) — the same
        publication the three real connectors make, outside their own try, for this exact reason.
        """
        chat = str(chat_id or order.get("chatId") or f"chat-{self._next()}")
        self._ingest.publish_msg_out(str(order.get("platform") or ""), {
            "chatId": chat, "messageId": f"out-{self._next()}", "ref": str(order.get("ref") or ""),
            "body": str(order.get("text") or ""), "senderName": "", "isGroup": False,
            "ts": self.now,
        })
        return chat

    def fail(self, order: dict, reason: str = "no se pudo enviar") -> None:
        """The message did NOT go out. No errand may be born for it."""
        self._ingest.publish_send_failed(dict(order or {}), reason)

    def say(self, platform: str, chat_id: str, text: str, *, name: str = "Iván Musikin",
            message_id: str = "") -> str:
        """The other person answers.

        Both halves, because the product needs both and a test doing only one measures a world that cannot
        exist: the message is WRITTEN into the thread store (what the owner's triage batch does, and what
        the wake's dossier reads) and PUBLISHED on the bus (what wakes the errand).
        """
        mid = message_id or f"in-{self._next()}"
        from connectors.messaging import store as msgstore
        from widgets.mensajeria import thread as _thread
        db = msgstore.load()
        _thread.append(db, platform, chat_id, {
            "senderName": name, "body": text, "messageId": mid, "chatId": chat_id,
            "senderId": chat_id, "isGroup": False, "ts": self.now,
        }, direction="in", name=name)
        msgstore.save(db)
        self._ingest.publish_msg(platform, {
            "senderName": name, "body": text, "messageId": mid, "chatId": chat_id,
            "senderId": chat_id, "isGroup": False, "ts": self.now,
        })
        return mid

    # ── the engine's beat ───────────────────────────────────────────────────────────────────────────────
    def beat(self, *, coalesced: bool = True) -> None:
        """One orchestrator pulse at the world's clock.

        `coalesced` advances past `watch.COALESCE_S` first, which is what a real beat four seconds later
        does: the wake deliberately waits for the owner's triage to have landed the message it is about to
        read. A test that wants to prove the coalesce ITSELF passes False.
        """
        from nucleo.errands import watch
        from widgets.mensajeria import owner
        if coalesced:
            self.advance(watch.COALESCE_S + 0.1)
        asyncio.run(watch.tick(self.now))
        # A beat is the whole pulse, not just the errand watcher: the messaging owner's own cycle is what
        # pushes the outbound queues onto the bus, with the secret scan on the way. A reply an errand
        # composes during the tick above leaves the engine HERE, one beat later, exactly as in production.
        owner._Owner()._flush_queues()

    def close(self) -> None:
        for sub in (self._send_sub, self._failed_sub):
            try:
                sub.close()
            except Exception:
                pass

    def _next(self) -> int:
        self._n += 1
        return self._n


def _drain(sub) -> list[dict]:
    q = getattr(sub, "queue", None)
    if q is None:
        return []
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except Exception:
            break
    return out


def answers(monkeypatch, *payloads: str):
    """Script the party turn's model: one JSON answer per wake, the last one repeating.

    It returns the recorder, so a test can assert what the model was SHOWN — which is how «the dossier
    carries three facts about the operator and nothing else» is measured by string rather than by reading
    the code.
    """
    from nucleo.errands import wake as wake_mod
    seq = list(payloads) or ["{}"]

    async def _fake(system: str, dossier: str, *, max_tokens: int = 0) -> str:
        # `max_tokens` is recorded, not ignored: the retry after an EMPTY answer is only a retry if it asks
        # for more room than the call that came back with nothing.
        _fake.calls.append({"system": system, "dossier": dossier, "max_tokens": max_tokens})
        return seq[min(len(_fake.calls) - 1, len(seq) - 1)]

    _fake.calls = []
    monkeypatch.setattr(wake_mod, "_ask_model", _fake)
    return _fake


def armed(monkeypatch, on: bool = True):
    """Take the errand OUT of shadow for one test — never by writing the operator's config file.

    Shadow is the shipped default and every arc runs under it; an arc that wants to see a message actually
    reach the transport says so here, explicitly, one test at a time.
    """
    from nucleo.errands import wake as wake_mod
    monkeypatch.setattr(wake_mod, "shadow", lambda: not on)


def agenda_holds(meeting: dict) -> None:
    """Put a meeting in the operator's agenda the way the product does — through its own store.

    `verify.meeting_exists` reads `agenda.view_data()`, so this writes what that reads, through the
    agenda's own loader. Nothing here touches the agenda's source: the store is a temp directory
    belonging to the test.

    ⚠️ It also stands in for a step that DOES NOT EXIST YET. Nothing in the engine turns an errand that
    reached «agreed» into a row in the agenda — the party turn holds no tools by design, and the link
    that was to close that gap (V2-683 row 6, the Meet invitation) is still blocked on
    `connectors/calendar/`. So an arc that verifies against the agenda is measuring the verifier, and
    saying so, rather than pretending the loop already closes by itself.
    """
    from widgets import store as wstore
    from widgets.agenda import data as agenda
    db = agenda.load_db()
    rows = list(db.get("meetings") or [])
    rows.append(dict(meeting))
    db["meetings"] = rows
    wstore.save(agenda.WIDGET_ID, db)
