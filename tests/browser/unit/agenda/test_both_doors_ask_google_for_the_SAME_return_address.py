# V2-687 — the operator's FIRST real Google connect, 2026-09-14, and it died at the last step:
#
#     Access blocked: This app's request is invalid
#     Error 400: redirect_uri_mismatch
#
# Everything on this side was correct and consistent, which is what made it hard to see. The client
# resolved (`app.source() == "shipped"`, project studied-reason-508412-f7, no per-connector override set),
# PKCE was fine, and the pending OAuth record proves the exact string we sent. What was NOT consistent is
# that TWO doors open this same consent and they derived the return address DIFFERENTLY:
#
#   ⚙ → Conectores → Calendario   `/api/calendar/connect` reads the REQUEST headers (V2-603's fix: a
#                                 hardcoded loopback only works for a self-host opened on that machine),
#                                 so from `https://local.zaelar.com:44317` it sends THAT origin back.
#   The agenda card's own button   went through `gcal.ui_action` → `service.connect_url(provider, tier)`
#                                 with NO origin, so it always fell back to the loopback default.
#
# ⚠️ The class, worth more than the case: V2-603's origin fix was copied into this connector «from day one
# instead of being paid twice» (its own docstring says so) — and it was copied into ONE of the two callers.
# A fix that lives in a caller has to be re-applied by every caller that arrives later, which is the same
# shape as V2-626 («a rule every caller has to remember is not a rule»).
#
# ── The second round, the same afternoon, and why agreeing was not enough ─────────────────────────────
#
# With both doors agreeing, the retry still died — and this time the engine's own probe of Google's
# authorize endpoint answered for every URI on the list, loopback included:
#
#     redirect_uri → http://127.0.0.1:43917/api/calendar/callback
#     «Si eres quien ha desarrollado la aplicación, registra el URI de redirección en la consola»
#
# Three separate defects were stacked under one error message, and only the first had been found:
#
#   1. the two doors disagreed                     (fixed above)
#   2. the list asked him to register FIVE URIs that Google will not accept: `local.zaelar.com` is a
#      DOMAIN — ours, shipped as a DNS alias of 127.0.0.1 so a local engine can be opened over TLS — and
#      Google exempts only the LOOPBACK address from domain ownership. The «remedy» of printing ten was
#      therefore half unregistrable. `normalize_origin()` collapses the two local listeners onto loopback.
#   3. the list named `/api/files/callback`, which the engine has never served: Drive answers on
#      `/api/cloudfiles/callback`, and `/api/files/*` belongs to `memory_routes` (`server/__init__.py:34`
#      says so in as many words). A wrong address on a list of five reads as «I pasted what it said».
#
# The lesson the last test pins: a list of addresses to register is only worth what it is DERIVED from.
# Hand-typed, it drifts away from the routes silently, and the drift only ever surfaces in the operator's
# browser.
from __future__ import annotations

import urllib.parse as _u

import pytest


def _redirect_of(url: str) -> str:
    return _u.parse_qs(_u.urlparse(url).query)["redirect_uri"][0]


_LOOPBACK = "http://127.0.0.1:43917"


@pytest.fixture
def calendar():
    svc = pytest.importorskip("connectors.calendar.service")
    if not (svc.connect_url("google", "") or {}).get("ok"):
        pytest.skip("no Google OAuth client on this machine")
    return svc


def _both_doors(calendar, origin: str) -> tuple[str, str]:
    from widgets.agenda import gcal

    panel = _redirect_of(calendar.connect_url("google", "", origin=origin)["url"])
    card = _redirect_of(gcal.ui_action("connect", {"provider": "google", "origin": origin}, {})["url"])
    return panel, card


@pytest.mark.parametrize("origin", ["https://local.zaelar.com:44317", "http://127.0.0.1:43917",
                                    "http://localhost:43917", "https://zaelar.example.com"])
def test_the_two_doors_send_the_SAME_return_address(calendar, origin):
    """The first defect, stated as the property that was missing. Both callers are exercised through the seam
    each one really uses: the panel hands its origin straight to `authorize_url`, the card hands it in the
    action payload — and the two have to come out identical, or one of them is unregistrable."""
    panel, card = _both_doors(calendar, origin)
    assert panel == card, f"{origin}: the panel and the card ask Google for different addresses"


@pytest.mark.parametrize("origin", ["https://local.zaelar.com:44317", "http://127.0.0.1:43917"])
def test_a_local_listener_returns_to_the_LOOPBACK_whichever_one_he_opened(calendar, origin):
    """The second defect. Both listeners are the same process, the same token store and the same
    self-contained callback page, so returning to loopback changes nothing he can observe — and it is the
    only one of the two that Google lets a self-hoster register at all."""
    panel, card = _both_doors(calendar, origin)
    assert panel == card == _LOOPBACK + "/api/calendar/callback"


