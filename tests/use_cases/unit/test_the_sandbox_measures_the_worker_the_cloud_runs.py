"""A platform that seeds only the fast chain measures a Brain Worker nobody ships.

Found 2026-08-27, watching the lab's own log: `worker[1]: ClaudeCodeSession start (model=default, …)` while
the operator's engine and every cloud Machine run a named model. The cause was not a bug in the worker — the
sandbox boots a fresh workspace, `seed_provider_chain` copied `fast` and nothing else, so `code_agent` came
back empty and `providers.pick()` fell to the first healthy rung of the catalogue with no model declared.

It matters more here than for the fast chain: in the cloud a worker can only be Z.AI or DeepSeek, because
inside a container there is no local Claude Code license to fall back to. A platform measuring with that
license would be measuring a worker no customer can ever have.

`api_key` is excluded for the same reason as the fast head: the engine resolves keys by endpoint from the
credential store, so nothing secret gets written under `tests/runs/` where nothing cleans it up.
"""
from __future__ import annotations

import json

from tests.use_cases.e2e.agent import run as R


def _seed(tmp_path, monkeypatch, cfg: dict) -> dict:
    engine = tmp_path / "engine"
    (engine / "config").mkdir(parents=True)
    (engine / "config" / "v2.json").write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setenv("ZAELAR_REAL_ENGINE", str(engine))
    ws = tmp_path / "ws"
    ws.mkdir()
    R.seed_provider_chain(ws)
    return json.loads((ws / "config" / "v2.json").read_text(encoding="utf-8"))


_FAST = {"fast": {"model": "m", "base_url": "https://api.deepseek.com",
                  "providers": [{"name": "t", "model": "m", "base_url": "https://api.deepseek.com"}]}}


def test_the_worker_the_operator_runs_travels_to_the_sandbox(tmp_path, monkeypatch):
    out = _seed(tmp_path, monkeypatch, {**_FAST, "code_agent": {
        "base_url": "https://api.z.ai/api/anthropic", "model": "glm-5.3", "provider": "claude_code",
        "providers": [{"name": "z.ai", "model": "glm-5.3"}, {"name": "deepseek"}]}})
    assert out["code_agent"]["model"] == "glm-5.3", "the sandbox boots workers on some other brain"
    assert out["code_agent"]["base_url"] == "https://api.z.ai/api/anthropic"
    assert [p["name"] for p in out["code_agent"]["providers"]] == ["z.ai", "deepseek"], \
        "the relay ladder did not travel — a sandbox that cannot relay dies where production would survive"


def test_and_its_key_does_NOT(tmp_path, monkeypatch):
    """Same discipline as the fast head: keys are resolved by endpoint, never written under tests/runs/."""
    out = _seed(tmp_path, monkeypatch, {**_FAST, "code_agent": {"model": "glm-5.3", "api_key": "SECRET"}})
    assert "api_key" not in out["code_agent"]
    assert "SECRET" not in json.dumps(out)


def test_an_engine_without_a_worker_config_seeds_nothing_rather_than_an_empty_shell(tmp_path, monkeypatch):
    """Sensitivity: writing `code_agent: {}` would PIN the sandbox to an empty config instead of letting the
    catalogue choose — a silent downgrade dressed as a seed."""
    out = _seed(tmp_path, monkeypatch, _FAST)
    assert "code_agent" not in out
    assert out["fast"]["providers"], "seeding the worker must not have broken the fast chain"
