"""nucleo/pulse/notice_devices.py — his devices for the notice ledger (`notices.py`): the Web Push subscriptions,
stored without ever handing their endpoint out, and the push of one notice to every one of them. Split out of
`notices.py` by concern (V2-851 F2) when the ledger became the out-of-turn mouth."""
from __future__ import annotations

import hashlib
import logging
import time

from memory.api import notices as _store

logger = logging.getLogger("zaelar.notices")


def _now() -> int:
    return int(time.time())


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
