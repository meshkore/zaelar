"""The harness must hand the text channel a provider rung that ANSWERS.

Measured 2026-08-21: `POST /api/flash/say` returned `{"ok": false, "error": "402 Insufficient Balance"}`
while the same log, in the same second, showed the VOICE channel relaying past that rung to a live one.
The text channel catches the provider error and returns it — it never tries the next rung. So a live
failover behind a dead titular is, for this channel, no failover at all: eight hours of measuring window
were spent on a preflight that could not have passed.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import run as R

A = {"name": "titular", "base_url": "https://a.example", "model": "pro", "env": ["A_KEY"]}
B = {"name": "failover", "base_url": "https://b.example", "model": "flash", "env": ["B_KEY"]}
C = {"name": "arnes-mismo-modelo", "base_url": "https://b.example", "model": "pro", "env": ["B_KEY"]}


def _answers(alive: set):
    def probe(rung, **kw):
        name = rung.get("name")
        return (True, "HTTP 200") if name in alive else (False, "HTTP 402 Insufficient Balance")
    return probe


def test_a_live_titular_is_left_exactly_where_the_operator_put_it(monkeypatch):
    """Measuring the product means measuring the route the product uses. No reorder without a reason."""
    monkeypatch.setattr(R, "rung_answers", _answers({"titular", "failover"}))
    chain, moved = R._live_rung_first([A, B])
    assert [x["name"] for x in chain] == ["titular", "failover"]
    assert moved == "", "an untouched chain must not be announced as touched"


def test_a_refusing_titular_yields_the_head_to_one_that_answers(monkeypatch):
    monkeypatch.setattr(R, "rung_answers", _answers({"failover"}))
    chain, moved = R._live_rung_first([A, B])
    assert [x["name"] for x in chain] == ["failover", "titular"]
    assert "no contesta" in moved and "failover" in moved


def test_nobody_is_dropped_and_the_rest_keep_their_order(monkeypatch):
    """The dead rung stays in the chain. Deleting the operator's config is not the harness's call, and the
    engine's OTHER channels do relay past it."""
    monkeypatch.setattr(R, "rung_answers", _answers({"arnes-mismo-modelo"}))
    chain, _moved = R._live_rung_first([A, B, C])
    assert [x["name"] for x in chain] == ["arnes-mismo-modelo", "titular", "failover"]


def test_when_NOBODY_answers_the_operators_order_survives(monkeypatch):
    """A chain nobody can serve must reach the preflight untouched, so it refuses with the real reason.
    Promoting a rung that cannot talk would only move the failure later and dress it as the product's."""
    monkeypatch.setattr(R, "rung_answers", _answers(set()))
    chain, moved = R._live_rung_first([A, B])
    assert [x["name"] for x in chain] == ["titular", "failover"]
    assert "NINGÚN" in moved


def test_an_empty_chain_is_not_a_crash(monkeypatch):
    assert R._live_rung_first([]) == ([], "")


def test_the_probe_carries_a_user_agent(monkeypatch):
    """A bare urllib request has none, and Cloudflare answers 1010 to it. The first version of this probe
    declared two LIVE providers dead for exactly that reason."""
    seen = {}

    class _Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    import urllib.request as ur
    monkeypatch.setattr(R, "__dummy__", None, raising=False)
    monkeypatch.setattr(ur, "urlopen", lambda req, timeout=None: seen.update(
        {"ua": req.headers.get("User-agent"), "url": req.full_url}) or _Resp())
    from config import credentials as cred
    monkeypatch.setattr(cred, "get", lambda name: "k-123")
    ok, why = R.rung_answers(A)
    assert ok and "200" in why
    assert seen["ua"] and "zaelar" in seen["ua"].lower()
    assert seen["url"] == "https://a.example/chat/completions"


def test_a_rung_with_no_credential_is_not_asked(monkeypatch):
    from config import credentials as cred
    monkeypatch.setattr(cred, "get", lambda name: "")
    ok, why = R.rung_answers(A)
    assert not ok and "credencial" in why


def test_the_SAME_brain_on_another_route_wins_over_a_smaller_one(monkeypatch):
    """The operator's failover carries a SMALLER model than the titular (`flash` behind `pro`). Promoting
    by position alone would swap the brain under measurement, and a round against flash is not comparable
    with yesterday's against pro."""
    monkeypatch.setattr(R, "rung_answers", _answers({"failover", "arnes-mismo-modelo"}))
    chain, moved = R._live_rung_first([A, B, C])
    assert chain[0]["name"] == "arnes-mismo-modelo"
    assert chain[0]["model"] == "pro"
    assert "OTRO CEREBRO" not in moved


def test_a_different_brain_is_allowed_but_SAID_OUT_LOUD(monkeypatch):
    """When nothing carries the titular's model, measuring beats not measuring — but the row must know."""
    monkeypatch.setattr(R, "rung_answers", _answers({"failover"}))
    chain, moved = R._live_rung_first([A, B, C])
    assert chain[0]["name"] == "failover"
    assert "OTRO CEREBRO" in moved and "flash" in moved


def test_the_seeded_head_is_the_operators_and_carries_NO_secret(tmp_path):
    """`config.v2.fast_model_spec()` reads `fast.model`/`fast.base_url`, not `fast.providers[0]`: seeding
    only the ladder left the sandbox on the hardcoded fallback, so the reorder changed nothing the turn
    used. And `api_key` stays out — the engine resolves it by endpoint from the credential store."""
    import json
    src = tmp_path / "v2.json"
    src.write_text(json.dumps({"fast": {"provider": "aimlapi", "model": "deepseek-v4-pro",
                                        "base_url": "https://api.deepseek.com",
                                        "api_key": "sk-NO-DEBE-VIAJAR", "providers": [A]}}),
                   encoding="utf-8")
    head = R._fast_head(src)
    assert head == {"provider": "aimlapi", "model": "deepseek-v4-pro",
                    "base_url": "https://api.deepseek.com"}
    assert "api_key" not in head


def test_a_head_from_an_unreadable_config_is_empty_not_a_crash(tmp_path):
    bad = tmp_path / "nope.json"
    bad.write_text("{not json", encoding="utf-8")
    assert R._fast_head(bad) == {}
