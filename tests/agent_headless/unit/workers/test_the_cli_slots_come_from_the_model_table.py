"""The Claude Code worker's model SLOTS come from the model table, per rung (V2-831 T-25).

The worker got only `ANTHROPIC_BASE_URL`/token and `--model`, so the CLI's secondary slot — the one WebFetch reads a
page with — ran on the MAIN model. Measured 2026-10-29 on the demo's whitepaper extraction: one WebFetch took 95.9 s
on glm-5.3 and 165.6 s on deepseek-v4-pro; with the rung's declared `fast_model`, 20.2 s (glm-5-turbo) and 19.7 s
(deepseek-flash). The slots are DATA (`config/models.default.json`) passed as env when the session starts.

Disarm: drop `out.update(slot_env(t))` from `env_for_worker` → red.
"""
from __future__ import annotations

_TIER = {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic", "env": ["Z_AI_API_KEY"],
         "model": "glm-5.3", "fast_model": "glm-5-turbo"}


def test_a_session_starts_with_the_rungs_slots(monkeypatch):
    from nucleo.workers import providers as p
    monkeypatch.setattr(p, "pick", lambda: dict(_TIER))
    monkeypatch.setattr(p, "_token_for", lambda t: "tok")
    env = p.env_for_worker()
    assert env.get("ANTHROPIC_SMALL_FAST_MODEL") == "glm-5-turbo", env
    assert env.get("ANTHROPIC_DEFAULT_SONNET_MODEL") == env.get("ANTHROPIC_DEFAULT_OPUS_MODEL") == "glm-5.3", env


def test_both_worker_rungs_declare_their_fast_slot():
    from config import models
    rungs = models.chain_for("brain_worker")
    assert len(rungs) == 2 and all(r.get("fast_model") and r["fast_model"] != r["model"] for r in rungs), rungs


def test_a_hand_ordered_tier_inherits_the_measured_fast_slot(monkeypatch):
    from nucleo.workers import providers as p
    monkeypatch.setattr(p, "KNOWN", [dict(_TIER)])
    assert p._with_measured_traits({"name": "mine", "base_url": _TIER["base_url"]})["fast_model"] == "glm-5-turbo"
