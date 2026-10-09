#
# oauth.py — OAuth2 (authorization-code + PKCE) for email, provider MODEL-AGNOSTIC (V2-055). Gmail and
# Outlook/Microsoft share the SAME flow (endpoints/scopes come from the `providers.py` registry), and transport
# remains IMAP/SMTP with SASL XOAUTH2 (the access token replaces the password; see `mailbox.xoauth2_sasl`).
#
# Pattern copied from `connectors/spotify/auth.py` (V2-041): PKCE S256 (without exposing a secret in installed apps),
# callback served by zaelar's OWN server (`server/email_api.py` → /api/email/callback), tokens in the credential
# store (`.meshkore/credentials/email_oauth.json`, chmod 600, gitignored — NEVER in the repo or frontend).
# UI-managed config: app `client_id`/`secret` (Google Cloud / Microsoft Entra) are set by the operator ONCE;
# DORMANT until then (like Spotify).
#
# All functions are SYNCHRONOUS and FAIL-SAFE (return {ok:False,...} or None; never raise to the caller).
#
# V2-778 F1-13 — the flow itself lives in `connectors/oauth_base.py`, shared by the six account connectors; this
# module keeps what is email's own: SEVERAL accounts per provider (keyed `provider:address`), providers that
# speak IMAP without OAuth beside the ones that do, the Google offline/consent parameters and the login hint.
# ⚠️ No route serves `/api/email/callback` yet (`server/email_api.py` does not exist — declared in
# `test_both_doors_ask_google_for_the_SAME_return_address`), so this half is reachable only once that is built.
#
from __future__ import annotations

import logging
import sys
from pathlib import Path

from connectors import oauth_base as _b
from connectors import secure_json_store as _sjs
from connectors.email import providers as _pv

logger = logging.getLogger("zaelar.email.oauth")

_ROOT = Path(__file__).resolve().parent.parent.parent
STORE = _sjs.credentials_path("email_oauth.json")
ENV_PREFIX = "EMAIL"
CALLBACK_PATH = "/api/email/callback"
_DEFAULT_REDIRECT = "http://127.0.0.1:43917/api/email/callback"
_GOOGLE_PROVIDERS = {'gmail'}
_m = sys.modules[__name__]


def _cred(name: str) -> str:
    return _b.cred(name)


def _shipped_google(provider_id: str, *, secret: bool = False) -> str:
    return _b.shipped_google(_m, provider_id, secret=secret)


def _oauth_capable(p) -> bool:
    return bool(p and p.oauth)


def _auth_spec(p, tier_id: str = ""):
    # Google: offline + consent force a refresh_token; Microsoft ignores both
    return p.oauth.authorize_url, p.oauth.token_url, list(p.oauth.scopes), {"access_type": "offline",
                                                                             "prompt": "consent"}


def client_id(provider_id: str) -> str:
    return _b.client_id(_m, provider_id)


def client_secret(provider_id: str) -> str:
    return _b.client_secret(_m, provider_id)


def configured(provider_id: str) -> bool:
    """Is there an OAuth app registered for this provider? (if not, the widget offers the app-password path)."""
    p = _pv.get(provider_id)
    if not p or not p.oauth:
        return False
    return bool(client_id(provider_id))


def redirect_uri(origin: str = "") -> str:
    return _b.redirect_uri(_m, origin)


def _load() -> dict:
    return _b.load(_m)


def _save(data: dict) -> None:
    _b.save(_m, data)


def _acct_key(provider_id: str, address: str) -> str:
    return f"{provider_id}:{(address or '').strip().lower()}"


def tokens_present(provider_id: str, address: str) -> bool:
    return bool(_b.account(_m, _acct_key(provider_id, address)).get("refresh_token"))


def forget(provider_id: str, address: str) -> None:
    _b.forget(_m, _acct_key(provider_id, address))


def authorize_url(provider_id: str, address: str = "", origin: str = "") -> dict:
    """{ok, url} — the consent URL to send the operator to, for one ADDRESS of this provider."""
    res = _b.authorize_url(_m, provider_id, "", origin, pending={"address": address},
                           params={"login_hint": address} if address else None)
    res.pop("tier", None)
    return res


def exchange_code(code: str, state: str) -> dict:
    """Callback: exchange `code` for the tokens of the address the consent was started for.
    Returns {ok, provider, address}."""
    res = _b.exchange_code(_m, code, state,
                           lambda pend: _acct_key(pend["provider"], pend.get("address") or ""))
    if not res.get("ok"):
        return res
    return {"ok": True, "provider": res["provider"], "address": res["pending"].get("address") or ""}


def _store_tokens(provider_id: str, address: str, tok: dict) -> None:
    _b.store_tokens(_m, _acct_key(provider_id, address), "", tok)


def access_token(provider_id: str, address: str) -> str | None:
    """Return a VALID access token (refreshing if expired) or None. Used by the connector for XOAUTH2."""
    key = _acct_key(provider_id, address)
    return _b.access_token(_m, provider_id, key, _b.account(_m, key))
