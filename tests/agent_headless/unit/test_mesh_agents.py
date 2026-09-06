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
    out = m.find("hotel in Madrid")
    assert out["intent"] == "" and out["agents"] == []
    # …and it must say it never REACHED the Oracle, or V2-594 would cache an outage as «nobody does hotels».
    assert out["reached"] is False
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


# ── V2-580 · the answer carries what the agent claims to be ───────────────────────────────────────────────
def test_a_successful_answer_says_what_the_agent_claims_to_serve(monkeypatch):
    """Measured 2026-09-05: asked for a TRAIN, the Oracle ranked `aerocast` (flights) first and it answered
    `ok: true` with ten FLIGHT offers. The caller is under orders to check the domain of what came back, and
    a wrong-domain payload looks exactly like a right one — so the claim has to travel with the data."""
    flights = {"agent_id": "aerocast", "endpoint": "https://aerocast.example", "online": True,
               "capabilities": ["flights", "airfare"], "description": "Flight search across 300+ airlines.",
               "pricing": {"amount": 0, "currency": "free"}}
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "compute", "agents": [flights]})
    monkeypatch.setattr(m, "ask", lambda agent, prompt, fields=None: {"ok": True, "data": {"count": 10}})
    # `_routes` reads the REAL learned-route store: without this the live route this bug already taught the
    # operator's engine («compute» → aerocast) walks in and answers the test instead of the fixture.
    monkeypatch.setattr(m, "_routes", lambda: {})
    monkeypatch.setattr(m, "remember_route", lambda *a: None)
    res = m.serve("train ticket from Madrid to Barcelona on 2026-10-20")
    assert res["ok"] is True
    assert res["serves"] == ["flights", "airfare"]
    assert res["describes_itself_as"] == "Flight search across 300+ airlines."


def test_the_claim_is_trimmed_so_it_cannot_eat_the_context(monkeypatch):
    fat = {"agent_id": "chatty", "endpoint": "https://chatty.example", "online": True,
           "capabilities": [f"cap{i}" for i in range(40)], "description": "x" * 900,
           "pricing": {"amount": 0, "currency": "free"}}
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "general", "agents": [fat]})
    monkeypatch.setattr(m, "ask", lambda agent, prompt, fields=None: {"ok": True, "data": {}})
    monkeypatch.setattr(m, "_routes", lambda: {})
    res = m.serve("anything")
    assert len(res["serves"]) == m._MAX_CAPS
    assert len(res["describes_itself_as"]) == m._MAX_DESC + 1        # the ellipsis says it was cut


def test_an_agent_that_declares_nothing_adds_no_empty_keys(monkeypatch):
    """Absence must stay absent: an empty `serves: []` would read as «it claims to serve nothing», which is a
    different statement from «it did not say»."""
    mute = {"agent_id": "mute", "endpoint": "https://mute.example", "online": True,
            "pricing": {"amount": 0, "currency": "free"}}
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "general", "agents": [mute]})
    monkeypatch.setattr(m, "ask", lambda agent, prompt, fields=None: {"ok": True, "data": {}})
    monkeypatch.setattr(m, "_routes", lambda: {})
    res = m.serve("anything")
    assert "serves" not in res and "describes_itself_as" not in res
    # Both halves, or this passes trivially the day the mechanism is removed: a silent agent adds no keys
    # ONLY because a speaking one adds them.
    loud = {**mute, "capabilities": ["hotels"]}
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "general", "agents": [loud]})
    assert m.serve("anything")["serves"] == ["hotels"]


def test_the_claim_falls_back_to_the_card_when_the_oracle_row_is_bare(monkeypatch):
    """The Oracle row is often thin — the same reason `_is_free` has to read the card at all."""
    bare = {"agent_id": "ticketlumen", "endpoint": "https://tl.example", "online": True,
            "pricing": {"amount": 0, "currency": "free"}}
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "general", "agents": [bare]})
    monkeypatch.setattr(m, "ask", lambda agent, prompt, fields=None: {"ok": True, "data": {}})
    monkeypatch.setattr(m, "_routes", lambda: {})
    m._cards["https://tl.example"] = {"capabilities": ["events"], "description": "Events."}
    res = m.serve("tickets")
    assert res["serves"] == ["events"] and res["describes_itself_as"] == "Events."


