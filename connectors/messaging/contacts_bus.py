"""connectors/messaging/contacts_bus.py — asking a connector for its address book and waiting for it.

V2-714. `ingest.py` owns the two topics; this owns the ROUND TRIP, because the widget's `sync_source` has
to be able to answer «traje 214» in the same turn he asked, and a fire-and-forget publish cannot.

The wait is short and a timeout is NOT an error worth shouting about: a connector that is reconnecting
answers on the next tick and `sources.tick` asks again. What must never happen is the turn hanging on a
platform — the voice loop is on the other side of this call, so the deadline is hard.

Polled with `queue.get_nowait()` in a sleep loop, the way `ingest._PlatformInbox.drain` already does it:
this is called from the widget's synchronous dispatch, sometimes off the event loop entirely, and a
Subscription built outside a loop delivers best-effort into its queue exactly for that case.
"""
from __future__ import annotations

import threading
import time

from loguru import logger

from bus import subscribe, unsubscribe

from . import ingest

#: Two cards asking at once would race for one answer, and the loser would time out over work that did
#: happen. One asker at a time; the second waits its turn or gives up on the same deadline.
_LOCK = threading.Lock()

_POLL_S = 0.15


def request(platform: str, *, timeout: float = 25.0) -> dict:
    """Ask `platform` for its contacts and groups, and wait for the one answer.

    Returns `{ok, contacts, groups, partial}` or `{ok: False, error}` with a sentence the card can show.
    NEVER raises.
    """
    platform = (platform or "").strip().lower()
    if not platform:
        return {"ok": False, "error": "no me has dicho de qué plataforma"}
    if not _LOCK.acquire(timeout=timeout):
        return {"ok": False, "error": "ya hay otra sincronización de contactos en curso"}
    sub = None
    try:
        # Subscribe BEFORE asking: a connector that answers fast would otherwise publish into nobody.
        sub = subscribe(ingest.TOPIC_CONTACTS)
        ingest.publish_contacts_ask(platform)
        end = time.time() + timeout
        while time.time() < end:
            while True:
                try:
                    ev = sub.queue.get_nowait()
                except Exception:
                    break
                if str((ev or {}).get("platform") or "").lower() == platform:
                    if ev.get("error"):
                        return {"ok": False, "error": str(ev["error"])}
                    return {"ok": True, "contacts": ev.get("contacts") or [],
                            "groups": ev.get("groups") or [], "partial": bool(ev.get("partial"))}
            time.sleep(_POLL_S)
        return {"ok": False,
                "error": f"{platform} no contestó a tiempo — lo reintento en la próxima pasada"}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"contacts_bus: {platform} falló ({e})")
        return {"ok": False, "error": str(e)}
    finally:
        if sub is not None:
            try:
                unsubscribe(sub)
            except Exception:  # noqa: BLE001
                pass
        _LOCK.release()
