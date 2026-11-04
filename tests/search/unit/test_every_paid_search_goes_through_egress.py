"""Every PAID search index is a family mediated egress carries, and its key is one egress stands in for.

2026-11-03: Perplexity, Brave, Tavily, Foursquare and Bright Data had no egress family. In a mediated deployment a
call to them could only succeed with the provider's own key in the process environment — which is exactly what a
mediated deployment must not hold. `route_url` logged «not a family egress carries» and the index was simply dead.
"""
from __future__ import annotations

import pytest

from nucleo.energy import egress
from search.providers import PROVIDERS


_URLS = {
    "perplexity": "https://api.perplexity.ai/v1/responses",
    "tavily": "https://api.tavily.com/search",
    "brave": "https://api.search.brave.com/res/v1/web/search",
    "openai": "https://api.openai.com/v1/responses",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
    "zai": "https://api.z.ai/api/paas/v4/web_search",
    "foursquare": "https://places-api.foursquare.com/places/search",
    "brightdata_serp": "https://api.brightdata.com/request",
    "brightdata_unlocker": "https://api.brightdata.com/request",
}


def test_every_paid_index_has_its_url_here():
    paid = {n for n, p in PROVIDERS.items() if p.paid}
    assert paid == set(_URLS), f"a paid index without its egress url in this test: {paid ^ set(_URLS)}"


@pytest.mark.parametrize("name", sorted(_URLS))
def test_the_index_is_a_family_egress_carries(name):
    family, base = egress.upstream_of(_URLS[name])
    assert family, f"{name}: {_URLS[name]} is not routed — in a mediated deployment it would need a master key"
    assert PROVIDERS[name].host in base


@pytest.mark.parametrize("name", sorted(_URLS))
def test_its_key_is_stood_in_for(name):
    assert set(PROVIDERS[name].keys) & set(egress._STANDS_IN_FOR), (
        f"{name}: none of {PROVIDERS[name].keys} is stood in for — the index would read as unkeyed in the cloud")


def test_a_mediated_call_goes_to_egress_with_the_accounts_credential(monkeypatch):
    monkeypatch.setattr(egress, "mediated", lambda: True)
    monkeypatch.setenv("ZAELAR_GATEWAY_URL", "https://gateway.example/v1")
    monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", "account-token")
    url, key = egress.route_url(_URLS["brave"], "a-master-key")
    assert url == "https://gateway.example/p/brave/web/search" and key == "account-token"
