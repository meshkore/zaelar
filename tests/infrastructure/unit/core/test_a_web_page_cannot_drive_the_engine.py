"""A web page the operator has open cannot drive his engine (V2-778 F4-35, 2026-10-02).

Every mutating `/api/*` route of a self-hosted engine trusted whoever reached it, and «whoever» included any site
open in his browser: a cross-site `POST /api/lists` needs no preflight and minted an order with his authority, and
a page rebinding its DNS name to 127.0.0.1 could read the answers. The guard (`server/api_guard.py`) decides on the
request's facts; these pin the decision and that the real app mounts it.
"""
from __future__ import annotations

import pytest

from server import api_guard as G


def _d(**kw):
    base = dict(path="/api/lists", method="POST", peer="127.0.0.1", host="127.0.0.1:43917", origin="",
                fetch_site="", token_given="", token_set="", cloud=False)
    base.update(kw)
    return G.decide(**base)


def test_the_engines_own_page_and_its_own_tools_pass():
    assert _d(origin="http://127.0.0.1:43917", fetch_site="same-origin")[0]
    assert _d(host="local.zaelar.com:44317", origin="https://local.zaelar.com:44317")[0]
    assert _d(host="localhost:43917")[0], "a CLI or the bridge sends no Origin"
    assert _d(method="GET", path="/api/tasks")[0]


@pytest.mark.parametrize("why,kw", [
    ("another site posting", {"origin": "https://evil.example", "fetch_site": "cross-site"}),
    ("another site, no fetch metadata", {"origin": "https://evil.example"}),
    ("a look-alike name", {"origin": "http://localhost.evil.example"}),
    ("a rebound name reading", {"method": "GET", "path": "/api/tasks", "host": "evil.example"}),
    ("a rebound name writing", {"host": "evil.example:43917"}),
    ("someone on the network", {"peer": "192.168.1.20"}),
])
def test_a_page_or_a_peer_that_is_not_the_engine_is_refused(why, kw):
    assert not _d(**kw)[0], why


def test_the_token_opens_the_door_only_when_he_set_one():
    assert _d(peer="192.168.1.20", token_set="s3cret", token_given="s3cret")[0]
    assert not _d(peer="192.168.1.20", token_set="s3cret", token_given="nope")[0]
    assert not _d(peer="192.168.1.20", token_set="", token_given="")[0]


def test_in_the_cloud_a_mutation_must_come_from_the_accounts_own_site():
    cloud = dict(cloud=True, peer="172.16.0.9", host="my.zaelar.com")
    assert _d(origin="https://my.zaelar.com", **cloud)[0]
    assert _d(**cloud)[0], "no Origin: not a browser on another site (the session gate already ran)"
    assert not _d(origin="https://evil.example", **cloud)[0]
    assert not _d(origin="https://my.zaelar.com", fetch_site="cross-site", **cloud)[0]
    assert _d(origin="https://my.zaelar.com", forwarded_host="my.zaelar.com",
              **{**cloud, "host": "internal.flycast"})[0]
    assert _d(method="GET", path="/api/tasks", origin="https://evil.example", **cloud)[0], \
        "reads in the cloud are the session gate's business"


def test_the_real_app_refuses_a_rebound_page_on_lists_and_torrents():
    """The audit's own cases, against the app as it is assembled — the wiring is the fix."""
    from fastapi.testclient import TestClient
    from server import create_app
    c = TestClient(create_app(), client=("127.0.0.1", 5555))
    for path in ("/api/lists", "/api/torrent/add"):
        r = c.post(path, json={}, headers={"host": "evil.example", "origin": "https://evil.example"})
        assert r.status_code == 403, (path, r.status_code)
    r = c.post("/api/lists", json={}, headers={"origin": "https://evil.example", "sec-fetch-site": "cross-site"})
    assert r.status_code == 403
