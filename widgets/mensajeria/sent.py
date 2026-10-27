"""sent.py — what this card SENT, as rows a verifier can read (V2-776 L2).

`threads[*].msgs` with `dir == "out"` is the record of what left, and `pending_send` what is still leaving.
Neither was a declared collection (`threads` is a dict), so «a Telegram to Rowan saying 4:30 went out» — the
postcondition `send_to` declares — could not be attested. This flattens both into `view_data()["sent"]`.
"""
from __future__ import annotations

import time

_MAX = 60


def rows(db: dict) -> list[dict]:
    out: list[dict] = []
    for k, th in (db.get("threads") or {}).items():
        if not isinstance(th, dict):
            continue
        plat, _sep, chat_id = str(k).partition("|")
        for m in th.get("msgs") or []:
            if not isinstance(m, dict) or m.get("dir") != "out":
                continue
            try:
                ts = float(m.get("ts") or 0)
            except (TypeError, ValueError):
                ts = 0.0
            out.append({"id": str(m.get("id") or ""), "platform": plat, "chatId": chat_id,
                        "name": str(th.get("name") or ""), "body": str(m.get("body") or ""), "ts": ts,
                        "queued": False})
    for o in db.get("pending_send") or []:
        if isinstance(o, dict):
            out.append({"id": str(o.get("ref") or ""), "platform": str(o.get("platform") or ""),
                        "chatId": str(o.get("chatId") or o.get("to") or ""), "name": str(o.get("name") or o.get("to") or ""),
                        "body": str(o.get("text") or ""), "ts": float(o.get("at") or time.time()), "queued": True,
                        # V2-800: a send he asked for LATER — the card shows when, and `cancel_send` stops it.
                        **({"scheduled_for": float(o["not_before"])} if o.get("scheduled") and float(o.get("not_before") or 0) > time.time() else {})})
    out.sort(key=lambda r: -float(r.get("ts") or 0))
    return out[:_MAX]


#: V2-807 T-12 — how much of a body that LEFT goes on the timeline: enough to hold a whole ordinary message.
LEFT_BODY_MAX = 4000


def left_event(ev: dict) -> dict | None:
    """What the timeline records when a send made HERE comes back from its connector as sent: the body as it left
    (signature included — the connector adds it), who it went to, and the order's `ref`. A message he typed in his
    own app is not this card's send and records nothing here. None when `ev` is not one of ours."""
    ev = ev if isinstance(ev, dict) else {}
    ours = bool(ev.get("ref")) or str(ev.get("messageId") or "").startswith("sent:")
    body = str(ev.get("body") or ev.get("text") or "")
    if not ours or not body.strip():
        return None
    return {"text": body[:LEFT_BODY_MAX],
            "extra": {"platform": str(ev.get("platform") or ""), "to": str(ev.get("chatId") or ""),
                      "name": str(ev.get("chatName") or ""), "ref": str(ev.get("ref") or ""),
                      "chars": len(body), "cut": len(body) > LEFT_BODY_MAX}}


# ── V2-819 · a send from his own hand is answered: sent, or not and why ────────────────────────────────────
# The card's Send used to clear the box the moment the order was QUEUED. Nothing after that reached the card: the
# owner applies the order in its mailbox and drops what the action returns, the reply drains of the connectors only
# told the brain, and `msg.send_failed` had no subscriber at all. So a send that never left looked exactly like one
# that did. The OUTBOX is one row per send the card made, keyed by the order's `ref`, settled by whoever learns the
# outcome first (the owner's own refusal, the connector's echo, the connector's failure) — and the card keeps his
# text until its row says «sent».

#: A row nobody settled in this long is reported as unconfirmed: a connector that is not running never answers.
OUTBOX_STALE_S = 120.0
#: How long a settled row stays readable by the card, so a repaint after the outcome still sees it.
OUTBOX_KEEP_S = 600.0
_OUTBOX_MAX = 40


def outbox_queue(db: dict, ref: str, platform: str, chat_id, key: str, text: str) -> dict:
    """Record a send the card just made. `key` is the composer's own conversation key, so the card finds its row."""
    row = {"ref": str(ref), "platform": str(platform or ""), "chatId": str(chat_id or ""), "key": str(key or ""),
           "text": str(text or "")[:4000], "state": "queued", "reason": "", "at": time.time()}
    rows = [r for r in (db.get("outbox") or []) if isinstance(r, dict) and r.get("ref") != row["ref"]]
    db["outbox"] = (rows + [row])[-_OUTBOX_MAX:]
    return row


def outbox_settle(db: dict, ref, ok: bool, reason: str = "") -> bool:
    """The outcome of the send `ref`. Only a QUEUED row moves: a late echo never turns a failure into a success,
    nor a failure reported twice into two. Returns True when a row changed."""
    for r in db.get("outbox") or []:
        if isinstance(r, dict) and r.get("ref") == str(ref or "") and r.get("state") == "queued":
            r["state"] = "sent" if ok else "failed"
            r["reason"] = "" if ok else str(reason or "")[:300]
            r["settled"] = time.time()
            return True
    return False


def outbox_view(db: dict, now: float | None = None) -> list[dict]:
    """The rows the card reads. A queued row past `OUTBOX_STALE_S` is shown as `unconfirmed`: not a claim that it
    failed, only that nothing has said it left."""
    now = float(now if now is not None else time.time())
    out = []
    for r in db.get("outbox") or []:
        if not isinstance(r, dict):
            continue
        at = float(r.get("settled") or r.get("at") or 0)
        if now - at > OUTBOX_KEEP_S:
            continue
        row = dict(r)
        if row.get("state") == "queued" and now - float(row.get("at") or 0) > OUTBOX_STALE_S:
            row["state"] = "unconfirmed"
        out.append(row)
    return out
