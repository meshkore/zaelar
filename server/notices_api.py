"""server/notices_api.py — the HTTP face of `nucleo/pulse/notices.py` and Web Push (V2-796).

  · `GET  /api/push/key`          — the VAPID public key a browser subscribes with (`applicationServerKey`).
  · `POST /api/push/subscribe`    — store a browser's PushSubscription (idempotent per endpoint).
  · `POST /api/push/unsubscribe`  — forget one.
  · `POST /api/push/device`       — a screen reports its install/permission state (installed PWA? push granted?).
  · `GET  /api/push/devices`      — which devices can be reached — never their endpoints.
  · `POST /api/push/test`         — send a test notice to every device (the «try it» button).
  · `GET  /api/notices`           — the ledger: recent notices and how each one ended.
  · `POST /api/notices/{id}/seen` — he opened it (the service worker's `notificationclick`).
"""
from __future__ import annotations

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from nucleo.pulse import notices

router = APIRouter()


@router.get("/api/push/key")
def push_key() -> dict:
    from nucleo.pulse import webpush
    try:
        return {"ok": True, "key": webpush.public_key()}
    except Exception as e:  # noqa: BLE001 — no key means no push; the UI then hides its offer
        return {"ok": False, "key": "", "error": str(e)[:120]}


@router.post("/api/push/subscribe")
def push_subscribe(payload: dict = Body(...)) -> JSONResponse:
    p = payload or {}
    res = notices.subscribe(p.get("subscription") or {}, dev=str(p.get("dev") or ""),
                            platform=str(p.get("platform") or ""), installed=bool(p.get("installed")))
    return JSONResponse(res, status_code=200 if res.get("ok") else 400)


@router.post("/api/push/unsubscribe")
def push_unsubscribe(endpoint: str = Body(..., embed=True)) -> dict:
    return {"ok": notices.unsubscribe(endpoint)}


@router.post("/api/push/device")
def push_device(payload: dict = Body(...)) -> dict:
    """A screen says what it is: installed as an app or a browser tab, and whether it may show notifications.
    Recorded as an event so the operator can see which of his phones can be reached, and why not."""
    p = payload or {}
    state = {"dev": str(p.get("dev") or "")[:80], "platform": str(p.get("platform") or "")[:40],
             "installed": bool(p.get("installed")), "permission": str(p.get("permission") or "")[:16],
             "supported": bool(p.get("supported"))}
    try:
        from voice.observer import emit
        emit("device", "📱 device state", role="system", extra=state)
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"notices_api: device state not recorded: {e!r}")
    return {"ok": True, "devices": len(notices.devices())}


@router.get("/api/push/devices")
def push_devices() -> dict:
    return {"devices": notices.devices()}


@router.post("/api/push/test")
async def push_test(dev: str = Body("", embed=True)) -> dict:
    import time
    row, _ = notices._claim(f"test:{int(time.time() * 1000)}", "info", "zaelar",
                            _test_line(), "", {"dev": str(dev)[:80]})
    import asyncio
    n = await asyncio.to_thread(notices.push, row)
    notices._set(row["id"], state="pushed" if n else "owed", channel="push" if n else "")
    return {"ok": bool(n), "accepted": n}


def _test_line() -> str:
    from i18n import langs
    return langs.words("notices.test_line", default="") or "Notifications are on."


@router.get("/api/notices")
def list_notices(state: str = "", limit: int = 30) -> dict:
    rows = notices.recent(limit=max(1, min(int(limit or 30), 100)), state=str(state or "")[:16])
    for r in rows:
        r.pop("detail", None)
    return {"notices": rows}


@router.post("/api/notices/{nid}/seen")
def notice_seen(nid: int) -> dict:
    return {"ok": notices.mark_seen(nid)}
