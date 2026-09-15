"""app.py — Zaelar's OAuth client for Google, resolved ONCE for every Google-backed connector (V2-685).

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
requires the exact redirect URI to be pre-registered in the console, and refuses an unregistered one
with **`Error 400: redirect_uri_mismatch`** at the last step of a flow that looked fine all the way up.
**`uris_to_register()` is what the operator pastes there — not `redirect_uris()`**: the redirect is
DERIVED from the origin the browser is on and this engine serves two of them, so a list printed for one
origin is right half the time. Measured the hard way on the first real connect (V2-687, 2026-09-14).

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
#:
#: ⚠️ These are the paths the engine ACTUALLY serves, not the ones its connectors are named after.
#: `files` answers on `/api/cloudfiles/callback` (`connectors/files/server_api.py`), and this tuple said
#: `/api/files/callback` until 2026-09-14 — a URI nothing serves, handed to the operator to register while
#: the one Drive really uses was missing from the list. `test_every_callback_we_ask_him_to_register_is_a_route_we_serve`
#: now derives the truth from the mounted router instead of trusting this tuple.
CALLBACK_PATHS: tuple[str, ...] = (
    "/api/email/callback",
    "/api/calendar/callback",
    "/api/video/callback",
    "/api/photos/callback",
    "/api/cloudfiles/callback",
    "/api/contacts/callback",
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


#: The host of the engine's HTTPS listener. It is a DNS alias of 127.0.0.1 (`dig local.zaelar.com` → the
#: loopback address) carrying a shared certificate, so that a LOCAL engine can be opened over TLS without
#: the operator minting one. For Google it is not a second machine — it is the same machine by another name.
LOCAL_TLS_HOST = "local.zaelar.com"


def loopback_origin() -> str:
    import os
    return "http://127.0.0.1:" + (os.getenv("ZAELAR_PORT") or "43917").strip()


def served_origins() -> list[str]:
    """The origins a LOCAL engine actually answers on — both listeners of the same app (`server/__main__.py`:
    HTTP on 43917, and the shared-cert HTTPS one on local.zaelar.com, ports overridable by env)."""
    import os
    tls_port = (os.getenv("ZAELAR_TLS_PORT") or "44317").strip()
    return [loopback_origin(), f"https://{LOCAL_TLS_HOST}:{tls_port}"]


def normalize_origin(origin: str) -> str:
    """Collapse this engine's TWO local listeners into the ONE address Google is asked to return to.

    A browser on `https://local.zaelar.com:44317` is on the same process, the same port-neighbour and the
    same token store as one on `http://127.0.0.1:43917`; the callback page is self-contained («conectado,
    cierra esta pestaña») and reads nothing from the origin's session, so which of the two Google returns
    to changes nothing the operator can observe.

    What it DOES change is whether the address can be registered at all. Google exempts the loopback
    address from domain ownership: `127.0.0.1` needs no verification, no HTTPS and no consent-screen
    authorized domain. `local.zaelar.com` is a domain — OURS, shipped with the engine — so registering it
    would require whoever self-hosts to verify a domain they do not own. Deriving the redirect from
    whichever listener the operator happened to open therefore made half the attempts unregistrable, and
    the remedy V2-687 reached for (print TEN URIs instead of five) asked him to register five addresses
    that cannot be registered.

    A genuinely remote origin — a managed deployment on its own verified domain — is NOT one of
    `served_origins()` and passes through untouched, which is the whole of V2-603's finding and stays true.
    """
    o = (origin or "").strip().rstrip("/")
    return loopback_origin() if o and o in set(served_origins()) else o


def uris_to_register() -> list[str]:
    """EVERY callback the operator has to paste into the console — the answer to «what do I register».

    ⚠️ It is not `redirect_uris()`, and the difference cost the first real connect (V2-687, 2026-09-14):
    the redirect is DERIVED from the origin the browser is on. Since `normalize_origin()` collapses this
    engine's two local listeners onto loopback, that is once again ONE list of five — but five that Google
    will actually accept, which the ten never were.
    """
    out: list[str] = []
    for uri in redirect_uris(loopback_origin()):
        if uri not in out:
            out.append(uri)
    return out


def check_registered(uris: list[str] | None = None, timeout: float = 8.0) -> dict:
    """Ask GOOGLE whether each redirect URI is registered — before anyone opens a consent screen.

    Registering a redirect URI is the one step of this setup that happens entirely in somebody else's
    console, and until 2026-09-14 the only way to find out whether it had worked was to run a whole
    consent flow and read `Error 400` at the end of it. That is a terrible feedback loop: the operator
    pastes five addresses, comes back, presses Connect, and gets an error that names neither the address
    it sent nor the box it should have gone in.

    The probe builds the SAME authorize URL the flow builds and reads the redirect Google answers with,
    following none of it: an unregistered URI comes back as a `302` to `accounts.google.com/signin/oauth/
    error` whose `authError` payload carries `redirect_uri_mismatch` AND the exact string Google received.
    Nothing is consented, no token exists and no browser opens — it stops at the first response.

    Returns `{uri: True | False | None}`; **None means «could not tell»** (no client, no network, an answer
    we do not recognise) and is never reported as a failure — an offline machine must not be told its setup
    is broken. Never raises.
    """
    import base64
    import urllib.error
    import urllib.parse
    import urllib.request

    cid = client_id()
    todo = uris if uris is not None else uris_to_register()
    out: dict[str, bool | None] = {}
    if not cid:
        return {u: None for u in todo}

    class _Stop(urllib.request.HTTPRedirectHandler):
        """Google answers the probe with a redirect; following it would fetch a sign-in page for nothing."""
        location = ""

        def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
            self.location = newurl
            return None

    for uri in todo:
        qs = urllib.parse.urlencode({
            "client_id": cid, "redirect_uri": uri, "response_type": "code",
            # A scope this app actually DECLARES. It used to send `openid`, which our Google flows never
            # request — only the Microsoft ones do — so the probe depended on a scope somebody could
            # legitimately remove from the consent screen, and would then have started failing for a reason
            # that has nothing to do with the redirect URI it exists to check. Caught 2026-09-14, by the
            # person managing the console asking whether `openid` was safe to retire.
            "scope": "https://www.googleapis.com/auth/calendar", "state": "zaelar-probe",
        })
        handler = _Stop()
        try:
            opener = urllib.request.build_opener(handler)
            req = urllib.request.Request("https://accounts.google.com/o/oauth2/v2/auth?" + qs,
                                         headers={"User-Agent": "Mozilla/5.0"})
            try:
                opener.open(req, timeout=timeout)
            except urllib.error.HTTPError:
                pass                       # a 4xx is still an ANSWER; the location is what we read
            loc = handler.location or ""
        except Exception:                  # noqa: BLE001 — no network is «could not tell», never «broken»
            out[uri] = None
            continue
        if not loc:
            out[uri] = None
            continue
        blob = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query).get("authError", [""])[0]
        if blob:
            try:
                raw = base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4))
            except Exception:              # noqa: BLE001
                out[uri] = None
                continue
            out[uri] = b"redirect_uri_mismatch" not in raw
        else:
            # No error payload at all: Google accepted the address and is asking the human to sign in.
            out[uri] = "/signin/oauth/error" not in loc
    return out


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
