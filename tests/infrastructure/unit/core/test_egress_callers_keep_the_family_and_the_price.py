"""Every caller of `llm_egress.route()` keeps what the route hands back (V2-811 T-00).

`route()` returns `(base, key, extra)`. Two things a caller can silently lose:

- **the family** — `extra` carries the provider family header. A caller that drops it sends every rung to the
  egress default family, so a stand-in on another provider goes to the wrong upstream. `memllm`, `susurro` and
  `rerank` did exactly that (`_extra`, never read).
- **the price** — the meter prices a call by its PROVIDER's URL. Metering with the routed (egress) base finds no
  rate row and bills the catch-all. `memllm`, `susurro` and `rerank` did that too.

And one caller that never metered at all: `FastClient.complete()` (and its Z.AI twin), used by ~20 call sites.
"""
from __future__ import annotations

import ast
import asyncio
import pathlib
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
_SKIP = {"tests", ".venv", "node_modules", "widgets/_user"}
_METERS = {"meter_openai_response", "report_llm_usage"}


def _sources():
    for p in ROOT.rglob("*.py"):
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(".") or "/." in rel or any(rel == s or rel.startswith(s + "/") for s in _SKIP):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if "llm_egress.route(" in text:
            yield rel, ast.parse(text)


def _route_targets(fn):
    """(base_name, extra_name, lineno) for each `a, b, c = llm_egress.route(...)` in this function."""
    for node in ast.walk(fn):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "route"
                and isinstance(node.targets[0], ast.Tuple) and len(node.targets[0].elts) == 3):
            names = [getattr(e, "id", None) for e in node.targets[0].elts]
            yield names[0], names[2], node.lineno


def _offences(rel, tree):
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for base, extra, line in _route_targets(fn):
            reads = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
            if extra not in reads:
                out.append(f"{rel}:{line} drops the family headers (`{extra}` is never read)")
            for call in ast.walk(fn):
                if not (isinstance(call, ast.Call) and getattr(call.func, "attr", getattr(call.func, "id", ""))
                        in _METERS):
                    continue
                for kw in call.keywords:
                    if kw.arg == "base_url" and base in {n.id for n in ast.walk(kw.value) if isinstance(n, ast.Name)}:
                        out.append(f"{rel}:{call.lineno} meters by the egress URL `{base}`, not the provider's")
    return out


def test_no_caller_of_route_drops_the_family_or_meters_by_the_egress_url():
    found, offences = 0, []
    for rel, tree in _sources():
        found += 1
        offences += _offences(rel, tree)
    assert found >= 8, f"only {found} callers found — the scan is not looking where the code is"
    assert not offences, "\n".join(offences)


def test_the_guard_bites_on_the_shape_it_forbids():
    bad = ast.parse(
        "def f(url, key):\n"
        "    url, key, _extra = llm_egress.route(url, key)\n"
        "    data = post(url, key)\n"
        "    energy_meter.meter_openai_response(data, base_url=url, model='m')\n")
    got = _offences("x.py", bad)
    assert any("drops the family" in o for o in got) and any("egress URL" in o for o in got), got


@pytest.fixture
def mediated(monkeypatch):
    from nucleo import energy_lease, llm_egress
    monkeypatch.setattr(llm_egress, "mediated", lambda: True)
    monkeypatch.setattr(energy_lease, "admit", lambda *_a, **_k: None)
    monkeypatch.setenv("ZAELAR_GATEWAY_URL", "https://egress.example")
    monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", "tok")


def test_memllm_sends_the_family_and_prices_by_the_provider(mediated, monkeypatch):
    from nucleo import energy_meter
    from nucleo.memory_agent.processor import llm
    sent, metered = {}, {}
    monkeypatch.setattr(llm, "_post_json", lambda url, payload, *, headers, timeout: (
        sent.update(url=url, headers=headers) or {"choices": [{"message": {"content": "ok"}}], "usage": {}}))
    monkeypatch.setattr(energy_meter, "meter_openai_response", lambda p, *, base_url, model=None: metered.update(
        base_url=base_url))
    out = llm._attempt("https://api.openai.com/v1", "gpt-4.1-mini", "k", False,
                          system="s", user="u", max_tokens=10, temperature=0, timeout=5)
    assert out == "ok"
    assert sent["url"].startswith("https://egress.example/v1")
    assert sent["headers"].get("X-Zaelar-Provider") == "openai", sent["headers"]
    assert metered["base_url"] == "https://api.openai.com/v1"


def test_fast_client_complete_meters_by_the_provider(monkeypatch):
    from nucleo import energy_lease, energy_meter
    from nucleo.flash import fast_client
    monkeypatch.setattr(energy_lease, "admit", lambda *_a, **_k: None)
    metered = {}
    monkeypatch.setattr(energy_meter, "meter_openai_response", lambda p, *, base_url, model=None: metered.update(
        base_url=base_url, model=model, usage=getattr(p, "usage", None)))
    resp = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="hi", tool_calls=None))],
                           usage={"prompt_tokens": 3, "completion_tokens": 1})

    async def create(**_kw):
        return resp

    cli = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(fast_client.FastClient, "_client_for", lambda self, spec: cli)
    spec = SimpleNamespace(model="deepseek-flash", is_local=lambda: False, _is_zai=lambda: False,
                           reasoning_effort=lambda: None, takes_thinking_field=lambda: False,
                           resolved_base_url=lambda: "https://api.deepseek.com")
    out = asyncio.run(fast_client.FastClient().complete([{"role": "user", "content": "x"}], spec=spec))
    assert out == "hi"
    assert metered == {"base_url": "https://api.deepseek.com", "model": "deepseek-flash",
                       "usage": {"prompt_tokens": 3, "completion_tokens": 1}}
