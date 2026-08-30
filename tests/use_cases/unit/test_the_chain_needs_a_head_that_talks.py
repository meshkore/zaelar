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


def test_the_seeded_head_is_the_TABLE_titular_and_carries_no_secret(tmp_path):
    """`config.v2.fast_model_spec()` reads `fast.model`/`fast.base_url`, not `fast.providers[0]`: seeding only
    the ladder left the sandbox on the hardcoded fallback, so the reorder changed nothing the turn used. The
    head travels with it.

    It used to be the OPERATOR's head, copied from his live config. Since V2-500 the shipped ladder is the
    table, and copying his machine is what let the ES lab spend a night answering on last night's model
    (2026-08-30). No `api_key` is written either — the engine resolves it by endpoint from the credential
    store, and nothing secret belongs under `tests/runs/`, which nothing cleans up.
    """
    import json

    from config import models as table

    ws = tmp_path / "ws"
    ws.mkdir()
    R.seed_provider_chain(ws)
    out = json.loads((ws / "config" / "v2.json").read_text(encoding="utf-8"))

    titular = table.rungs("voice_brain")[0]
    assert out["fast"]["model"] == titular["model"], "the sandbox answers on a brain we do not ship"
    assert out["fast"]["base_url"] == titular["base_url"]
    assert out["fast"]["provider"] == titular["provider"]
    assert "api_key" not in out["fast"]
    assert "api_key" not in json.dumps(out)


def test_the_seed_IGNORES_whatever_the_operator_has_on_his_machine(tmp_path, monkeypatch):
    """The sensitivity half, and the whole point of the change: the previous seed read the operator's live
    `config/v2.json`, so a lab measured the machine it happened to run on. Pointing that variable at a config
    naming a different brain must change NOTHING."""
    import json

    engine = tmp_path / "engine"
    (engine / "config").mkdir(parents=True)
    (engine / "config" / "v2.json").write_text(json.dumps({
        "fast": {"provider": "aimlapi", "model": "un-cerebro-que-no-enviamos",
                 "base_url": "https://api.aimlapi.com/v1",
                 "providers": [{"name": "suyo", "model": "otro", "base_url": "https://api.aimlapi.com/v1"}]},
    }), encoding="utf-8")
    monkeypatch.setenv("ZAELAR_REAL_ENGINE", str(engine))

    ws = tmp_path / "ws"
    ws.mkdir()
    R.seed_provider_chain(ws)
    out = json.loads((ws / "config" / "v2.json").read_text(encoding="utf-8"))

    assert out["fast"]["model"] != "un-cerebro-que-no-enviamos"
    assert "suyo" not in json.dumps(out), "the operator's ladder reached the lab"


def test_a_seed_over_a_STALE_config_replaces_it_whole(tmp_path):
    """How the defect actually reached a round: the lab's own file survived the seed. It is written whole, so
    a block left over from a previous night cannot outlive a boot."""
    import json

    ws = tmp_path / "ws"
    (ws / "config").mkdir(parents=True)
    (ws / "config" / "v2.json").write_text(json.dumps({
        "fast": {"provider": "aimlapi", "model": "de-anoche", "providers": [{"name": "viejo"}]},
        "code_agent": {"providers": [{"name": "licencia-claude", "local_only": True}]},
    }), encoding="utf-8")

    R.seed_provider_chain(ws)
    out = json.loads((ws / "config" / "v2.json").read_text(encoding="utf-8"))
    assert "de-anoche" not in json.dumps(out) and "viejo" not in json.dumps(out)
    assert "licencia-claude" not in json.dumps(out), \
        "a local-only rung cannot exist in the cloud: a lab that keeps it measures a worker no customer has"
