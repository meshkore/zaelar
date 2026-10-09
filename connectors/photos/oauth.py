#
# oauth.py — OAuth2 (authorization-code + PKCE) for the photos connector (V2-564). Same shape as
# `connectors/files/oauth.py` (V2-557): PKCE S256 so an installed app never ships a secret, the callback served
# by zaelar's OWN server, tokens in the credential store (`.meshkore/credentials/photos_oauth.json`, chmod 600,
# gitignored — NEVER in the repo or the frontend).
#
# UI-managed config (product invariant): the operator registers the OAuth app ONCE from the Connectors tab and
# the connector stays DORMANT until then — no credentials in `.env`, and nothing here raises to its caller.
#
# V2-778 F1-13 — the flow itself lives in `connectors/oauth_base.py`, shared by the six account connectors; this
# module keeps what is THIS connector's own: where its tokens live, its credential names, its callback route,
# which provider rides Zaelar's Google app, and `status()`. The base reads all of it through this module at
# call time, so redefining one function here, or patching it in a test, still governs the whole flow.
#
from __future__ import annotations

import logging
import sys
from pathlib import Path

from connectors import oauth_base as _b
from connectors import secure_json_store as _sjs
from connectors.photos import providers as _pv

logger = logging.getLogger("zaelar.photos.oauth")

_ROOT = Path(__file__).resolve().parent.parent.parent
STORE = _sjs.credentials_path("photos_oauth.json")
ENV_PREFIX = "PHOTOS"
CALLBACK_PATH = "/api/photos/callback"
_DEFAULT_REDIRECT = "http://127.0.0.1:43917/api/photos/callback"
_PENDING_TTL = 900
_GOOGLE_PROVIDERS = {'google-photos'}
_m = sys.modules[__name__]


def _cred(name: str) -> str:
    return _b.cred(name)


def _shipped_google(provider_id: str, *, secret: bool = False) -> str:
    return _b.shipped_google(_m, provider_id, secret=secret)


def client_id(provider_id: str) -> str:
    return _b.client_id(_m, provider_id)


def client_secret(provider_id: str) -> str:
    return _b.client_secret(_m, provider_id)


def configured(provider_id: str) -> bool:
    return bool(_pv.get(provider_id) and client_id(provider_id))


def redirect_uri(origin: str = "") -> str:
    return _b.redirect_uri(_m, origin)


def _load() -> dict:
    return _b.load(_m)


def _save(data: dict) -> None:
    _b.save(_m, data)


def _accounts(data: dict | None = None) -> dict:
    return (data if data is not None else _load()).get("accounts", {}) or {}


def account(provider_id: str) -> dict:
    return _accounts().get((provider_id or "").strip().lower(), {}) or {}


def tokens_present(provider_id: str) -> bool:
    return bool(account(provider_id).get("refresh_token"))


def forget(provider_id: str) -> dict:
    _b.forget(_m, (provider_id or "").strip().lower())
    return {"ok": True, "provider": provider_id}


def authorize_url(provider_id: str, tier_id: str = "", origin: str = "") -> dict:
    return _b.authorize_url(_m, provider_id, tier_id, origin)


def exchange_code(code: str, state: str) -> dict:
    res = _b.exchange_code(_m, code, state, lambda pend: pend["provider"])
    res.pop("pending", None)
    return res


def _store_tokens(provider_id: str, tier_id: str, tok: dict) -> None:
    _b.store_tokens(_m, provider_id, tier_id, tok)


def access_token(provider_id: str) -> str | None:
    pid = (provider_id or "").strip().lower()
    return _b.access_token(_m, pid, pid, account(pid))


def status() -> list[dict]:
    out = []
    for p in _pv.PROVIDERS.values():
        connected = tokens_present(p.id)
        tier = p.tier()
        out.append({
            "id": p.id, "label": p.label, "app_configured": configured(p.id), "connected": connected,
            "tier": tier.id, "tier_label": tier.label, "browsable": False, "note": p.note,
        })
    return out