def test_a_deployment_on_its_OWN_domain_still_gets_its_own_address(calendar):
    """The counterweight, and the whole of V2-603: collapsing the local pair must not re-hardcode loopback.
    A managed deployment is a different machine with a domain of its own — one it can verify, unlike ours —
    and sending that consent to 127.0.0.1 lands it on the operator's laptop, where no pending state exists."""
    panel, card = _both_doors(calendar, "https://zaelar.example.com")
    assert panel == card == "https://zaelar.example.com/api/calendar/callback"


def test_the_same_collapse_applies_to_the_video_door(calendar):
    """`video` is the other connector that derives from the origin, and it was the ORIGINAL home of V2-603.
    Fixing calendar alone would recreate, one connector over, the exact split this file opens with."""
    voauth = pytest.importorskip("connectors.video.oauth")
    assert voauth.redirect_uri("https://local.zaelar.com:44317") == _LOOPBACK + "/api/video/callback"
    assert voauth.redirect_uri("https://zaelar.example.com") == "https://zaelar.example.com/api/video/callback"


def test_without_a_browser_it_still_answers_the_loopback(calendar):
    """A voice-driven connect and a worker have no page and therefore no origin. The loopback default is the
    only honest answer there — and it must not change, because it is what a self-hoster registers."""
    from widgets.agenda import gcal

    for payload in ({"provider": "google"}, {"provider": "google", "origin": ""}):
        url = gcal.ui_action("connect", payload, {})["url"]
        assert _redirect_of(url) == _LOOPBACK + "/api/calendar/callback"


def test_a_shape_that_is_not_an_origin_falls_back_instead_of_travelling(calendar):
    """The payload is not a trusted field. It cannot leak a code — Google only ever redirects to a URI the
    client has REGISTERED, which is the control that actually holds here, and the same one this whole batch
    tripped over — but a `javascript:` or a fragment has no business reaching a URL we hand to a browser."""
    from widgets.agenda import gcal

    for junk in ("javascript:alert(1)", "not a url", "http://x y", "//evil", "http://a#f", ""):
        url = gcal.ui_action("connect", {"provider": "google", "origin": junk}, {})["url"]
        assert _redirect_of(url) == _LOOPBACK + "/api/calendar/callback", junk


def test_the_card_actually_sends_its_own_origin():
    """The wiring, read from the widget itself: a passthrough nobody calls is worth nothing, and this one is
    invisible from Python — the value comes from the browser."""
    import pathlib
    js = (pathlib.Path(__file__).resolve().parents[4] / "widgets" / "agenda" / "widget.js").read_text("utf-8")
    body = "\n".join(L for L in js.splitlines() if not L.strip().startswith("//"))
    assert 'ctx.action("connect", {provider:"google", origin: location.origin})' in body


def test_what_the_operator_PASTES_is_one_list_of_five_that_google_can_accept():
    """The registration list, after the collapse. Ten was not «five plus five»: it was five that work and
    five that a self-hoster cannot register, offered with equal confidence."""
    from connectors.google import app

    todo = app.uris_to_register()
    assert len(todo) == len(app.CALLBACK_PATHS) == 5
    assert len(todo) == len(set(todo)), "a duplicate would be pasted twice into the console"
    assert all(u.startswith(_LOOPBACK + "/") for u in todo), todo
    assert not any(app.LOCAL_TLS_HOST in u for u in todo), "a domain nobody self-hosting can verify"
    assert app.redirect_uris("https://zaelar.example.com")[0].startswith("https://zaelar.example.com/")


def test_the_listeners_are_read_from_the_env_the_server_honours(monkeypatch):
    """A self-hoster who moves a port must not be handed a stale list — the two names are the same ones
    `server/__main__.py` reads, and the collapse has to follow the port, not a frozen 43917."""
    from connectors.google import app
    monkeypatch.setenv("ZAELAR_PORT", "8080")
    monkeypatch.setenv("ZAELAR_TLS_PORT", "8443")
    assert app.served_origins() == ["http://127.0.0.1:8080", f"https://{app.LOCAL_TLS_HOST}:8443"]
    assert app.normalize_origin(f"https://{app.LOCAL_TLS_HOST}:8443") == "http://127.0.0.1:8080"
    assert app.uris_to_register()[0].startswith("http://127.0.0.1:8080/")