# ── V2-581 · the Oracle can refuse a wrong-domain agent, and is asked to ───────────────────────────────────
def test_the_oracle_is_asked_to_refuse_a_wrong_domain_agent(monkeypatch):
    """`strict` is the request this module made after a TRAIN errand came back with ten FLIGHT offers. Zero
    is better than wrong: zero falls back to the browser, a false positive hands the user a lie."""
    seen: dict = {}
    def _spy(url, body, timeout=None):
        seen.update(body)
        return 200, {"intent": "transport.train", "coverage": "none", "agents": []}
    monkeypatch.setattr(m, "_post", _spy)
    m.find("train ticket from Madrid to Barcelona on 2026-10-20")
    assert seen["strict"] is True


def test_an_agent_the_oracle_marks_as_the_wrong_domain_is_dropped(monkeypatch):
    right = {**FREE, "domain_match": True}
    wrong = {"agent_id": "aerocast", "endpoint": "https://aerocast.example", "online": True,
             "status": "available", "domain_match": False, "pricing": {"amount": 0, "currency": "free"}}
    monkeypatch.setattr(m, "_post", _oracle([wrong, right]))
    monkeypatch.setattr(m, "_get", lambda url, timeout=None: None)
    assert [a["agent_id"] for a in m.find("hotel in Madrid")["agents"]] == ["roomrover"]


def test_silence_about_the_domain_is_not_a_mismatch(monkeypatch):
    """An older Oracle sends no `domain_match` at all. Treating the missing key as `false` would empty the
    mesh the day the field is rolled back — only an explicit `false` is a statement."""
    monkeypatch.setattr(m, "_post", _oracle([FREE]))
    monkeypatch.setattr(m, "_get", lambda url, timeout=None: None)
    assert [a["agent_id"] for a in m.find("hotel in Madrid")["agents"]] == ["roomrover"]


def test_nobody_covers_this_yet_is_said_differently_from_nobody_answered(monkeypatch):
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "wellness", "coverage": "none",
                                                   "agents": [], "reached": True})
    monkeypatch.setattr(m, "_routes", lambda: {})
    assert "todavía no hay" in m.serve("un masaje en Madrid")["reason"]
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "bookings.hotels", "coverage": "full",
                                                  "agents": []})
    assert "todavía no hay" not in m.serve("hotel in Madrid")["reason"]


# ── V2-593 · a free tier arrives as one entry in a LIST of tiers ───────────────────────────────────────────
TIERED_FREE = {"agent_id": "lucid", "endpoint": "https://lucid.example", "online": True, "status": "available",
               "pricing": [{"unit": "request", "amount": 0, "currency": "free", "use": "free daily tier"},
                           {"unit": "request", "amount": 430000, "currency": "lamports", "model": "flux-dev"}]}


def test_an_agent_is_free_when_any_of_its_tiers_is(monkeypatch):
    """Measured 2026-09-05: after the operator ruled that every usable agent must have a free tier, `lucid`
    and `ybana` published one as the first entry of a LIST — and the single-dict reader was blind to exactly
    the thing it was looking for, calling both paid."""
    monkeypatch.setattr(m, "_post", _oracle([TIERED_FREE]))
    monkeypatch.setattr(m, "_get", lambda url, timeout=None: None)
    assert [a["agent_id"] for a in m.find("draw me a picture")["agents"]] == ["lucid"]


def test_a_list_of_priced_tiers_with_no_free_one_is_still_paid(monkeypatch):
    """The rule did not loosen: a tier list buys no benefit of the doubt."""
    all_paid = {**TIERED_FREE, "agent_id": "pricey",
                "pricing": [{"unit": "request", "amount": 430000, "currency": "lamports"},
                            {"unit": "request", "amount": 850000, "currency": "lamports"}]}
    monkeypatch.setattr(m, "_post", _oracle([all_paid]))
    monkeypatch.setattr(m, "_get", lambda url, timeout=None: None)
    assert m.find("draw me a picture")["agents"] == []


def test_an_empty_or_unreadable_tier_list_is_not_free(monkeypatch):
    """Unknown still counts as paid — including a list that says nothing at all."""
    for pricing in ([], [{"unit": "request"}], ["free"]):
        mystery = {**TIERED_FREE, "agent_id": "mystery", "pricing": pricing}
        assert m._is_free(mystery) is False, pricing


def test_a_tiered_card_can_prove_a_bare_oracle_row_free(monkeypatch):
    """The row is often thin; the card is where the tiers live."""
    bare = {"agent_id": "lucid", "endpoint": "https://lucid.example", "online": True, "status": "available"}
    assert m._is_free(bare) is False
    assert m._is_free(bare, {"pricing": TIERED_FREE["pricing"]}) is True


