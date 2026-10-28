"""nucleo/pulse/notices.py — the ONE door for a notice the agent owes the operator, and the ledger of how it ended (V2-796).

A reminder that rings, a commission that finished, an approval the agent is waiting on: each is a ROW in `notices`
(`memory/schema.py`), keyed by a `dedupe_key`, and each row ends in exactly one state:

    spoken   said by voice while he was in front of a screen
    pushed   accepted by the push service for ≥ 1 of his devices (Web Push)
    covered  another system he uses rings for it (a Google Calendar alarm) — we stay quiet on purpose
    shown    painted on a screen that connected later (the owed list drains there)
    seen     he opened it (notification click)
    owed     nobody could take it yet: retried with backoff, and drained to the next screen that opens

Three properties, each with its test (`tests/agent_headless/unit/test_notice_ledger.py`):
  · NEVER TWICE — `dedupe_key` is UNIQUE. A second emit for the same key (a restart that re-fires a job, two doors
    announcing the same finish) returns the existing row and delivers nothing.
  · NEVER LOST — a notice no channel could take stays `owed`; it is retried, and the next screen shows it.
  · ⏻ SILENCES THE VOICE, NOT THE LOCK SCREEN — stopped, nothing is spoken; a push still goes out.

Which notices push is DECLARED by the caller (`notify(..., push=True)` is the default only here), never guessed
from the words: `voice/proactive.notify` stays the voice door for everything else, interim lines included.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time

logger = logging.getLogger("zaelar.notices")

#: How long someone must have touched a screen for a spoken notice to count as HEARD. A desktop tab left visible on
#: an empty desk is not an audience; past this, the phone is told as well.
PRESENT_S = 15 * 60
#: Retry schedule for an owed notice (seconds after each failed attempt), then it waits for a screen.
_BACKOFF_S = (60, 300, 900, 1800, 3600)
_RETRY_FOR_S = 24 * 3600
_RETRY_EVERY_S = 30.0
_last_retry = [0.0]

from memory.api import notices as _store


def _now() -> int:
    return int(time.time())


def _row(r) -> dict:
    d = dict(r)
    try:
        d["detail"] = json.loads(d.get("detail") or "{}")
    except Exception:  # noqa: BLE001
        d["detail"] = {}
    return d


def get(nid) -> dict | None:
    r = _store.get(nid)
    return _row(r) if r else None


def by_key(key: str) -> dict | None:
    r = _store.by_key(key)
    return _row(r) if r else None


def recent(limit: int = 30, state: str = "") -> list[dict]:
    return [_row(r) for r in _store.recent(limit, state)]


def _claim(key: str, kind: str, title: str, body: str, url: str, detail: dict) -> tuple[dict, bool]:
    """Insert the row for `key`, or return the one already there. (row, fresh)."""
    existing = by_key(key)
    if existing:
        return existing, False
    try:
        nid = _store.insert(key, kind, title[:200], body[:1000], url[:300], _now(),
                            json.dumps(detail or {}, ensure_ascii=False))
    except Exception:  # noqa: BLE001 — a concurrent claim of the same key lost the race: the winner delivers
        row = by_key(key)
        if row:
            return row, False
        raise
    return get(nid), True


def _set(nid, **fields) -> None:
    _store.update(nid, **fields)


def mark_seen(nid) -> bool:
    row = get(nid)
    if not row:
        return False
    _set(nid, state="seen", seen_at=_now())
    return True


# ── devices ───────────────────────────────────────────────────────────────────────────────────────────────────
def device_id(endpoint: str) -> str:
    return hashlib.sha256(str(endpoint).encode()).hexdigest()[:24]


def subscribe(sub: dict, *, dev: str = "", platform: str = "", installed: bool = False) -> dict:
    """Store a browser's PushSubscription ({endpoint, keys:{p256dh, auth}}). Idempotent per endpoint."""
    endpoint = str((sub or {}).get("endpoint") or "").strip()
    keys = (sub or {}).get("keys") or {}
    p256dh, auth = str(keys.get("p256dh") or "").strip(), str(keys.get("auth") or "").strip()
    if not endpoint.startswith("https://") or not p256dh or not auth:
        return {"ok": False, "error": "invalid subscription"}
    did = device_id(endpoint)
    _store.device_upsert(did, endpoint, p256dh, auth, str(dev)[:80], str(platform)[:40], installed, _now())
    return {"ok": True, "id": did}