def test_every_callback_we_ask_him_to_register_is_a_route_we_serve():
    """The third defect, and the only one of the three that a test could have caught the day it was written.

    `CALLBACK_PATHS` was hand-typed next to the connectors' names, and `files` does not answer on
    `/api/files/callback` — that prefix belongs to `memory_routes`. So the list handed over an address the
    engine has never served while omitting the one Drive really uses, and the flow would have died with the
    same `redirect_uri_mismatch` for a completely different reason, after he had done everything right.
    """
    from connectors.google import app

    served: set[str] = set()
    for mod in ("connectors.calendar.server_api", "connectors.video.server_api",
                "connectors.photos.server_api", "connectors.files.server_api"):
        router = pytest.importorskip(mod).router
        served |= {getattr(r, "path", "") for r in router.routes}

    missing = [p for p in app.CALLBACK_PATHS if p not in served]
    # Gmail's OAuth callback has no router at all — `server/email_api.py`, named by
    # `connectors/email/oauth.py:7`, does not exist. It is listed here because the day it is built it will
    # already be registered, and named here so the gap is DECLARED instead of discovered in a browser.
    assert missing == ["/api/email/callback"], missing
    assert "/api/cloudfiles/callback" in served and "/api/files/callback" not in served


# ── Asking Google instead of guessing ────────────────────────────────────────────────────────────────

def _fake_google(monkeypatch, *, location="", boom=False):
    """Stand in for `accounts.google.com`, so what is measured is how the probe READS an answer.

    The handler the probe builds is the one that records the redirect, so the fake opener writes the
    location onto it exactly the way `HTTPRedirectHandler.redirect_request` would — anything less would be
    testing the double instead of the parsing.
    """
    import urllib.request

    class _Opener:
        def __init__(self, handler):
            self._handler = handler

        def open(self, req, timeout=None):
            if boom:
                raise OSError("no network")
            self._handler.location = location
            return None

    monkeypatch.setattr(urllib.request, "build_opener", _Opener)


def _err_url(payload: bytes) -> str:
    """The shape Google really answers with: a redirect to its error page carrying a base64 payload."""
    import base64
    import urllib.parse
    blob = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return "https://accounts.google.com/signin/oauth/error?" + urllib.parse.urlencode({"authError": blob})


def test_an_unregistered_uri_is_reported_as_NOT_registered(monkeypatch):
    """The whole point: the operator can find out BEFORE opening a consent screen, instead of after."""
    from connectors.google import app

    monkeypatch.setattr(app, "client_id", lambda: "probe.apps.googleusercontent.com")
    _fake_google(monkeypatch, location=_err_url(b"\n\x15redirect_uri_mismatch"))
    assert app.check_registered(["http://127.0.0.1:43917/api/calendar/callback"]) == {
        "http://127.0.0.1:43917/api/calendar/callback": False}


def test_a_registered_uri_is_the_one_google_asks_a_human_to_sign_in_for(monkeypatch):
    from connectors.google import app

    monkeypatch.setattr(app, "client_id", lambda: "probe.apps.googleusercontent.com")
    _fake_google(monkeypatch, location="https://accounts.google.com/o/oauth2/v2/auth/oauthchooseaccount?x=1")
    assert app.check_registered(["http://127.0.0.1:43917/api/calendar/callback"]) == {
        "http://127.0.0.1:43917/api/calendar/callback": True}


def test_a_DIFFERENT_error_is_not_reported_as_an_unregistered_uri(monkeypatch):
    """`invalid_client` means the address was never the question. Reporting it as «not registered» would
    send the operator back to the console to re-paste five URIs that were already fine."""
    from connectors.google import app

    monkeypatch.setattr(app, "client_id", lambda: "probe.apps.googleusercontent.com")
    _fake_google(monkeypatch, location=_err_url(b"\n\x0einvalid_client"))
    assert app.check_registered(["http://127.0.0.1:43917/api/calendar/callback"]) == {
        "http://127.0.0.1:43917/api/calendar/callback": True}


def test_no_network_and_no_client_both_answer_I_CANNOT_TELL(monkeypatch):
    """The asymmetry that matters. A machine that is offline, or has no client yet, must never be told its
    setup is broken — «could not tell» and «not registered» send the operator to two different places."""
    from connectors.google import app

    uri = "http://127.0.0.1:43917/api/calendar/callback"
    monkeypatch.setattr(app, "client_id", lambda: "")
    assert app.check_registered([uri]) == {uri: None}, "no client is not a failed registration"

    monkeypatch.setattr(app, "client_id", lambda: "probe.apps.googleusercontent.com")
    _fake_google(monkeypatch, boom=True)
    assert app.check_registered([uri]) == {uri: None}, "an unreachable Google is not a failed registration"
