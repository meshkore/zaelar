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
# So which URI Google had to match depended on which button he pressed — and registering the five the
# engine prints left the other five failing, with an error that names neither door.
#
# ⚠️ The class, worth more than the case: V2-603's origin fix was copied into this connector «from day one
# instead of being paid twice» (its own docstring says so) — and it was copied into ONE of the two callers.
# A fix that lives in a caller has to be re-applied by every caller that arrives later, which is the same
# shape as V2-626 («a rule every caller has to remember is not a rule»).
from __future__ import annotations

import urllib.parse as _u

import pytest


def _redirect_of(url: str) -> str:
    return _u.parse_qs(_u.urlparse(url).query)["redirect_uri"][0]


@pytest.fixture
def calendar():
    svc = pytest.importorskip("connectors.calendar.service")
    if not (svc.connect_url("google", "") or {}).get("ok"):
        pytest.skip("no Google OAuth client on this machine")
    return svc


@pytest.mark.parametrize("origin", ["https://local.zaelar.com:44317", "http://127.0.0.1:43917",
                                    "http://localhost:43917"])
def test_the_two_doors_send_the_SAME_return_address(calendar, origin):
    """The defect, stated as the property that was missing. Both callers are exercised through the seam each
    one really uses: the panel hands its origin straight to `authorize_url`, the card hands it in the action
    payload — and the two have to come out identical, or one of them is unregistrable."""
    from widgets.agenda import gcal

    panel = _redirect_of(calendar.connect_url("google", "", origin=origin)["url"])
    card = _redirect_of(gcal.ui_action("connect", {"provider": "google", "origin": origin}, {})["url"])
    assert panel == card == origin + "/api/calendar/callback"


def test_without_a_browser_it_still_answers_the_loopback(calendar):
    """A voice-driven connect and a worker have no page and therefore no origin. The loopback default is the
    only honest answer there — and it must not change, because it is what a self-hoster registers."""
    from widgets.agenda import gcal

    for payload in ({"provider": "google"}, {"provider": "google", "origin": ""}):
        url = gcal.ui_action("connect", payload, {})["url"]
        assert _redirect_of(url) == "http://127.0.0.1:43917/api/calendar/callback"


def test_a_shape_that_is_not_an_origin_falls_back_instead_of_travelling(calendar):
    """The payload is not a trusted field. It cannot leak a code — Google only ever redirects to a URI the
    client has REGISTERED, which is the control that actually holds here, and the same one this whole batch
    tripped over — but a `javascript:` or a fragment has no business reaching a URL we hand to a browser."""
    from widgets.agenda import gcal

    for junk in ("javascript:alert(1)", "not a url", "http://x y", "//evil", "http://a#f", ""):
        url = gcal.ui_action("connect", {"provider": "google", "origin": junk}, {})["url"]
        assert _redirect_of(url) == "http://127.0.0.1:43917/api/calendar/callback", junk


def test_the_card_actually_sends_its_own_origin():
    """The wiring, read from the widget itself: a passthrough nobody calls is worth nothing, and this one is
    invisible from Python — the value comes from the browser."""
    import pathlib
    js = (pathlib.Path(__file__).resolve().parents[4] / "widgets" / "agenda" / "widget.js").read_text("utf-8")
    body = "\n".join(L for L in js.splitlines() if not L.strip().startswith("//"))
    assert 'ctx.action("connect", {provider:"google", origin: location.origin})' in body


def test_what_the_operator_PASTES_covers_every_origin_this_engine_serves():
    """The other half of the same defect, and the one that made it read as «I did exactly what it said».
    `redirect_uris(origin)` is what the FLOW uses — one origin, five callbacks. What goes into the console
    is every origin the engine answers on, or the door he happens to use is the unregistered one."""
    from connectors.google import app

    served = app.served_origins()
    assert any(o.startswith("http://127.0.0.1:") for o in served), served
    assert any(o.startswith("https://local.zaelar.com:") for o in served), served

    todo = app.uris_to_register()
    assert len(todo) == len(served) * len(app.CALLBACK_PATHS) == 10
    assert len(todo) == len(set(todo)), "a duplicate would be pasted twice into the console"
    for origin in served:
        assert origin + "/api/calendar/callback" in todo
    assert len(app.redirect_uris()) == 5, "the FLOW still asks for one origin at a time"


def test_the_listeners_are_read_from_the_env_the_server_honours(monkeypatch):
    """A self-hoster who moves a port must not be handed a stale list — the two names are the same ones
    `server/__main__.py` reads."""
    from connectors.google import app
    monkeypatch.setenv("ZAELAR_PORT", "8080")
    monkeypatch.setenv("ZAELAR_TLS_PORT", "8443")
    assert app.served_origins() == ["http://127.0.0.1:8080", "https://local.zaelar.com:8443"]