def unsubscribe(endpoint: str) -> bool:
    _store.device_delete(device_id(endpoint))
    return True


def devices() -> list[dict]:
    """Every subscribed device — WITHOUT its endpoint or keys (a capability URL never leaves this module)."""
    return _store.devices_public()


def _targets() -> list[dict]:
    return _store.devices_all()


def _url_for(row: dict, device: dict) -> str:
    if row.get("url"):
        return row["url"]
    base = "/m" if str(device.get("platform") or "").startswith("mobile") else "/"
    return f"{base}?notice={row['id']}"


def push(row: dict) -> int:
    """Send `row` to every subscribed device. Returns how many push services accepted it. Blocking: call it in a
    thread from async code."""
    from nucleo.pulse import webpush
    accepted = 0
    for d in _targets():
        msg = {"id": row["id"], "kind": row.get("kind") or "info", "title": row.get("title") or "zaelar",
               "body": row.get("body") or "", "url": _url_for(row, d), "tag": f"zaelar-{row['id']}"}
        res = webpush.send({"endpoint": d["endpoint"], "p256dh": d["p256dh"], "auth": d["auth"]}, msg,
                           topic=f"n{row['id']}")
        if res.get("ok"):
            accepted += 1
            _store.device_ok(d["id"], _now())
        elif res.get("gone"):
            _store.device_delete(d["id"])
            logger.info(f"notices: device {d['id']} revoked its subscription — forgotten")
        else:
            _store.device_failed(d["id"])
    return accepted


def someone_looking(now: float | None = None) -> bool:
    """Is he in front of a screen right now: one is visible AND was touched within `PRESENT_S`."""
    try:
        from voice import screens
        now = time.time() if now is None else now
        return any(s.get("visible") and now - float(s.get("input_at") or 0) <= PRESENT_S
                   for s in screens.open_screens())
    except Exception as e:  # noqa: BLE001 — unknown presence reads as «not looking»: the phone is told as well
        logger.debug(f"notices: screen registry unreadable: {e!r}")
        return False


def _owe(row: dict) -> None:
    n = int(row.get("attempts") or 0)
    wait = _BACKOFF_S[min(n, len(_BACKOFF_S) - 1)]
    nxt = _now() + wait if _now() - int(row.get("created_at") or _now()) < _RETRY_FOR_S else None
    _set(row["id"], state="owed", attempts=n + 1, next_try_at=nxt)


