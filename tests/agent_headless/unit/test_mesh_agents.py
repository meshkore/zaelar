"""Asking the mesh before opening a browser (V2-167 · second half).

The three browser cases that failed did so against defences built to stop exactly what a browser does:
Booking's `chal_t=` challenge, Google's CAPTCHA. The mesh serves those same domains over plain HTTP, and the
numbers behind this module were measured live against the public Oracle on 2026-08-19:

    POST /v1/search  "hotel in Madrid"          -> intent bookings.hotels,  roomrover (free, online)
    POST roomrover   explicit ISO dates          -> 10 real properties with booking links, ~1 s
    POST /v1/search  "flight from Madrid to Rome" -> intent bookings.flights, aerocast (free)
    POST aerocast    explicit ISO dates          -> 10 real offers with price and carrier

Everything below is offline: the network is faked, because a unit test that depends on a third party being up
tells you about the third party, not about us. What is asserted is the CONTRACT and the four decisions that
cost real failures elsewhere — free-only, never pay a 402, the `prompt` field, the card's path but not its
host.
"""
from __future__ import annotations

import pytest

from nucleo import mesh_agents as m


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Nothing in this file may touch the real Oracle. A test that silently reaches the network is a test that
    passes for the wrong reason on a good day and fails for the wrong reason on a bad one."""
    def _boom(*a, **k):
        raise AssertionError("un test tocó la red de verdad")
    monkeypatch.setattr(m, "_post", _boom)
    monkeypatch.setattr(m, "_get", _boom)
    m._cards.clear()
    yield
    m._cards.clear()


FREE = {"agent_id": "roomrover", "endpoint": "https://roomrover.example", "online": True,
        "status": "available", "capabilities": ["hotels"], "pricing": {"amount": 0, "currency": "free"}}
PAID = {"agent_id": "pricey", "endpoint": "https://pricey.example", "online": True,
        "status": "available", "pricing": {"amount": 0.01, "currency": "USDC"}}
UNPRICED = {"agent_id": "mystery", "endpoint": "https://mystery.example", "online": True, "status": "available"}
OFFLINE = {"agent_id": "ghost", "endpoint": "https://ghost.example", "online": False,
           "pricing": {"amount": 0, "currency": "free"}}


def _oracle(agents, intent="bookings.hotels"):
    return lambda url, body, timeout=None: (200, {"intent": intent, "query_id": 1, "agents": agents})


# ── money ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_only_free_agents_come_back(monkeypatch):
    monkeypatch.setattr(m, "_post", _oracle([FREE, PAID]))
    monkeypatch.setattr(m, "_get", lambda url, timeout=None: None)
    assert [a["agent_id"] for a in m.find("hotel in Madrid")["agents"]] == ["roomrover"]


def test_an_agent_we_cannot_price_counts_as_paid(monkeypatch):
    """Deliberately asymmetric: skipping a free agent costs one fallback to the browser, calling a paid one
    costs money nobody authorised."""
    monkeypatch.setattr(m, "_post", _oracle([UNPRICED]))
    monkeypatch.setattr(m, "_get", lambda url, timeout=None: None)
    assert m.find("hotel in Madrid")["agents"] == []


def test_but_its_own_card_can_prove_it_is_free(monkeypatch):
    """The Oracle's result often carries no price at all; the agent's card does. Measured: roomrover's card
    says `{"unit": "request", "amount": 0, "currency": "free"}`."""
    monkeypatch.setattr(m, "_post", _oracle([UNPRICED]))
    monkeypatch.setattr(m, "_get", lambda url, timeout=None: {"pricing": {"amount": 0, "currency": "free"}})
    assert [a["agent_id"] for a in m.find("hotel in Madrid")["agents"]] == ["mystery"]


def test_a_402_is_reported_and_never_paid(monkeypatch):
    monkeypatch.setattr(m, "_post", lambda url, body, timeout=None: (402, {"amount": "0.01 USDC"}))
    monkeypatch.setattr(m, "_get", lambda url, timeout=None: None)
    res = m.ask(FREE, "hotel in Madrid 2026-09-10")
    assert res["ok"] is False and res["payment_required"] is True
    assert res["challenge"] == {"amount": "0.01 USDC"}


def test_an_offline_agent_is_not_offered(monkeypatch):
    monkeypatch.setattr(m, "_post", _oracle([OFFLINE]))
    monkeypatch.setattr(m, "_get", lambda url, timeout=None: None)
    assert m.find("hotel in Madrid")["agents"] == []


def test_the_oracle_is_asked_through_prompt_because_that_is_what_parses(monkeypatch):
    """The costliest gotcha of the two, because it fails QUIETLY. `query` alone is a BM25 keyword match over an
    English catalogue: «vuelo de Madrid a Roma» comes back 200 with zero agents and looks exactly like «nobody
    on the mesh does this», while the same words in `prompt` resolve to `bookings.flights` and aerocast. A
    whole domain of the mesh was invisible for one missing field."""
    seen = {}
    monkeypatch.setattr(m, "_post", lambda url, body, timeout=None: (seen.update(body) or (200, {"agents": []})))
    m.find("vuelo de Madrid a Roma")
    assert seen["prompt"] == "vuelo de Madrid a Roma"
    assert seen["query"] == seen["prompt"]


# ── the call contract ─────────────────────────────────────────────────────────────────────────────────────
def test_the_free_text_field_is_prompt_not_query(monkeypatch):
    """The gotcha `integrations/openclaw-plugin` already paid for: real agents branch on `body.prompt` and
    ignore `query`, so a well-formed `{"query": …}` comes back 400. Both are sent."""
    seen = {}
    monkeypatch.setattr(m, "_post", lambda url, body, timeout=None: (seen.update(body) or (200, {"count": 0})))
    monkeypatch.setattr(m, "_get", lambda url, timeout=None: None)
    m.ask(FREE, "hotel in Madrid check-in 2026-09-10")
    assert seen["prompt"] == "hotel in Madrid check-in 2026-09-10"
    assert seen["query"] == seen["prompt"]


def test_the_path_comes_from_the_card_and_the_host_never_does(monkeypatch):
    """The other gotcha, and the reason it matters: foodlens advertises a hostname with NO DNS record while the
    origin the Oracle verified serves the same path fine. Trusting the card's host trades a 404 for a network
    failure."""
    seen = {}
    monkeypatch.setattr(m, "_get", lambda url, timeout=None:
                        {"contact": {"http": "https://no-such-host.invalid/v1/analyze"}})
    monkeypatch.setattr(m, "_post", lambda url, body, timeout=None: (seen.update(url=url) or (200, {})))
    m.ask({"agent_id": "x", "endpoint": "https://verified.example"}, "algo")
    assert seen["url"] == "https://verified.example/v1/analyze"
    assert "no-such-host" not in seen["url"]


def test_an_endpoint_that_already_names_a_path_needs_no_card(monkeypatch):
    monkeypatch.setattr(m, "_get", lambda url, timeout=None: pytest.fail("no debería pedir la ficha"))
    seen = {}
    monkeypatch.setattr(m, "_post", lambda url, body, timeout=None: (seen.update(url=url) or (200, {})))
    m.ask({"agent_id": "x", "endpoint": "https://a.example/v1/custom"}, "algo")
    assert seen["url"] == "https://a.example/v1/custom"


# ── fall back to the browser ──────────────────────────────────────────────────────────────────────────────
def test_a_mesh_that_is_down_is_not_an_error(monkeypatch):
    """The whole point of the fallback: if this raised, a mesh outage would break every web errand — the
    browser has to stay the plan."""
    monkeypatch.setattr(m, "_post", lambda url, body, timeout=None: (0, None))
    assert m.find("hotel in Madrid") == {"intent": "", "agents": []}
    assert m.serve("hotel in Madrid")["ok"] is False


def test_no_agent_says_so_in_words(monkeypatch):
    """«No hay ningún agente para esto» is worth hearing BEFORE zaelar opens a browser for four minutes."""
    monkeypatch.setattr(m, "_post", _oracle([], intent="general"))
    res = m.serve("arréglame la caldera")
    assert res["ok"] is False and "agente" in res["reason"]


# ── the genetic part: the learned route ───────────────────────────────────────────────────────────────────
def test_a_successful_errand_teaches_the_route(monkeypatch, tmp_path):
    store: dict = {}
    monkeypatch.setattr(m, "_routes", lambda: store.get("r", {}))
    monkeypatch.setattr(m, "remember_route",
                        lambda intent, agent: store.__setitem__(
                            "r", {**store.get("r", {}),
                                  intent: {"at": 9e9, "agent": {"agent_id": agent["agent_id"],
                                                                "endpoint": agent["endpoint"]}}}))
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "bookings.hotels", "agents": [FREE]})
    monkeypatch.setattr(m, "ask", lambda agent, prompt, fields=None: {"ok": True, "data": {"count": 10}})
    assert m.serve("hotel in Madrid")["ok"] is True
    assert m.route_for("bookings.hotels")["agent_id"] == "roomrover"


def test_a_learned_route_is_tried_first(monkeypatch):
    import time as _t
    cached = {"agent_id": "roomrover", "endpoint": "https://roomrover.example"}
    monkeypatch.setattr(m, "_routes", lambda: {"bookings.hotels": {"at": _t.time(), "agent": cached}})
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "bookings.hotels", "agents": [PAID]})
    order = []
    monkeypatch.setattr(m, "ask", lambda agent, prompt, fields=None: (order.append(agent["agent_id"]),
                                                         {"ok": True, "data": {}})[1])
    monkeypatch.setattr(m, "remember_route", lambda *a: None)
    m.serve("hotel in Madrid")
    assert order[0] == "roomrover"


def test_but_a_stale_route_is_ignored(monkeypatch):
    """A cache, not a truth: a publisher that disappears must cost one failed call, not a permanently wrong
    route."""
    monkeypatch.setattr(m, "_routes",
                        lambda: {"bookings.hotels": {"at": 0, "agent": {"agent_id": "old",
                                                                       "endpoint": "https://old.example"}}})
    assert m.route_for("bookings.hotels") is None


def test_an_unclassified_errand_never_teaches_a_route(monkeypatch):
    """`general` is the Oracle's «I could not classify this», not a kind of errand — and it is the NORMAL
    answer for a query it still serves («entradas de teatro en Madrid» → intent `general`, agent
    `ticketlumen`). Keying a route on it would send the next plumber or bicycle errand to the theatre agent."""
    store = {}
    monkeypatch.setattr(m, "_routes", lambda: store)
    monkeypatch.setattr(m, "kv_write", lambda *a: None, raising=False)
    m.remember_route("general", FREE)
    assert store == {}
    assert m.route_for("general") is None


# ── auth: a gated agent's bearer comes from the store, and only then ──────────────────────────────────────
# Some mesh agents gate their skills behind a bearer of their own issue (e.g. to cap the provider bill their
# calls run up). The credential lives in the credentials store under MESH_BEARER_<AGENT_ID>, endpoint host as
# fallback key. No entry, no header — public agents keep being called exactly as before, which is why one of
# these tests hands `ask()` a legacy `_post` double WITHOUT a `bearer` parameter and expects it to still work.

GATED = {"agent_id": "zaelar-connectors", "endpoint": "https://zc.example.com", "online": True,
         "status": "available", "pricing": {"amount": 0, "currency": "free"}}

# Captured at import time, BEFORE the autouse fixture swaps `_post` for the network trap — the header test
# below exercises the real assembly with urlopen faked, which is not "touching the network".
_REAL_POST = m._post


def test_a_gated_agent_gets_its_stored_bearer_attached(monkeypatch):
    from config import credentials
    seen = {}

    def fake_post(url, body, timeout=None, bearer=None):
        seen["bearer"] = bearer
        return 200, {"ok": True}

    monkeypatch.setattr(m, "_post", fake_post)
    monkeypatch.setattr(m, "_get", lambda url, timeout=None: None)
    monkeypatch.setattr(credentials, "get",
                        lambda k: "tok-123" if k == "MESH_BEARER_ZAELAR_CONNECTORS" else "")
    r = m.ask(GATED, "search plumbers in Soria")
    assert r["ok"] is True
    assert seen["bearer"] == "tok-123"


def test_an_agent_without_a_stored_bearer_is_called_exactly_as_before(monkeypatch):
    """The double deliberately has the LEGACY signature (no `bearer` kwarg): if `ask()` ever passes the
    keyword unconditionally, every existing caller and test double breaks — this is the regression fence."""
    from config import credentials

    def legacy_post(url, body, timeout=None):
        return 200, {"ok": True}

    monkeypatch.setattr(m, "_post", legacy_post)
    monkeypatch.setattr(m, "_get", lambda url, timeout=None: None)
    monkeypatch.setattr(credentials, "get", lambda k: "")
    r = m.ask(GATED, "search plumbers in Soria")
    assert r["ok"] is True


def test_the_bearer_key_falls_back_to_the_endpoint_host(monkeypatch):
    from config import credentials
    seen = {}

    def fake_post(url, body, timeout=None, bearer=None):
        seen["bearer"] = bearer
        return 200, {"ok": True}

    monkeypatch.setattr(m, "_post", fake_post)
    monkeypatch.setattr(m, "_get", lambda url, timeout=None: None)
    monkeypatch.setattr(credentials, "get",
                        lambda k: "tok-host" if k == "MESH_BEARER_ZC_EXAMPLE_COM" else "")
    anon = dict(GATED)
    anon.pop("agent_id")
    r = m.ask(anon, "search plumbers in Soria")
    assert r["ok"] is True
    assert seen["bearer"] == "tok-host"


def test_the_authorization_header_only_exists_when_a_bearer_does(monkeypatch):
    """Exercises the real `_post` header assembly (urlopen faked): with a bearer the header is set, without
    one the request carries no authorization at all — an empty `Bearer ` header is a different bug."""
    import urllib.request as ur
    captured = {}

    class _Resp:
        status = 200

        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.headers)
        return _Resp()

    monkeypatch.setattr(ur, "urlopen", fake_urlopen)
    status, _ = _REAL_POST("https://zc.example.com/v1/x", {}, bearer="tok-9")
    assert status == 200
    assert captured["headers"].get("Authorization") == "Bearer tok-9"
    status, _ = _REAL_POST("https://zc.example.com/v1/x", {})
    assert status == 200
    assert not any(k.lower() == "authorization" for k in captured["headers"])
