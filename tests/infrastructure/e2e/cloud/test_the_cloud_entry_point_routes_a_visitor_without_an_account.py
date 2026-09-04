"""The cloud entry point, as a visitor WITHOUT a session sees it (LIVE — read-only, opt-in).

`my.zaelar.com` is a routing edge, not a server: with a session cookie it replays the request to that account's
Machine, and with NO cookie it falls back to the "smart entry" — an interstitial that sends the visitor to the
engine on their own computer. That behaviour is deliberate and it is the ONLY part of the cloud surface that can
be checked without spending money, provisioning a Machine or leaving an account behind.

WHY IT IS WORTH A TEST. The unauthenticated fallback is what every stranger who types the address gets, and it
fails in a way nobody would notice from inside: a routing change turns it into a 404, a 500 or — worse — into
something that serves real content to someone with no account, and the engine's own suite has no opinion about
it because the engine is not what answers.

⚠️ AND THE TRAP IT PINS, measured 2026-09-04. WITHOUT a session cookie the edge answers this same HTML for
EVERY path on the origin — `/m`, `/manifest.webmanifest` and `/sw.js` included, all `200 text/html`. So a
browser with no account cannot install the PWA and cannot register a service worker, because the files it needs
are not JavaScript or JSON at that moment; the manifest and the worker only become real once the cookie routes
the request to the account's Machine. That is correct (a visitor with no account has nothing to install) and it
is exactly the shape that reads as "the PWA is broken" to whoever debugs it from a logged-out browser.

READ-ONLY and OPT-IN: nothing but GETs, no account, no session, no writes. Built whole and SKIPPED unless the
runner asks for it (`ZAELAR_CLOUD_LIVE=1`) — the same shape as the connectors' live round-trip, and for the same
reason: reaching the real internet on every commit is flaky, and it would put CI traffic on production. It also
SKIPS rather than fails when the network is not there — a broken wifi is not a broken product. It is deliberately
NOT a `live` node in the map: those are removed from the deterministic run entirely, which is how a test quietly
stops being true (the third form in `test_a_test_outside_the_map_is_not_a_test.py`). Skipped is visible; absent
is not.

Run:  ZAELAR_CLOUD_LIVE=1 ./.venv/bin/python -m pytest tests/infrastructure/e2e/cloud/ -q
Env:  ZAELAR_CLOUD_URL (default https://my.zaelar.com)
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request

import pytest

CLOUD = os.getenv("ZAELAR_CLOUD_URL", "https://my.zaelar.com").rstrip("/")

pytestmark = pytest.mark.skipif(
    os.getenv("ZAELAR_CLOUD_LIVE", "") not in ("1", "true", "yes"),
    reason="reaches the real cloud entry point — enable with ZAELAR_CLOUD_LIVE=1 "
           "(read-only GETs, no account, no cost)",
)

# Cloudflare sits in front and 403s a request whose User-Agent looks like a bot — urllib's default is blocked
# and a browser one passes (measured in `tests/voice/e2e/agent/cloud_smoke.py`, same reason). The tester is a
# legitimate client, so it presents itself as one.
_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
       "Version/17.0 Mobile/15E148 Safari/604.1")


def _get(path: str) -> tuple[int, str, str]:
    req = urllib.request.Request(CLOUD + path, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read().decode("utf-8", "replace")
    except Exception as e:                      # noqa: BLE001 — no network is not a product failure
        pytest.skip(f"{CLOUD} unreachable: {type(e).__name__}: {e}")


def test_the_entry_point_answers_at_all():
    """A dead entry point is the one outage a customer notices before we do."""
    status, _, _ = _get("/")
    assert status == 200, f"{CLOUD}/ answered {status}"


def test_a_visitor_without_a_session_is_sent_to_their_own_computer():
    """The smart entry: no cookie means no account to route to, so the visitor is handed to the engine on their
    own machine instead of an error page."""
    status, ctype, body = _get("/m")
    assert status == 200 and "text/html" in ctype
    assert "local.zaelar.com" in body, (
        "the unauthenticated fallback no longer points at the local engine — a routing change would strand "
        "every visitor without an account on a page that does nothing"
    )
    assert "location.replace" in body or "<a href" in body, "the redirect has to actually happen"


def test_the_fallback_page_gives_a_visitor_a_way_forward_without_javascript():
    """A `location.replace` alone is a dead end for anyone whose browser did not run it."""
    _, _, body = _get("/m")
    assert "<a href" in body and "local.zaelar.com" in body


def test_the_fallback_leaks_nothing_about_anybody():
    """It is served to strangers, so what it may contain is: an explanation and a link."""
    _, _, body = _get("/m")
    assert len(body) < 4000, "the fallback grew past an interstitial; check what it is serving now"
    for leak in ("zaelar_cloud_session", "@", "api_key", "sk-", "Bearer "):
        assert leak not in body, f"the unauthenticated entry page contains {leak!r}"


@pytest.mark.parametrize("path", ["/manifest.webmanifest", "/sw.js"])
def test_the_pwa_files_are_NOT_served_to_a_visitor_without_a_session(path):
    """Pins the trap in this module's docstring rather than leaving it to be rediscovered.

    These two are what a phone needs to install the app, and unauthenticated they come back as the SAME HTML
    interstitial — so "the PWA will not install" is the expected answer for somebody with no account, not a
    defect. If this ever starts returning real JavaScript or JSON to a stranger, that is the thing to look at:
    it would mean the edge is serving an account's files without a cookie."""
    status, ctype, body = _get(path)
    assert status == 200
    assert "text/html" in ctype and "local.zaelar.com" in body, (
        f"{path} no longer falls back to the interstitial for an anonymous visitor — the edge may be serving "
        f"a real Machine's file without a session (content-type: {ctype})"
    )