# ── V2-594 · the workflow table answers before the network does ───────────────────────────────────────────
def test_a_known_empty_domain_never_reaches_the_oracle(monkeypatch):
    """The whole point of the negative row: no round trip, and no empty result sent through a model to have
    the emptiness narrated back. `_post` is the network trap, so reaching it fails the test by itself."""
    from nucleo import workflows as wf
    wf.forget("wellness")
    wf.note_empty("wellness", evidence="oracle coverage=none")
    try:
        res = m.serve("quiero un masaje en Sevilla")
        assert res["ok"] is False
        assert res["from_cache"] is True and res["coverage"] == "none"
        assert "todavía no hay" in res["reason"]
    finally:
        wf.forget("wellness")


def test_an_oracle_that_says_nobody_covers_this_is_remembered(monkeypatch):
    """`coverage: none` is the Oracle stating the vertical is uncovered — worth caching. «Nobody answered» is
    a transient failure, and caching that would turn one bad minute into three bad days."""
    from nucleo import workflows as wf
    wf.forget("wellness")
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "wellness", "coverage": "none",
                                                   "agents": [], "reached": True})
    monkeypatch.setattr(m, "_routes", lambda: {})
    try:
        m.serve("quiero un masaje en Sevilla")
        assert wf.plan("quiero un masaje en Sevilla").known_empty is True
    finally:
        wf.forget("wellness")


def test_an_unreachable_oracle_is_NOT_remembered(monkeypatch):
    """The distinction that makes the negative row safe: a network outage must never become three days of
    «nobody does this». Measured need — an uncovered vertical really returns an empty `coverage`, so the word
    cannot be the key; whether the Oracle ANSWERED is."""
    from nucleo import workflows as wf
    wf.forget("wellness")
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "", "agents": [], "reached": False})
    monkeypatch.setattr(m, "_routes", lambda: {})
    try:
        m.serve("quiero un masaje en Sevilla")
        assert wf.plan("quiero un masaje en Sevilla").known_empty is False
    finally:
        wf.forget("wellness")


# ── V2-598 · «give me a field» and «I broke» are different answers ────────────────────────────────────────
def _agent(**kw):
    base = {"agent_id": "aerocast", "endpoint": "https://aerocast.example", "online": True,
            "pricing": {"amount": 0, "currency": "free"}}
    base.update(kw)
    return base


def _serve_against(monkeypatch, error_body):
    """Drive `serve` down the failure path with one agent that answers a non-200 carrying `error_body`."""
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "bookings.flights", "agents": [_agent()]})
    monkeypatch.setattr(m, "_routes", lambda: {})
    # `ask` builds the URL through the card; without this the autouse network trap fires on the card fetch
    # and the test reports «tocó la red» instead of the contract it is here to pin.
    monkeypatch.setattr(m, "_skill_path", lambda endpoint: "/v1/search")
    monkeypatch.setattr(m, "_post", lambda url, body, **kw: (400, error_body))
    return m.serve("flight from Madrid to Barcelona next Friday")


def test_an_agent_that_names_its_missing_fields_earns_the_retry_advice(monkeypatch):
    """`roomrover` answers 400 with `{"error": "missing_fields", "need": [...]}`. That IS actionable: the
    caller can fill the fields and ask again, and V2-487 exists so the errand does not go to the browser when
    the answer is one field away."""
    res = _serve_against(monkeypatch, {"error": "missing_fields", "need": ["checkin", "checkout"]})
    assert res["ok"] is False
    assert res["agent_asks"]["need"] == ["checkin", "checkout"]
    assert "--field" in res["reason"]
    assert not res.get("agent_failed")


def test_an_upstream_failure_is_not_dressed_up_as_a_request_for_fields(monkeypatch):
    """Measured live 2026-09-05: `aerocast` fails on roughly half of the relative-date errands, passing a
    non-ISO date to Duffel and relaying a 422. Every one of those was reported as «the agent says what it
    needs: ask again with --field key=value» — advice that cannot work, because the fields were never
    missing. The caller loops instead of falling through to the browser."""
    duffel_422 = {"error": "upstream_error",
                  "detail": "offer_requests 422: " + '{"errors":[{"title":"Invalid type"}]}'}
    res = _serve_against(monkeypatch, duffel_422)
    assert res["ok"] is False
    assert res["agent_failed"] is True
    assert "--field" not in res["reason"], "an upstream 422 must not ask the caller for fields"
    assert res["agent_asks"]["error"] == "upstream_error"      # the cause still travels, it just is not advice


