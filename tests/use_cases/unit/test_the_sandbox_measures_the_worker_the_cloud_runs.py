"""A lab that seeds only the fast chain measures a Brain Worker nobody ships.

Found 2026-08-27, watching the lab's own log: `worker[1]: ClaudeCodeSession start (model=default, …)` while
the operator's engine and every cloud Machine run a named model. The cause was not a bug in the worker — the
sandbox boots a fresh workspace, `seed_provider_chain` copied `fast` and nothing else, so `code_agent` came
back empty and `providers.pick()` fell to the first healthy rung of the catalogue with no model declared.

It matters more here than for the fast chain: in the cloud a worker can only be Z.AI or DeepSeek, because
inside a container there is no local Claude Code licence to fall back to. A lab measuring with that licence
would be measuring a worker no customer can ever have.

⚠️ Rewritten 2026-08-30 (V2-501 follow-up). These tests used to hand the seeder a FAKE operator engine through
`ZAELAR_REAL_ENGINE` and assert that its worker travelled. Two of them then passed for the wrong reason — the
table happens to name the same brain, so they would have gone green whatever the fake config said. The source
of truth is now `config/models.default.json`, so what is guarded is that the lab measures THE PRODUCT, and
that no operator config can move it.
"""
from __future__ import annotations

import json

from config import models as table
from tests.use_cases.e2e.agent import run as R


def _seed(tmp_path) -> dict:
    ws = tmp_path / "ws"
    ws.mkdir()
    R.seed_provider_chain(ws)
    return json.loads((ws / "config" / "v2.json").read_text(encoding="utf-8"))


def test_the_worker_the_cloud_runs_travels_to_the_sandbox(tmp_path):
    out = _seed(tmp_path)
    titular = table.rungs("brain_worker")[0]
    assert out["code_agent"]["model"] == titular["model"], "the sandbox boots workers on some other brain"
    assert out["code_agent"]["base_url"] == titular["base_url"]
    assert out["code_agent"]["provider"] == "claude_code"


def test_the_relay_ladder_travels_too(tmp_path):
    """A sandbox that cannot relay dies where production would survive — and then the round reports an engine
    defect that production does not have."""
    out = _seed(tmp_path)
    seeded = [p.get("base_url") for p in out["code_agent"]["providers"]]
    expected = [r["base_url"] for r in table.chain_for("brain_worker", names=("z.ai", "deepseek"))]
    assert seeded == expected, "the worker ladder does not match the one we ship"
    assert len(seeded) <= 2, "one failover per service — a third rung is not the product (V2-500)"


def test_no_key_is_ever_written_under_tests_runs(tmp_path):
    """Keys are resolved by endpoint from the credential store. Nothing under `tests/runs/` is ever cleaned
    up, so a secret written there outlives every round that put it there."""
    out = _seed(tmp_path)
    blob = json.dumps(out)
    assert "api_key" not in blob
    assert "sk-" not in blob and "CENTINELA" not in blob
    for rung in out["code_agent"]["providers"]:
        # `env` carries the NAME of the variable, which is not a secret and is what the engine resolves by.
        assert "api_key" not in rung


def test_the_seed_is_DEAF_to_the_operators_own_worker_config(tmp_path, monkeypatch):
    """The sensitivity half. Before, whatever the operator had on his machine that day became the lab's
    worker — including a `licencia-claude` rung that cannot exist inside a container."""
    engine = tmp_path / "engine"
    (engine / "config").mkdir(parents=True)
    (engine / "config" / "v2.json").write_text(json.dumps({
        "fast": {"model": "m", "base_url": "https://api.deepseek.com", "providers": [{"name": "t"}]},
        "code_agent": {"model": "un-worker-suyo", "base_url": "https://ejemplo.invalido",
                       "providers": [{"name": "licencia-claude", "local_only": True}]},
    }), encoding="utf-8")
    monkeypatch.setenv("ZAELAR_REAL_ENGINE", str(engine))

    blob = json.dumps(_seed(tmp_path))
    assert "un-worker-suyo" not in blob and "licencia-claude" not in blob
