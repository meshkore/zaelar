"""A provider that REJECTS the request is down for us, however fast it answers (V2-682).

Measured on the operator's own engine, 2026-09-12, the English sessions (19:53 → 20:46): **15 Brain Worker
escalations, 15 deaths**, every one of them the same line —

    API Error: 400 [1210][Invalid API parameter, please check the documentation.]

— from `glm-5.3`. Nothing relayed, nothing went on cooldown, nothing reached the status panel, so the next
errand picked the same broken tier and died identically. He heard «That task couldn't be completed — a
provider failure» seven times and asked «What fucking provider failed?».

The cause was one gap in the classifier: `classify_failure` knows quota, credentials and rate-limits, and a
400 is none of the three, so `note_failure` walked away from a tier that was refusing **every** call.

The exclusion carries as much weight as the rule: a blown CONTEXT is also a 400, and its answer is compact
and continue — relaying it would blow up identically on the next tier, because the cause is the size of the
conversation and not who serves it.
"""
import time

import pytest

from nucleo.workers import providers as prov

RESET_DATE = time.strftime("%Y-%m-%d", time.localtime(time.time() + 2 * 86400))

# The real text, verbatim from the operator's `events` table.
REAL_400 = "API Error: 400 [1210][Invalid API parameter, please check the documentation.][202609130153508318fa1]"
REAL_429 = ("API Error: Request rejected (429) · [1310][Weekly/Monthly Limit Exhausted. "
            f"Your limit will reset at {RESET_DATE} 00:00:00]")
CONTEXT_400 = ("API Error: 400 {\"type\":\"invalid_request_error\",\"message\":\"input length and `max_tokens` "
               "exceed context limit: 138000 + 64000 > 200000\"}")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    fresh = prov.CooldownStore(prov._KV)
    fresh._loaded = True                                # without touching real state
    monkeypatch.setattr(fresh, "_save", lambda: None)
    monkeypatch.setattr(prov, "_store", fresh)
    monkeypatch.setattr(prov, "_is_container", lambda: False)
    for _var in {e for t in prov.KNOWN for e in t.get("env", ())}:
        monkeypatch.delenv(_var, raising=False)
    yield


def _cfg(monkeypatch, **over):
    import config.v2 as v2
    base = {"base_url": "https://api.z.ai/api/anthropic", "model": "glm-5.3"}
    base.update(over)
    monkeypatch.setattr(v2, "get", lambda k: base if k == "code_agent" else {})


def _both_tiers(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k2")


# ── the predicate: what is a rejected REQUEST and what is not ────────────────────────────────────────
@pytest.mark.parametrize("text", [
    REAL_400,
    'Error code: 400 - {"error": {"code": "1210", "message": "This model always engages in thinking '
    'and cannot be disabled; please use low, high, or max"}}',
    "API Error: 404 model not found",
    "422 Unprocessable Entity: unsupported parameter 'thinking'",
])
def test_a_deterministic_4xx_is_a_broken_request(text):
    assert prov.is_broken_request(text) is True


@pytest.mark.parametrize("text", [
    REAL_429,                       # quota — `classify_failure` owns it and answers it better
    "429 Too Many Requests",        # transient rate limit — retrying is right
    "401 unauthorized",             # credential
    "Insufficient Balance",         # empty wallet
    "connection timeout",           # no 4xx signature at all
    "500 internal server error",    # their side, transient
])
def test_what_is_NOT_a_broken_request(text):
    assert prov.is_broken_request(text) is False


def test_a_blown_context_is_never_a_broken_request():
    """It is a 400 too, and relaying it would blow up identically on the next tier."""
    assert prov.is_broken_request(CONTEXT_400) is False
    assert prov.is_context_overflow(CONTEXT_400) is True


# ── the chain: the errand moves to the next tier instead of dying fifteen times ──────────────────────
def test_the_real_400_relays_to_the_next_tier(monkeypatch):
    _both_tiers(monkeypatch)
    assert prov.pick()["name"] == "z.ai"
    nxt = prov.note_failure(REAL_400, prov.pick())
    assert nxt is not None and nxt["name"] == "deepseek", "a tier that refuses every call must be relieved"
    assert prov.pick()["name"] == "deepseek", "and the NEXT spawn must not choose the broken one again"


def test_the_broken_tier_is_retried_soon_not_parked(monkeypatch):
    """A rejected parameter is our config or their deploy — both get fixed in minutes, unlike an empty
    wallet, which does not come back until the operator tops it up."""
    _both_tiers(monkeypatch)
    prov.note_failure(REAL_400, prov.pick())
    left = prov._store.until("z.ai") - time.time()
    assert 0 < left <= prov._BROKEN_COOLDOWN_S + 5
    assert left < prov._DEPLETED_COOLDOWN_S, "a broken request must not be punished like an empty wallet"


def test_the_operator_is_told_which_provider_and_that_it_is_not_money(monkeypatch):
    """His own question that evening was «What fucking provider failed?» — the panel now answers it, and
    says the thing he would otherwise act on wrongly: this is not a balance to top up."""
    _both_tiers(monkeypatch)
    seen = {}
    import voice.health_state as hs
    monkeypatch.setattr(hs, "record", lambda svc, kind, text="": seen.update(
        {"svc": svc, "kind": kind, "text": text}))
    prov.note_failure(REAL_400, prov.pick())
    assert seen["svc"] == "code_agent"
    assert seen["kind"] == "outage", "a refusing provider is an outage, never a credit problem"
    assert "z.ai" in seen["text"]
    assert "RECHAZA" in seen["text"] and "deepseek" in seen["text"]
    assert "SIN SALDO" not in seen["text"]


def test_a_blown_context_does_not_move_the_chain(monkeypatch):
    """The counterweight: the one 400 that must NOT relay leaves the chain exactly as it was."""
    _both_tiers(monkeypatch)
    assert prov.note_failure(CONTEXT_400, prov.pick()) is None
    assert prov.pick()["name"] == "z.ai"


def test_the_local_licence_is_never_put_on_cooldown_for_this(monkeypatch):
    """Unchanged rule: the tier with no `base_url` is the operator's own licence, not an endpoint."""
    _cfg(monkeypatch)
    assert prov.note_failure(REAL_400, prov.LICENSE_TIER) is None


# ── the voice/cluster chain reads the SAME predicate (V2-252: two chains, one decision) ──────────────
def test_the_voice_chain_relays_on_a_rejected_request_too(monkeypatch):
    from nucleo.flash import provider_chain as pc
    fresh = pc.CooldownStore(pc._KV)
    fresh._loaded = True
    monkeypatch.setattr(fresh, "_save", lambda: None)
    monkeypatch.setattr(pc, "_store", fresh)
    import config.v2 as v2
    monkeypatch.setattr(v2, "get", lambda k: {"providers": [
        {"name": "uno", "base_url": "https://one.example/v1", "model": "m1", "env": ["UNO_KEY"]},
        {"name": "dos", "base_url": "https://two.example/v1", "model": "m2", "env": ["DOS_KEY"]}]}
        if k == "cluster" else {})
    monkeypatch.setenv("UNO_KEY", "a")
    monkeypatch.setenv("DOS_KEY", "b")
    assert pc.pick(pc.ROLE_CLUSTER)["name"] == "uno"
    nxt = pc.note_failure(REAL_400, role=pc.ROLE_CLUSTER)
    assert nxt is not None and nxt["name"] == "dos"
