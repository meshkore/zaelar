"""`--fresh` wiped the provider cooldowns, so every round burned 21% of itself on a tier it knew was dead.

Measured on the round of 2026-08-24 15:16, `search-buy-bicycle__es`, from the flow's own event timeline:

    36.0s  worker_start  worker · claude_code
    36.5s  task          proveedor sin cuota          ← dead half a second after starting
    67.4s  task          start                        ← the relay's worker finally begins
    ...
   150.0s  task          cancel                       ← the round runs out of turns

The round is 150 seconds long and the first 67 produced nothing. The engine log says why, and had said the
same thing on every single batch that day: «brain worker: "z.ai" (GLM coding plan) sin cuota hasta el
25 Aug 01:39 → relevo a "deepseek"». The cooldown store had that expiry written down — and `wipe()` deleted
it with the rest of `memory/`, so the next round went at the dead tier again with a real request.

The distinction that decides where this gets fixed: a provider cooldown is a fact about the OUTSIDE WORLD
(«this endpoint has no quota until Monday»), not something this agent learned about its operator. In
PRODUCTION `sys_kv` persists and the tier is discovered once and held for hours — so this is not a product
defect, it is an artefact of measuring against a brand-new install, and the fix belongs in the harness.

What is NOT carried over is everything else: the memory, the widgets, the config. A fresh round has to be a
fresh agent or the measurement means nothing.
"""
import json
import sqlite3

import pytest

from tests.use_cases.lab import stage


@pytest.fixture
def ws(tmp_path):
    """A workspace shaped like a lab agent's, with a sandbox DB carrying a cooldown and a memory."""
    d = tmp_path / "es"
    (d / "memory" / "_data").mkdir(parents=True)
    (d / "widgets").mkdir()
    (d / "config").mkdir()
    (d / "widgets" / "results.json").write_text('{"items": [{"title": "una bici"}]}')
    con = sqlite3.connect(str(d / "memory" / "_data" / "sandbox.db"))
    con.execute("CREATE TABLE sys_kv (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO sys_kv VALUES (?, ?)",
                ("worker_provider_cooldown", json.dumps({"z.ai": [1787614742.0, "health"]})))
    con.execute("INSERT INTO sys_kv VALUES (?, ?)",
                ("cluster_provider_cooldown", json.dumps({"z.ai": [1787614742.0, "health"]})))
    con.execute("INSERT INTO sys_kv VALUES (?, ?)", ("canvas_layout", '{"items": []}'))
    con.commit()
    con.close()
    return d


def _kv(ws) -> dict:
    con = sqlite3.connect(str(ws / "memory" / "_data" / "sandbox.db"))
    try:
        return {k: v for k, v in con.execute("SELECT key, value FROM sys_kv")}
    finally:
        con.close()


# ── the measured case ────────────────────────────────────────────────────────────────────────────────────────

def test_the_dead_tier_survives_the_wipe(ws, monkeypatch):
    """The bar the round set: the second batch must not spend its first minute rediscovering `z.ai`."""
    monkeypatch.setattr(stage, "workspace_of", lambda p: ws)
    carried = stage.wipe(object())
    assert "worker_provider_cooldown" in carried, "the cooldown has to be read BEFORE the directory is deleted"
    assert json.loads(carried["worker_provider_cooldown"])["z.ai"][0] == 1787614742.0

    # the seed rebuilds the database; the harness then puts the fact back
    (ws / "memory" / "_data").mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(ws / "memory" / "_data" / "sandbox.db"))
    con.execute("CREATE TABLE sys_kv (key TEXT PRIMARY KEY, value TEXT)")
    con.commit()
    con.close()
    stage._restore_kv(ws, carried)

    back = _kv(ws)
    assert json.loads(back["worker_provider_cooldown"])["z.ai"][0] == 1787614742.0
    assert json.loads(back["cluster_provider_cooldown"])["z.ai"][0] == 1787614742.0


def test_and_nothing_else_survives_it(ws, monkeypatch):
    """The other half, and the one that keeps the measurement honest: a fresh round is a fresh agent. The
    memory, the widget data and the config all go — only the fact about the outside world stays."""
    monkeypatch.setattr(stage, "workspace_of", lambda p: ws)
    carried = stage.wipe(object())
    assert not (ws / "memory").exists(), "the memory is what a wipe exists to remove"
    assert not (ws / "widgets").exists()
    assert not (ws / "config").exists()
    assert set(carried) <= set(stage._KEEP_KV), "nothing outside the declared list is carried over"
    assert "canvas_layout" not in carried, "the canvas is this agent's state, not the world's"


def test_a_first_boot_has_nothing_to_carry(tmp_path, monkeypatch):
    """No database yet is the NORMAL case, not an error: a lab agent that has never run must still boot."""
    d = tmp_path / "es"
    d.mkdir()
    monkeypatch.setattr(stage, "workspace_of", lambda p: d)
    assert stage.wipe(object()) == {}
    stage._restore_kv(d, {"worker_provider_cooldown": "{}"})     # must not raise with no database


def test_restoring_nothing_is_not_an_error(ws):
    """Fail-soft on the way back too: a harness that cannot restore a cooldown loses a minute per round, and
    a harness that CRASHES restoring one loses the batch."""
    stage._restore_kv(ws, {})
    assert "worker_provider_cooldown" in _kv(ws), "restoring nothing must leave what was there alone"
