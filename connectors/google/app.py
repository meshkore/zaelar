"""app.py — Zaelar's OAuth client for Google, resolved ONCE for every Google-backed connector (V2-684).

## Why this exists

`builtin_client_id` was declared in `connectors/video/providers.py` (V2-603) and copied into
`connectors/calendar/providers.py` (V2-679) with the same comment in both: *«EMPTY until Zaelar
registers its own Google OAuth client»*. The operator registered it on 2026-09-12. Filling those two
strings by hand would have left the other three Google connectors (Gmail, Drive, Photos) still asking
him for the same client, one env var each — five names for one fact.

## Where the value comes from, in order

1. **The operator's own**, `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in the credential store. A
   self-hoster who wants their own quota, their own consent screen and their own verification status
   keeps it — the same rule `video/oauth.py` already applies per connector, lifted one level up.
2. **The client shipped with this install** — the `client_secret_*.json` that the Google Cloud console
   hands you, dropped into `.meshkore/credentials/` verbatim. Read as given: no retyping the id into a
   source file, and no second copy to drift.
3. **Nothing** — and then every Google connector stays DORMANT and SAYS so, which is the behaviour
   they already had.

Per-connector overrides (`EMAIL_GMAIL_CLIENT_ID` and friends) still win over all of this: each
connector checks its own name first and only falls through to here. Nothing that worked stops working.

## What is and is not a secret

A `client_id` is not a secret — PKCE is what protects the exchange, which is why the other connectors
could ship theirs in a public repo. A `client_secret` **is** one, and the file that carries it lives in
`.meshkore/credentials/`, which is gitignored in its entirety. This module never logs either value; it
reports WHERE the client came from, never what it is.

⚠️ This client is a Google **web** client (`"web"` key in the JSON), not an installed one, so Google
requires the exact redirect URI to be pre-registered in the console. `redirect_uris()` prints the list
the operator must paste there — being wrong about that is an `invalid_client` at the last step of a
flow that looked fine all the way up to it.

Every function is SYNCHRONOUS and FAIL-SAFE: it returns "" or an empty list, never raises to a caller.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("zaelar.google.app")

_ROOT = Path(__file__).resolve().parent.parent.parent
CREDENTIALS_DIR = _ROOT / ".meshkore" / "credentials"

#: The callback each Google-backed connector already serves. They are NOT unified into one path: the
#: five flows store their tokens in five files with five different shapes, and rerouting them through a
#: shared callback would be a token-store migration wearing a redirect's clothes. What IS unified is the
#: app, which is the part the operator had to answer five times.
CALLBACK_PATHS: tuple[str, ...] = (
    "/api/email/callback",
    "/api/calendar/callback",
    "/api/video/callback",
    "/api/photos/callback",
    "/api/files/callback",
)

#: Cache keyed by (path, mtime) so an edited credentials file is picked up without a restart, and a
#: missing one is not re-globbed on every status poll. Never keyed by "have I looked yet" — that shape
#: is how a language cache once made a live switch a no-op.
_cache: dict = {"key": None, "value": None}


def _cred(name: str) -> str:
    """The credential store first (it OVERRIDES `.env` — `.meshkore/credentials/README.md`), env second."""
    try:
        from config import credentials as store
        v = (store.get(name) or "").strip()
        if v:
            return v
    except Exception:                      # noqa: BLE001 — a store that cannot be read is a store without the key
        pass
    return (os.getenv(name) or "").strip()


def _client_file() -> Path | None:
    """The `client_secret_*.json` the Google Cloud console produced, if one was dropped in the store.

    Prefers a name starting with `google` so an operator who keeps several (a second project, an old
    one) gets a deterministic answer instead of whichever the filesystem happened to list first.
    """
    try:
        found = sorted(CREDENTIALS_DIR.glob("*client_secret*.json"))
    except Exception:                      # noqa: BLE001
        return None
    if not found:
        return None
    preferred = [p for p in found if p.name.lower().startswith("google")]
    return (preferred or found)[0]


def _from_file() -> dict:
    """`{client_id, client_secret, project_id, kind}` from the console's JSON, or `{}`.

    Accepts both shapes Google emits: `{"web": {...}}` for a web client and `{"installed": {...}}` for a
    desktop one. Which one it is decides whether a redirect URI must be pre-registered, so the kind is
    carried out rather than flattened away.
    """
    p = _client_file()
    if not p:
        _cache["key"], _cache["value"] = None, None
        return {}
    try:
        key = (str(p), p.stat().st_mtime_ns)
    except OSError:
        return {}
    if _cache["key"] == key:
        return _cache["value"] or {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception as e:                 # noqa: BLE001
        logger.warning(f"google: no he podido leer {p.name}: {e}")
        _cache["key"], _cache["value"] = key, {}
        return {}
    for kind in ("web", "installed"):
        block = raw.get(kind)
        if isinstance(block, dict) and str(block.get("client_id") or "").strip():
            out = {"client_id": str(block.get("client_id") or "").strip(),
                   "client_secret": str(block.get("client_secret") or "").strip(),
                   "project_id": str(block.get("project_id") or "").strip(),
                   "kind": kind, "file": p.name}
            _cache["key"], _cache["value"] = key, out
            return out
    logger.warning(f"google: {p.name} no tiene bloque «web» ni «installed` con client_id")
    _cache["key"], _cache["value"] = key, {}
    return {}


def client_id() -> str:
    """The OAuth client this install uses for Google, or "" when there is none."""
    return _cred("GOOGLE_CLIENT_ID") or str(_from_file().get("client_id") or "")


def client_secret() -> str:
    """The matching secret, or "". A web client REQUIRES it at the token exchange; an installed one
    does not, and then this is legitimately empty — the callers all send it only when truthy."""
    return _cred("GOOGLE_CLIENT_SECRET") or str(_from_file().get("client_secret") or "")


def configured() -> bool:
    return bool(client_id())


def is_web_client() -> bool:
    """True when the shipped client is a Google **web** client — the kind whose redirect URIs must be
    registered in the console beforehand. False for an installed/desktop client, and False when the id
    came from the credential store, where the kind is not recorded."""
    return _from_file().get("kind") == "web" and not _cred("GOOGLE_CLIENT_ID")


def source() -> str:
    """WHERE the client came from: `operator` (their own, in the store), `shipped` (the console JSON in
    `.meshkore/credentials/`), or "" (none — every Google connector is dormant). Never the value."""
    if _cred("GOOGLE_CLIENT_ID"):
        return "operator"
    return "shipped" if _from_file().get("client_id") else ""


def project_id() -> str:
    """The Google Cloud project behind the shipped client — shown in the Connectors tab so the operator
    can tell WHICH of their projects is answering, without the id being a secret."""
    return str(_from_file().get("project_id") or "")


def redirect_uris(origin: str = "") -> list[str]:
    """Every callback that must be registered as an *Authorized redirect URI* in the console.

    `origin` is the scheme://host[:port] the operator actually opens the engine on — a managed
    deployment is not loopback, and a hardcoded `127.0.0.1` there is a flow that dies at the last step
    (V2-603's finding, paid once already). Defaults to the local engine.
    """
    base = (origin or "").strip().rstrip("/") or "http://127.0.0.1:43917"
    return [base + path for path in CALLBACK_PATHS]


def status(origin: str = "") -> dict:
    """Redacted state for the Connectors tab and `/api/status`. Says whether Google can be connected at
    all, from where, and — when it cannot — what is missing. Carries NO credential value."""
    src = source()
    return {
        "configured": bool(src),
        "source": src,
        "project_id": project_id(),
        "client_file": str(_from_file().get("file") or ""),
        "web_client": is_web_client(),
        "has_secret": bool(client_secret()),
        "redirect_uris": redirect_uris(origin),
        "services": [],                    # filled by `services.public_list()`; kept here so the shape is stable
    }
