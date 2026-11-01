"""oauth_broker.py — an OAuth app this install does not hold, used through a broker that does.

An account connector needs an OAuth CLIENT registered with the provider: a `client_id`, and for some providers
(a Google *web* client, Microsoft confidential clients) a `client_secret` that has to be presented at every token
exchange and every refresh. A self-hosted engine keeps both in its own credential store (`connectors/google/app.py`,
`<PREFIX>_<PROVIDER>_CLIENT_ID`). A deployment that runs one engine per person in a container cannot: whatever is in
the container is readable by the code the agent runs there, and a client secret belongs to the operator of the app,
not to each instance.

So such a deployment may name a BROKER: an HTTPS endpoint that holds the client per provider family and performs
the two token calls on the engine's behalf. The engine still does everything else — it builds the consent URL with
PKCE, owns the `state`, serves the callback and stores the tokens in its own store. The broker sees one
`code`+`code_verifier` (or one `refresh_token`) per call and adds the secret; the token URL is chosen by the broker
from the family, never sent by the engine.

Configuration (both optional; with neither, nothing here does anything and every flow is exactly as before):
  * `ZAELAR_OAUTH_BROKER_URL` — the broker's base URL (`<base>/client`, `<base>/token`).
  * otherwise `CONTROL_PLANE_URL` + `/oauth`, when `CONTROL_PLANE_SERVICE_TOKEN` is set too.
The engine authenticates with the same workload header it already sends there (`X-Service-Token`).

Precedence is unchanged: a client this install holds ALWAYS wins. The broker is only the last fallback, and a
token call goes to it only when the client in use is the broker's own (`owns(client_id)`), so a self-hoster who
registered their own app never has a token leave for anybody else.

Fail-safe like the rest of the OAuth code: nothing raises to a caller; an unreachable broker reads as «no client»,
and the connector stays dormant and says so.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import urllib.parse
from connectors import outcome as _outcome   # every provider call reports what happened (V2-833)

logger = logging.getLogger("zaelar.oauth.broker")

#: Provider family by the HOST of its token endpoint. The engine names a family; the broker maps it to the token
#: URL it trusts. A provider not in this table never goes to the broker.
FAMILIES: dict[str, str] = {
    "oauth2.googleapis.com": "google",
    "accounts.google.com": "google",
    "login.microsoftonline.com": "microsoft",
    "accounts.spotify.com": "spotify",
}

_CLIENT_TTL = 3600.0          # a client id changes when the operator rotates the app — an hour is plenty
_MISS_TTL = 60.0              # «no client / unreachable» is retried soon, never cached for long
_cache: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()


def base_url() -> str:
    explicit = (os.getenv("ZAELAR_OAUTH_BROKER_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    cp = (os.getenv("CONTROL_PLANE_URL") or "").strip().rstrip("/")
    if cp and _token():
        return cp + "/oauth"
    return ""


def enabled() -> bool:
    return bool(base_url())


def _token() -> str:
    return (os.getenv("CONTROL_PLANE_SERVICE_TOKEN") or "").strip()


def _headers() -> dict[str, str]:
    t = _token()
    return {"X-Service-Token": t} if t else {}


def family_of(token_url: str) -> str:
    """`google` / `microsoft` / `spotify`, or "" for a provider the broker does not serve."""
    try:
        host = (urllib.parse.urlparse(token_url or "").hostname or "").lower()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"oauth broker: unreadable token url: {type(e).__name__}")
        return ""
    return FAMILIES.get(host, "")


def _fetch(family: str) -> str:
    cid = ""
    try:
        import httpx
        r = _outcome.call(f"oauth-broker:{family}", "client", lambda: httpx.post(base_url() + "/client", json={"provider": family},
                                                                             headers=_headers(), timeout=4), measure=lambda r: {"status": r.status_code}, refused=lambda r: r.status_code >= 400)
        if r.status_code == 200:
            cid = str((r.json() or {}).get("client_id") or "").strip()
    except Exception as e:  # noqa: BLE001 — unreachable reads as «no client»
        logger.warning(f"oauth broker: client lookup for {family} failed: {type(e).__name__}")
    with _lock:
        _cache[family] = (cid, time.monotonic() + (_CLIENT_TTL if cid else _MISS_TTL))
    return cid


def client_id(family: str) -> str:
    """The broker's client id for `family`, or "" (no broker, no client for that family, broker unreachable).

    Status endpoints call this on every poll, from the event loop. So only the FIRST lookup of a family waits for
    the network (bounded); afterwards a known id is answered from memory at once and refreshed in the background
    when it ages; a miss is answered "" at once and retried in the background too, so a broker that is down
    costs the event loop one bounded wait per family, not one per poll."""
    if not family or not enabled():
        return ""
    now = time.monotonic()
    with _lock:
        hit = _cache.get(family)
    if hit is None:
        return _fetch(family)
    cid, until = hit
    if now >= until:
        with _lock:
            _cache[family] = (cid, now + _MISS_TTL)           # one refresh in flight, not one per poll
        threading.Thread(target=_fetch, args=(family,), daemon=True, name="oauth-broker-client").start()
    return cid


def owns(family: str, cid: str) -> bool:
    """True when `cid` is the broker's client for `family` — the only case a token call is sent there."""
    return bool(cid) and bool(family) and client_id(family) == cid


def token(family: str, body: dict) -> dict:
    """POST one token request (authorization_code or refresh_token) through the broker. Returns the provider's
    JSON as the broker relays it, or `{"error": ...}`. The body never carries a secret: the broker adds it."""
    payload = {k: v for k, v in (body or {}).items() if k != "client_secret"}
    payload["provider"] = family
    try:
        import httpx
        r = _outcome.call(f"oauth-broker:{family}", "token", lambda: httpx.post(base_url() + "/token", json=payload,
                                                                            headers=_headers(), timeout=30), measure=lambda r: {"status": r.status_code}, refused=lambda r: r.status_code >= 400)
        out = r.json()
        return out if isinstance(out, dict) else {"error": "broker_bad_response"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"broker_unreachable: {type(e).__name__}"}


def _reset_for_tests() -> None:
    with _lock:
        _cache.clear()
