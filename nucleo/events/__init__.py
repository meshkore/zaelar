"""nucleo/events — what arrives without a turn, as a `Request` with its origin (V2-851 F4, §7).

One topic per source. An event is the same thing as a request he speaks — something that may need doing — whose
origin is the source instead of his voice, so it is routed by the same door: `nucleo.turn.flow_of.route(event=…)`.
The router answers one of three: a task WAITING for it (its row says `waiting_for = event:<topic>[:<key>]`, or a
claimant such as an errand bound to that conversation) is resumed; a rule SUBSCRIBED to it (`rules.subscriptions`)
hands it to the stream worker (`nucleo/events/stream.py`); else nothing (the source's own handling stands).

  · `event(topic, key=, text=, **fields)` — the event: `{origin, key, text, fields, at}`; the fields are DECLARED by
    the source (sender, platform, chat…), and a subscription matches on them, never on words;
  · `of_message(msg)` — an inbound connector message as its event (`mail.in` for mail, `connector.msg` else);
  · `pump.py` — the pulse's beat: drains the bus, routes, obeys the route.
"""
from __future__ import annotations

import time

CONNECTOR_MSG = "connector.msg"
MAIL_IN = "mail.in"
CRON_DUE = "cron.due"
WORKER_DONE = "worker.done"
WORKER_ASK = "worker.ask"
#: What a row waits for when it waits for an event: `event:<topic>` or `event:<topic>:<key>` (§3, `ledger.waiting`).
WAITING_PREFIX = "event:"


def event(topic: str, *, key: str = "", text: str = "", **fields) -> dict:
    """An event as a request with its origin. `key` is what a waiting task may name (a job id, a thread)."""
    return {"origin": str(topic), "key": str(key or ""), "text": str(text or "")[:2000],
            "fields": {k: v for k, v in fields.items() if v not in (None, "")}, "at": time.time()}


def waits_for(topic: str, key: str = "") -> str:
    """The `waiting_for` value of a row that waits for this event."""
    return f"{WAITING_PREFIX}{topic}" + (f":{key}" if key else "")


def of_message(msg: dict) -> dict:
    """An inbound connector message (`connector.msg` on the bus) as its event. Mail is its own stream."""
    m = dict(msg or {})
    platform = str(m.get("platform") or "")
    topic = MAIL_IN if platform == "email" else CONNECTOR_MSG
    return event(topic, key=f"{platform}:{m.get('chatId')}", text=str(m.get("body") or ""),
                 platform=platform, sender=str(m.get("senderId") or m.get("chatId") or ""),
                 name=str(m.get("senderName") or ""), chat=str(m.get("chatId") or ""),
                 subject=str(m.get("subject") or ""), message=str(m.get("messageId") or ""),
                 group=bool(m.get("isGroup")), _raw=m)
