"""The retired LLM broker stays retired: no tracked file names it, no default route reaches it (V2-827).

Operator, 2026-10-27 and again 2026-11-07: the broker is not used — not as titular, not as relay, not in tests, not
in docs. It had been out of every live config for weeks while the code, the tests and the docs still described it as
a fallback, so a reader (human or agent) was told a relay existed that the operator had ruled out. Every LLM route
now calls its provider's own DIRECT endpoint.

Two halves, because either can regress alone:
  · TEXT — no git-tracked file mentions the broker (a doc or a comment is how the wrong belief travels);
  · ROUTES — no default the engine resolves on its own points at the broker's host (the `ModelSpec` default, the
    memory distiller's fallback, every memory-task rung, the key and egress tables, the shipped model table).

The forbidden word is assembled from pieces so this file does not match itself.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
_WORD = "aiml" + "api"


def _tracked() -> list[str]:
    r = subprocess.run(["git", "ls-files", "-z"], cwd=ENGINE, capture_output=True, text=True)
    return [p for p in r.stdout.split("\0") if p]


def _mentions() -> list[str]:
    hits = []
    for rel in _tracked():
        p = ENGINE / rel
        try:
            if not p.is_file() or p.stat().st_size > 2_000_000:
                continue
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        n = text.lower().count(_WORD)
        if n:
            hits.append(f"{rel}: {n}")
    return hits


def test_no_tracked_file_names_the_retired_broker():
    hits = _mentions()
    assert not hits, f"the retired broker is named again — every LLM route is a provider's DIRECT endpoint: {hits[:20]}"


def _bad(url: str | None) -> bool:
    return _WORD in (url or "").lower()


def test_no_default_route_reaches_the_broker(monkeypatch):
    for var in ("FAST_API_KEY", "MEM_PROCESSOR_URL", "ZAELAR_LOCAL_LLM_URL"):
        monkeypatch.delenv(var, raising=False)

    from nucleo.llm.model_spec import ModelSpec, _provider_label
    spec = ModelSpec(model="x")
    assert spec.resolved_base_url() == "https://api.deepseek.com", spec.resolved_base_url()
    assert spec.provider == "deepseek" and _provider_label("", None) == "deepseek"

    from nucleo.memory_agent.processor import distill_config, llm_routes
    assert not _bad(distill_config._FALLBACK_URL), distill_config._FALLBACK_URL
    for task, (url, _model, _dt) in llm_routes._DEFAULTS.items():
        assert not _bad(url), f"{task} titular: {url}"
    for task, rungs in llm_routes._FAILOVER.items():
        for url, _model in rungs:
            assert not _bad(url), f"{task} rung: {url}"

    from nucleo.energy import egress, keys
    assert not [n for n, env in keys._ENDPOINTS if _bad(n) or _bad(env)]
    assert not [h for h, name in egress._PROVIDER_BY_HOST if _bad(h) or _bad(name)]

    from server.config_catalog import _PROVIDER_CATALOG
    for piece, conf in _PROVIDER_CATALOG.items():
        for prov in conf.get("providers", []):
            assert not (_bad(prov.get("id")) or _bad(prov.get("base_url"))), f"{piece}: {prov.get('id')}"

    table = json.loads((ENGINE / "config" / "models.default.json").read_text(encoding="utf-8"))
    for name, svc in table["services"].items():
        for rung in ("titular", "failover"):
            r = svc.get(rung) or {}
            assert not (_bad(r.get("provider")) or _bad(r.get("base_url"))), f"{name}.{rung}: {r}"
