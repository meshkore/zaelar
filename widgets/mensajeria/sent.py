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
                        "body": str(o.get("text") or ""), "ts": float(o.get("at") or time.time()), "queued": True})
    out.sort(key=lambda r: -float(r.get("ts") or 0))
    return out[:_MAX]