async def notify(title: str, text: str, *, key: str, kind: str = "reminder", url: str = "",
                 covered_by: str = "", speak: bool = True, push_: bool = True, detail: dict | None = None,
                 **voice_kw) -> dict:
    """Deliver one notice through the channels, in order, and record how it ended. Never raises.

    `key` is the identity of the notice (e.g. `job:42:1730000000`): the same key never reaches him twice.
    `covered_by` names another system that already rings for it (`google`): the row is closed, nothing delivered.
    Returns {"id", "state", "channel", "duplicate"}."""
    text = (text or "").strip()
    if not text:
        return {"id": None, "state": "", "channel": "", "duplicate": False}
    try:
        row, fresh = _claim(key, kind, title or "zaelar", text, url, detail or {})
    except Exception as e:  # noqa: BLE001 — a ledger that cannot write must not swallow the notice: say it anyway
        logger.warning(f"notices: ledger unavailable ({e!r}) — delivering by voice only")
        from voice import proactive
        await proactive.notify(title or "zaelar", text, key=key, **voice_kw)
        return {"id": None, "state": "", "channel": "voice", "duplicate": False}
    if not fresh:
        return {"id": row["id"], "state": row["state"], "channel": row.get("channel") or "", "duplicate": True}
    if covered_by:
        _set(row["id"], state="covered", channel=covered_by, delivered_at=_now())
        _observe(row, "covered", covered_by)
        return {"id": row["id"], "state": "covered", "channel": covered_by, "duplicate": False}

    from nucleo import runstate
    stopped = runstate.stopped()
    said = False
    if speak and not stopped:
        try:
            from voice import proactive
            said = bool(await proactive.notify(title or "zaelar", text, key=key, **voice_kw))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"notices: voice delivery failed: {e!r}")
    if said and someone_looking():
        _set(row["id"], state="spoken", channel="voice", delivered_at=_now())
        _observe(row, "spoken", "voice")
        return {"id": row["id"], "state": "spoken", "channel": "voice", "duplicate": False}

    accepted = 0
    if push_:
        try:
            accepted = await asyncio.to_thread(push, row)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"notices: push failed: {e!r}")
    if accepted:
        ch = "voice+push" if said else "push"
        _set(row["id"], state="pushed", channel=ch, delivered_at=_now())
        _observe(row, "pushed", ch)
        return {"id": row["id"], "state": "pushed", "channel": ch, "duplicate": False}
    if said:
        _set(row["id"], state="spoken", channel="voice", delivered_at=_now())
        _observe(row, "spoken", "voice")
        return {"id": row["id"], "state": "spoken", "channel": "voice", "duplicate": False}
    _owe(row)
    if stopped:
        # Stopped and unreachable: nothing was said and no device took it. It still reaches the screen and the
        # retry, but the event says so, because «the agent was off» is not «the agent forgot».
        _observe(row, "owed", "stopped")
    else:
        _observe(row, "owed", "")
    return {"id": row["id"], "state": "owed", "channel": "", "duplicate": False}


def _observe(row: dict, state: str, channel: str) -> None:
    try:
        from voice.observer import emit
        emit("notice", f"🔔 {state}", text=str(row.get("title") or "")[:80], role="system",
             extra={"id": row.get("id"), "kind": row.get("kind"), "state": state, "channel": channel})
    except Exception as e:  # noqa: BLE001 — the ledger row already holds the outcome; the event is a mirror
        logger.debug(f"notices: observe failed: {e!r}")


async def retry_owed(now: float | None = None) -> int:
    """Push again every owed notice whose turn has come. Returns how many were delivered. Throttled."""
    now = time.time() if now is None else now
    if now - _last_retry[0] < _RETRY_EVERY_S:
        return 0
    _last_retry[0] = now
    try:
        rows = [_row(r) for r in _store.owed_due(int(now))]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"notices: owed list unreadable, retry skipped: {e!r}")
        return 0
    if not rows or not _targets():
        for r in rows:
            _owe(r)
        return 0
    done = 0
    for r in rows:
        try:
            ok = await asyncio.to_thread(push, r)
        except Exception:  # noqa: BLE001
            ok = 0
        if ok:
            _set(r["id"], state="pushed", channel="push", delivered_at=_now())
            _observe(r, "pushed", "push")
            done += 1
        else:
            _owe(r)
    return done


def drain_to_screen(dev: str = "") -> int:
    """Paint every owed notice on a screen that just connected, and close them as `shown`. Returns how many."""
    try:
        rows = [_row(r) for r in _store.owed_all()]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"notices: owed list unreadable, nothing drained: {e!r}")
        return 0
    if not rows:
        return 0
    try:
        from voice.observer import emit
    except Exception as e:  # noqa: BLE001
        logger.warning(f"notices: no observer to paint owed notices on: {e!r}")
        return 0
    for r in rows:
        try:
            emit("notify", ("🔔 " + (r.get("title") or "zaelar"))[:60], text=r.get("body") or "", role="assistant",
                 extra={"title": r.get("title") or "", "notice_id": r["id"], "late": True,
                        **({"origin_dev": dev} if dev else {})})
            _set(r["id"], state="shown", channel="screen", delivered_at=_now())
        except Exception as e:  # noqa: BLE001 — that one stays owed and is tried on the next screen
            logger.warning(f"notices: could not show notice {r.get('id')}: {e!r}")
    return len(rows)
