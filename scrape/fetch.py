"""scrape/fetch.py — getting to a page: a plain GET from this machine, then Bright Data's unlocker (V2-846).

Measured 2026-11-04 from a Fly Machine: AutoScout24 answers a plain GET in 0.5 s with its ads in the page; coches.net,
milanuncios, refurbed and idealista come whole through the unlocker in 25-73 s; Wallapop refuses any datacenter IP.
So the cheap rung is asked first and a WALL (`walls.py`: a blocking status, a challenge page, the site's own error
page) or a page that held nothing moves the read one rung up — a block is a state, never the answer while a rung is
left. Each wall is noted in the engine's one per-source record (`hooks.note_source`).

POLITENESS per domain (moved from `search/listing.py`): a minimum interval between two requests to the same host, a
rest after repeated 403/429 that honours `Retry-After`. Retrying into a wall is how a polite reader gets banned.
"""
from __future__ import annotations

import os
import random
import threading
import time

from scrape import brightdata as _bd, hooks as _hooks, walls as _walls

_TIMEOUT_S = float(os.getenv("LISTING_SEARCH_TIMEOUT", "12.0"))
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/142.0 Safari/537.36")

_MIN_INTERVAL_S = float(os.getenv("LISTING_SEARCH_DOMAIN_INTERVAL", "2.0"))
_PENALTY_S = 120.0
_MAX_WAIT_S = 6.0
_domain_state: dict[str, dict] = {}
_domain_lock = threading.Lock()


class Wall(RuntimeError):
    """The site stopped this rung (status, challenge, its own error page). The next rung may get in."""


def _acquire(host: str) -> bool:
    now = time.monotonic()
    with _domain_lock:
        st = _domain_state.setdefault(host, {"next_ok": 0.0, "strikes": 0})
        wait = st["next_ok"] - now
        if wait > _MAX_WAIT_S:
            return False
        st["next_ok"] = max(now, st["next_ok"]) + _MIN_INTERVAL_S + random.uniform(0.0, 0.5)
    if wait > 0:
        time.sleep(wait)
    return True


def _penalize(host: str, *, retry_after: float | None = None) -> None:
    with _domain_lock:
        st = _domain_state.setdefault(host, {"next_ok": 0.0, "strikes": 0})
        st["strikes"] += 1
        pause = retry_after if retry_after else (_PENALTY_S if st["strikes"] >= 2 else _MIN_INTERVAL_S * 4)
        st["next_ok"] = max(st["next_ok"], time.monotonic() + pause)


def _wall_of(status: int, url: str, body: str) -> str:
    return (_walls.status_wall_reason(status) or _walls.wall_reason(url)
            or (_walls.body_wall_reason(body) if len(body) <= _walls.WALL_BODY_PEEK_CHARS else ""))


def http(url: str) -> str:
    """A plain GET from this machine. Raises `Wall` when the site stopped it, RuntimeError on any other failure."""
    import httpx
    host = _walls.host_of(url)
    if not _acquire(host):
        raise Wall(f"{host}: resting after repeated blocks")
    with httpx.Client(timeout=_TIMEOUT_S, follow_redirects=True,
                      headers={"User-Agent": _UA, "Accept-Language": "es,en;q=0.8"}) as client:
        resp = client.get(url)
    reason = _wall_of(resp.status_code, str(resp.url), resp.text)
    if reason:
        if resp.status_code in (403, 429):
            try:
                _penalize(host, retry_after=float(resp.headers.get("retry-after", "")))
            except ValueError:
                _penalize(host)
        _hooks.note_source(host, "wall", f"http {resp.status_code}: {reason}")
        raise Wall(f"{host}: {reason}")
    if resp.status_code >= 400:
        raise RuntimeError(f"{host}: HTTP {resp.status_code}")
    return resp.text


def unlocker(url: str, country: str = "") -> str:
    """The page through Bright Data's Web Unlocker. Raises when there is no token or the provider refused."""
    if not _bd.token():
        raise RuntimeError("no unlocker token")
    from urllib.parse import quote
    # The provider validates the url strictly: brackets in a query (`makes[]=…`, cars.com) are a 400 unless encoded.
    payload = {"zone": _bd.zone_unlocker(), "url": quote(url, safe=":/?&=%#+,;@!$'()*~"), "format": "raw"}
    if country:
        payload["country"] = country.lower()
    try:
        body = _bd.request(payload, provider="brightdata_unlocker")
    except RuntimeError as e:
        _hooks.note_source(_walls.host_of(url), "wall", f"unlocker: {str(e)[:160]}")
        raise
    reason = _walls.body_wall_reason(body) if len(body) <= _walls.WALL_BODY_PEEK_CHARS else ""
    if reason:
        raise Wall(f"{_walls.host_of(url)}: {reason} (through the unlocker)")
    return body


#: The fetch rungs, cheapest first. The browser rungs join in V2-846 F3/F4.
RUNGS = (("http", lambda url, country: http(url)), ("unlocker", unlocker))
