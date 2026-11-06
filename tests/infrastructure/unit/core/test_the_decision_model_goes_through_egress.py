"""The decision model (Jev) goes out through mediated egress like every other paid call.

Measured 2026-10-24: in a mediated deployment the process holds no provider key and Jev had neither a key nor a
route, so `jev.enabled()` was False on every turn. Every guard that reads a Jev verdict to complete or correct the
model's decision (`canvas_license.verdict_grants`, `close_license`) was then reading nothing — a video the user
asked for by name was vetoed as context-bleed. A self-hosted install keeps talking to the provider directly.
"""
from __future__ import annotations

import pytest

from nucleo import jev
from nucleo.energy import egress as llm_egress

GW = "https://egress.example"
# The provider's own address — the suite points `jev.ENDPOINT` at a local stub, so it is pinned here.
PROVIDER = "https://api.typesafe.ai/v1/systemone"
TOKEN = "tok-of-this-account"


@pytest.fixture
def mediated(monkeypatch):
    monkeypatch.setattr(llm_egress, "mediated", lambda: True)
    monkeypatch.setenv("ZAELAR_GATEWAY_URL", GW + "/v1")
    monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", TOKEN)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(jev, "ENDPOINT", PROVIDER)
    yield


def test_the_decision_model_is_a_family_egress_carries():
    assert llm_egress.upstream_of(PROVIDER) == ("typesafe", "https://api.typesafe.ai")


def test_a_mediated_trip_goes_to_egress_with_this_accounts_credential(mediated):
    assert llm_egress.route_url(jev.ENDPOINT, jev._read_key()) == (f"{GW}/p/typesafe/v1/systemone", TOKEN)


def test_the_stand_in_gives_the_decision_model_a_key_so_it_is_not_silently_off(mediated):
    assert "TYPESAFE_API_KEY" in llm_egress.stand_in_for_provider_keys()
    assert jev._read_key() == TOKEN


def test_self_host_talks_to_the_provider_with_its_own_key(monkeypatch):
    monkeypatch.setattr(llm_egress, "mediated", lambda: False)
    monkeypatch.setenv("TYPESAFE_API_KEY", "own-key")
    monkeypatch.setattr(jev, "ENDPOINT", PROVIDER)
    assert llm_egress.route_url(jev.ENDPOINT, jev._read_key()) == (PROVIDER, "own-key")


# ── the client names itself (2026-10-24): egress's edge refuses `Python-urllib/x.y` with a 403 (error 1010) ─────

class _Captured(Exception):
    pass


def _capture(monkeypatch, sink: dict):
    import urllib.request

    def fake_urlopen(req, timeout=None):
        sink["url"] = req.full_url
        sink["ua"] = req.get_header("User-agent")
        raise _Captured()
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def test_a_decision_trip_names_its_client(mediated, monkeypatch):
    seen: dict = {}
    _capture(monkeypatch, seen)
    with pytest.raises(_Captured):
        jev._post_question("q", "User: hi", "Is it a greeting?", {"yes": "greets", "no": "does not"}, 1.0)
    assert seen["url"] == f"{GW}/p/typesafe/v1/systemone"
    assert seen["ua"] == llm_egress.USER_AGENT