def test_a_diagnostic_cannot_eat_the_callers_context(monkeypatch):
    """The measured Duffel body was 400+ characters of upstream JSON. It names the real cause, so it is kept
    — but a diagnostic is not allowed to become the context the worker reasons in."""
    res = _serve_against(monkeypatch, {"error": "upstream_error", "detail": "x" * 4000})
    assert len(res["agent_asks"]["detail"]) <= m._DIAG_MAX + 1
    assert res["agent_asks"]["detail"].endswith("…")


def test_a_named_field_survives_alongside_a_diagnostic(monkeypatch):
    """An agent may say both at once. The presence of a diagnostic must not hide an actionable field name."""
    res = _serve_against(monkeypatch, {"error": "bad_request", "missing": ["departure_date"]})
    assert "--field" in res["reason"]
    assert res["agent_asks"]["missing"] == ["departure_date"]


# ── V2-602 · an empty answer is not a served errand ───────────────────────────────────────────────────────
def test_a_missing_field_announced_in_prose_is_still_a_missing_field(monkeypatch):
    """Measured against `ybana`: 400 with `{"error": "missing_product", "detail": "body.product is
    required"}`. It says exactly what it lacks — under diagnostic KEYS. V2-596 split need-keys from
    diagnostic-keys and started calling this «the agent broke, more data will not help», which is backwards:
    supplying `product` makes it answer with twenty offers. The WORDING separates the two cases — a missing
    field is announced as missing or required; a broken upstream calls what it received INVALID."""
    res = _serve_against(monkeypatch, {"error": "missing_product", "detail": "body.product is required"})
    assert "--field" in res["reason"]
    assert not res.get("agent_failed")


def test_an_invalid_value_is_still_not_a_missing_field(monkeypatch):
    """The other half of the same line: Duffel's 422 names a field and calls it INVALID, never absent. It
    must keep failing as breakage, or V2-596 is undone."""
    duffel = {"error": "upstream_error",
              "detail": "offer_requests 422: Field 'departure_date' is invalid. Expected ISO 8601"}
    res = _serve_against(monkeypatch, duffel)
    assert res["agent_failed"] is True
    assert "--field" not in res["reason"]


def test_an_ok_with_no_rows_does_not_end_the_search(monkeypatch):
    """Measured 2026-09-06: asked in English for sneakers, `ebay-finder` answered 200 with `count: 0` and
    `serve` took it, never reaching `ybana` — which had twenty real offers. The vertical looked alive and
    returned nothing, and `ok: true` made it indistinguishable from a real answer."""
    empty = _agent(agent_id="empty-one")
    full = _agent(agent_id="full-one", endpoint="https://full.example")
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "shopping", "agents": [empty, full]})
    monkeypatch.setattr(m, "_routes", lambda: {})
    monkeypatch.setattr(m, "remember_route", lambda *a: None)
    monkeypatch.setattr(m, "ask", lambda agent, prompt, fields=None: (
        {"ok": True, "data": {"count": 0, "offers": []}} if agent["agent_id"] == "empty-one"
        else {"ok": True, "data": {"count": 2, "offers": [{"x": 1}, {"x": 2}]}}))
    res = m.serve("buy sneakers")
    assert res["ok"] is True
    assert res["agent"] == "full-one", "una respuesta vacía se quedó con el encargo"
    assert res["data"]["count"] == 2


def test_an_empty_answer_is_still_returned_when_nobody_does_better(monkeypatch):
    """«Nobody has this» is a real result. Held back only so a better one can win — never discarded, and
    never downgraded to «los agentes no contestaron», which would send the errand to the browser for a
    question the mesh already answered."""
    a, b = _agent(agent_id="e1"), _agent(agent_id="e2", endpoint="https://e2.example")
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "shopping", "agents": [a, b]})
    monkeypatch.setattr(m, "_routes", lambda: {})
    monkeypatch.setattr(m, "remember_route", lambda *a_: None)
    monkeypatch.setattr(m, "ask", lambda agent, prompt, fields=None: {"ok": True, "data": {"count": 0}})
    res = m.serve("buy a unicorn")
    assert res["ok"] is True and res["empty"] is True
    assert res["agent"] in ("e1", "e2")


def test_an_unrecognised_payload_is_never_thrown_away():
    """`_is_empty_payload` inspects only the shapes these agents use. Anything it does not understand counts
    as NOT empty — a payload we cannot read must never be discarded as if it were nothing."""
    assert m._is_empty_payload({"count": 0}) is True
    assert m._is_empty_payload({"offers": []}) is True
    assert m._is_empty_payload(None) is True
    assert m._is_empty_payload({"count": 3}) is False
    assert m._is_empty_payload({"weird": {"nested": "thing"}}) is False
    assert m._is_empty_payload({"summary": "no rows but here is prose"}) is False
