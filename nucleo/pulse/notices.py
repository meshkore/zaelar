"""nucleo/pulse/notices.py — the ONE door for a notice the agent owes the operator, and the ledger of how it ended (V2-796).

A reminder that rings, a commission that finished, an approval the agent is waiting on: each is a ROW in `notices`
(`memory/schema.py`), keyed by a `dedupe_key`, and each row ends in exactly one state:

    spoken   said by voice while he was in front of a screen
    pushed   accepted by the push service for ≥ 1 of his devices (Web Push)
    covered  another system he uses rings for it (a Google Calendar alarm) — we stay quiet on purpose
    shown    painted on a screen that connected later (the owed list drains there)
    answered a question (`ask_id`) closed before it could be delivered — never delivered after (V2-852 T09)
    seen     he opened it (notification click)
    owed     nobody could take it yet: retried with backoff, and drained to the next screen that opens

Tested in `tests/agent_headless/unit/test_notice_ledger.py`: NEVER TWICE (`dedupe_key` is UNIQUE; a re-emit
returns the existing row), NEVER LOST (`owed` is retried and drained to the next screen), ⏻ SILENCES THE VOICE,
NOT THE LOCK SCREEN. Push is DECLARED by the caller.

V2-851 F2 — this is THE out-of-turn mouth: everything the agent says outside a turn comes through `notify`, with an
identity — the `task_id` of the row it belongs to, or a notice `key` when it belongs to no task (a cron, an inbound
message, a sign-in left halfway). `voice/proactive.notify` is only the speaking primitive this door uses; the
in-turn mouth is `nucleo/turn/reply`.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time

logger = logging.getLogger("zaelar.notices")

#: A spoken notice counts as HEARD only if a screen was touched this recently; past it, the phone is told too.
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


# ── devices: `notice_devices.py` (his Web Push subscriptions and the push itself) ─────────────────────────────
from nucleo.pulse.notice_devices import (  # noqa: E402,F401 — the ledger's own names, read and patched here
    _targets, _url_for, device_id, devices, push, subscribe, unsubscribe)


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


def _digest(text: str) -> str:
    return hashlib.sha256(" ".join(str(text or "").split()).encode()).hexdigest()[:12]


def identity(text: str, *, key: str = "", task_id: str = "", ask_id: str = "") -> str:
    """The notice's identity: a question is `ask:<ask_id>` whatever door words it (V2-852 T09); a task's line is
    `task:<id>:<digest>` (a new line about it is a new notice); else the line is its own identity for the day."""
    if ask_id:
        return f"ask:{ask_id}"
    if key:
        return str(key)
    if task_id:
        return f"task:{task_id}:{_digest(text)}"
    return f"notice:{time.strftime('%Y-%m-%d', time.gmtime())}:{_digest(text)}"


async def notify(title: str, text: str, *, key: str = "", task_id: str = "", kind: str = "reminder",
                 url: str = "", covered_by: str = "", speak: bool = True, push_: bool = True,
                 detail: dict | None = None, ask_id: str = "", **voice_kw) -> dict:
    """Deliver one notice through the channels, in order, and record how it ended. Never raises.

    `key` is the identity of the notice (e.g. `job:42:1730000000`): the same key never reaches him twice. A line
    about a task passes its `task_id` instead (the key is derived, `identity`), a QUESTION its `ask_id`.
    `covered_by` names another system that already rings for it (`google`): the row is closed, nothing delivered.
    Returns {"id", "state", "channel", "duplicate"}."""
    text = (text or "").strip()
    if not text:
        return {"id": None, "state": "", "channel": "", "duplicate": False}
    key = identity(text, key=key, task_id=task_id, ask_id=ask_id)
    task_id = str(task_id or "")
    detail = {**(detail or {}), "ask_id": str(ask_id)} if ask_id else detail   # shown until answered (`_answered`)
    if task_id:
        detail = {**(detail or {}), "task_id": task_id}
        voice_kw["task_id"] = task_id
    try:
        row, fresh = _claim(key, kind, title or "zaelar", text, url, detail or {})
    except Exception as e:  # noqa: BLE001 — a ledger that cannot write must not swallow the notice: say it anyway
        logger.warning(f"notices: ledger unavailable ({e!r}) — delivering by voice only")
        from voice import proactive
        await proactive.notify(title or "zaelar", text, key=key, speak=speak, **voice_kw)
        return {"id": None, "state": "", "channel": "voice", "duplicate": False}
    if not fresh:
        return {"id": row["id"], "state": row["state"], "channel": row.get("channel") or "", "duplicate": True}
    if covered_by:
        _set(row["id"], state="covered", channel=covered_by, delivered_at=_now())
        _observe(row, "covered", covered_by)
        return {"id": row["id"], "state": "covered", "channel": covered_by, "duplicate": False}

    from nucleo import runstate
    stopped = runstate.stopped()
    said = painted = False
    if not stopped:
        try:
            from voice import proactive
            # Painted on the screen whatever happens to the voice (the primitive's UI half); spoken only if `speak`.
            painted = True
            said = bool(await proactive.notify(title or "zaelar", text, key=key, speak=speak, **voice_kw)) and speak
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
    if painted and someone_looking():
        # Not said, but painted on the screen he is in front of: voice if quiet, else the screen — never owed twice.
        _set(row["id"], state="shown", channel="screen", delivered_at=_now())
        _observe(row, "shown", "screen")
        return {"id": row["id"], "state": "shown", "channel": "screen", "duplicate": False}
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
        task_id = str((row.get("detail") or {}).get("task_id") or "")
        emit("notice", f"🔔 {state}", text=str(row.get("title") or "")[:80], role="system",
             extra={"id": row.get("id"), "kind": row.get("kind"), "state": state, "channel": channel,
                    "key": row.get("dedupe_key") or "", **({"task_id": task_id} if task_id else {})})
    except Exception as e:  # noqa: BLE001 — the ledger row already holds the outcome; the event is a mirror
        logger.debug(f"notices: observe failed: {e!r}")


def _answered(row: dict) -> bool:
    """A question notice whose ask is no longer open is closed `answered`: never pushed nor painted later. Unreadable
    asks: delivered, as before."""
    ask = str((row.get("detail") or {}).get("ask_id") or "")
    try:
        from nucleo.cli import worker_api_asks as _asks
        if not ask or any(a.get("ask_id") == ask for a in _asks.pending_asks()):
            return False
    except Exception as e:  # noqa: BLE001
        return bool(logger.debug(f"notices: open asks unreadable: {e!r}"))
    _set(row["id"], state="answered", next_try_at=None)
    _observe(row, "answered", "")
    return True


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
    rows = [r for r in rows if not _answered(r)]
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
    rows = [r for r in rows if not _answered(r)]
    if not rows:
        return 0
    try:
        from voice.observer import emit
    except Exception as e:  # noqa: BLE001
        logger.warning(f"notices: no observer to paint owed notices on: {e!r}")
        return 0
    for r in rows:
        try:
            _tid = str((r.get("detail") or {}).get("task_id") or "")
            emit("notify", ("🔔 " + (r.get("title") or "zaelar"))[:60], text=r.get("body") or "", role="assistant",
                 extra={"title": r.get("title") or "", "notice_id": r["id"], "late": True,
                        "key": r.get("dedupe_key") or "", **({"task_id": _tid} if _tid else {}),
                        **({"origin_dev": dev} if dev else {})})
            _set(r["id"], state="shown", channel="screen", delivered_at=_now())
        except Exception as e:  # noqa: BLE001 — that one stays owed and is tried on the next screen
            logger.warning(f"notices: could not show notice {r.get('id')}: {e!r}")
    return len(rows)
