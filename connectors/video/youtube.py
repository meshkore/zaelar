#
# youtube.py — the YouTube Data API v3 client (V2-597). Speaks HTTP, returns the NORMALIZED shapes, nothing
# else — the facade (`service.py`) composes and the widget never sees this module. Quota facts that shaped it
# (free tier is 10,000 units/day): `subscriptions.list` and `playlistItems.list` cost 1 unit per page, so a
# full suggestions pull for 25 channels is ~26 units — comfortably free many times a day.
#
# The uploads playlist of a channel is DERIVED, not fetched: a channel id `UCxxxx` has uploads playlist
# `UUxxxx` (documented YouTube convention). That saves one `channels.list` call per channel — without it the
# pull would cost double and take twice the round-trips.
#
from __future__ import annotations

import logging

logger = logging.getLogger("zaelar.video.youtube")

_TIMEOUT = 12


def _err_of(resp) -> str:
    """One readable line out of a Google error body. 401 means the token died (reconnect); 403 is usually
    quota or a disabled API — the distinction changes what the operator does, so it travels."""
    try:
        body = resp.json()
        reason = ((body.get("error") or {}).get("errors") or [{}])[0].get("reason") or ""
        msg = (body.get("error") or {}).get("message") or ""
    except Exception:
        reason, msg = "", ""
    if resp.status_code == 401:
        return "la sesión con YouTube caducó — reconecta la cuenta"
    if resp.status_code == 403 and "quota" in (reason + msg).lower():
        return "cuota diaria de la API de YouTube agotada — vuelve a intentarlo mañana"
    if resp.status_code == 403 and "disabled" in msg.lower():
        return "la YouTube Data API v3 no está habilitada en tu proyecto de Google Cloud"
    return f"YouTube respondió {resp.status_code}" + (f" ({reason or msg[:80]})" if (reason or msg) else "")


def list_subscriptions(client, api_base: str, token: str, max_n: int = 50) -> dict:
    """The account's subscriptions, newest-relevance order (the API's default for mine=true).
    Returns {"ok": True, "channels": [{channel_id, channel}]} or {"ok": False, "error"}."""
    rows, page = [], ""
    while len(rows) < max_n:
        params = {"part": "snippet", "mine": "true", "maxResults": min(50, max_n - len(rows))}
        if page:
            params["pageToken"] = page
        r = client.get(f"{api_base}/subscriptions", params=params,
                       headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
        if r.status_code != 200:
            return {"ok": False, "error": _err_of(r)}
        body = r.json()
        for it in body.get("items") or []:
            sn = it.get("snippet") or {}
            cid = ((sn.get("resourceId") or {}).get("channelId") or "").strip()
            title = str(sn.get("title") or "").strip()
            if cid and title:
                rows.append({"channel_id": cid, "channel": title[:80]})
        page = str(body.get("nextPageToken") or "")
        if not page:
            break
    return {"ok": True, "channels": rows[:max_n]}


def channel_recent_uploads(client, api_base: str, token: str, channel_id: str,
                           channel_title: str, n: int = 2) -> list[dict]:
    """Most recent uploads of ONE channel, as normalized video rows. Best-effort PER CHANNEL on purpose:
    one channel with a broken/empty uploads playlist must not cost the whole suggestions pull — the facade
    keeps walking the rest."""
    cid = (channel_id or "").strip()
    if not cid.startswith("UC"):
        return []
    playlist = "UU" + cid[2:]
    try:
        r = client.get(f"{api_base}/playlistItems",
                       params={"part": "snippet,contentDetails", "playlistId": playlist,
                               "maxResults": max(1, min(n, 10))},
                       headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
        if r.status_code != 200:
            return []
        out = []
        for it in r.json().get("items") or []:
            vid = ((it.get("contentDetails") or {}).get("videoId") or "").strip()
            sn = it.get("snippet") or {}
            title = str(sn.get("title") or "").strip()
            if not vid or not title:
                continue                      # a hit the parser cannot NAME is not a candidate (V2-469)
            out.append({
                "videoId": vid, "title": title[:140], "channel": channel_title[:80],
                "published": str(sn.get("publishedAt") or "")[:20],
                "url": "https://www.youtube.com/watch?v=" + vid,
            })
        return out
    except Exception as e:
        logger.debug(f"uploads pull failed for {cid}: {e}")
        return []
