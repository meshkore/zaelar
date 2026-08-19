"""The provider ORDER for every memory LLM task (2026-08-19, operator's standing rule).

**DeepSeek V4 DIRECT first, the AIMLAPI broker second, an OpenAI/Anthropic model last.** Before this the memory
router had NO chain at all: `chat_sync` resolved one endpoint, tried it, and on any failure returned None for the
caller to fail open. That was survivable while the titular WAS the broker; it stopped being survivable the day
every off-hot-path task moved to the direct endpoint, because a DeepSeek outage then meant REM synthesis and the
paraphrase channel producing nothing at all, quietly — and the write HEART falling to its lossy regex heuristic on
EVERY turn without a second provider ever being tried.

What is asserted here is the shape of the decision, not the wording of any comment: the order, who is skipped and
why, the two places a relay must be VISIBLE, and the four traps that make a plausible rung useless.
"""
from __future__ import annotations

import pytest

from nucleo import mem_processor as MP
from nucleo import memllm

_AIML = "https://api.aimlapi.com/v1"
_DS = "https://api.deepseek.com"


# ── credentials: absent ≠ "local" ─────────────────────────────────────────────────────────────────────────────
def test_a_local_endpoint_needs_no_key():
    """`key_for_endpoint` returns the sentinel `"local"` for an endpoint it has no env var for. On Ollama that is
    CORRECT (it wants no key); treating it as missing would drop the one rung a self-hoster configured."""
    assert memllm._has_credential("http://localhost:11434/v1", "local")
    assert memllm._has_credential("http://127.0.0.1:11434/v1", "")


def test_a_cloud_endpoint_resolving_to_the_sentinel_has_NO_credential():
    """Sending a request with no key buys a 401 and a slower failure, never a chance — so that rung is skipped."""
    assert not memllm._has_credential(_AIML, "local")
    assert not memllm._has_credential(_DS, "")


# ── the order, and who gets dropped ───────────────────────────────────────────────────────────────────────────
def test_the_chain_is_titular_then_broker_then_openai(monkeypatch):
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "k")
    monkeypatch.setattr(memllm, "resolve", lambda t: (_DS, "deepseek-v4-flash", "k", False))
    hosts = [u for u, _m, _k, _dt in memllm.chain("rem")]
    assert hosts[0] == _DS, "el directo es el titular, no un escalón de relevo"
    assert hosts[1:] == [_AIML, _AIML]
    models = [m for _u, m, _k, _dt in memllm.chain("rem")]
    assert models[-1] == "openai/gpt-4.1-mini", "OpenAI es el ÚLTIMO recurso, no el segundo"


def test_a_rung_the_config_already_promoted_is_not_tried_twice(monkeypatch):
    """An operator who points `rem_base_url`/`rem_model` at the broker's DeepSeek has made it the titular; keeping
    it in the fallback list would burn a retry on the endpoint that just failed."""
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "k")
    rungs = memllm.failover_rungs("rem", titular=(_AIML, "deepseek/deepseek-v4-flash"))
    assert [m for _u, m, _k, _dt in rungs] == ["openai/gpt-4.1-mini"]


def test_an_uncredentialed_fallback_is_dropped(monkeypatch):
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "local")
    assert memllm.failover_rungs("rem", titular=(_DS, "deepseek-v4-flash")) == []


def test_the_titular_SURVIVES_a_missing_credential(monkeypatch):
    """Deliberate asymmetry. Dropping the titular would silently substitute a different model for the one the
    config names — turning a visible misconfiguration into a wrong-model-answered-fine, the harder bug to notice."""
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "local")
    monkeypatch.setattr(memllm, "resolve", lambda t: (_DS, "deepseek-v4-flash", "local", False))
    chain = memllm.chain("rem")
    assert len(chain) == 1 and chain[0][1] == "deepseek-v4-flash"


# ── the two traps that make a plausible rung useless ──────────────────────────────────────────────────────────
def test_paraphrase_has_NO_deepseek_rung_on_the_broker():
    """This task only works with reasoning OFF (measured 2026-08-18: with it on the whole budget goes to
    reasoning and `content` comes back EMPTY), and the broker ACCEPTS `thinking:disabled` while ignoring it. That
    rung would answer HTTP 200 with nothing in it, and a rung that reports success while delivering silence is
    worse than no rung — it consumes the chain's last chance and looks fine in the log."""
    for url, model in memllm._FAILOVER["paraphrase"]:
        assert not (url == _AIML and "deepseek" in model), (
            "un escalón de paráfrasis en el broker devolvería 200 con content vacío"
        )


def test_the_hot_path_judges_have_NO_chain():
    """`turn_complete`/`directed` fire mid-conversation and their callers already fail open to a safe default in
    milliseconds. A second attempt through a broker measured at ~8.6s TTFT (V2-097) would hurt the operator far
    more than the default they degrade to — being slow at the right answer is the failure this repo banned a model
    over. This is a RATCHET: adding a rung here is a latency regression that no other test would catch."""
    assert "turn_complete" not in memllm._FAILOVER
    assert "directed" not in memllm._FAILOVER


# ── chat_sync: relaying, and the one case where relaying is forbidden ──────────────────────────────────────────
def _stub_attempts(monkeypatch, outcomes: dict[str, str | Exception]):
    """`outcomes` maps model → content to return, or an exception to raise."""
    seen: list[str] = []

    def fake(url, model, key, dt, **kw):
        seen.append(model)
        out = outcomes.get(model, RuntimeError("boom"))
        if isinstance(out, Exception):
            raise out
        return out

    monkeypatch.setattr(memllm, "_attempt", fake)
    return seen


def test_chat_sync_relays_past_a_dead_titular(monkeypatch):
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "k")
    monkeypatch.setattr(memllm, "resolve", lambda t: (_DS, "deepseek-v4-flash", "k", False))
    seen = _stub_attempts(monkeypatch, {"deepseek/deepseek-v4-flash": "OK"})
    assert memllm.chat_sync("rem", "s", "u") == "OK"
    assert seen[:2] == ["deepseek-v4-flash", "deepseek/deepseek-v4-flash"]


def test_a_relay_is_VISIBLE_in_the_health_state(monkeypatch):
    """Three incidents in this module were a failure that stayed in a `logger.warning`. A relay means the titular
    is DOWN, which is exactly what the ◉ exists to show."""
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "k")
    monkeypatch.setattr(memllm, "resolve", lambda t: (_DS, "deepseek-v4-flash", "k", False))
    _stub_attempts(monkeypatch, {"deepseek/deepseek-v4-flash": "OK"})
    recorded: list[tuple] = []
    from voice import health_state
    monkeypatch.setattr(health_state, "record", lambda *a, **k: recorded.append(a))
    memllm.chat_sync("rem", "s", "u")
    assert recorded and recorded[0][0] == "memory" and recorded[0][1] == "degraded"


def test_every_rung_failing_reports_an_OUTAGE_and_fails_open(monkeypatch):
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "k")
    monkeypatch.setattr(memllm, "resolve", lambda t: (_DS, "deepseek-v4-flash", "k", False))
    _stub_attempts(monkeypatch, {})
    recorded: list[tuple] = []
    from voice import health_state
    monkeypatch.setattr(health_state, "record", lambda *a, **k: recorded.append(a))
    assert memllm.chat_sync("rem", "s", "u") is None, "fail-open: el llamador decide, nunca una excepción"
    assert recorded and recorded[0][1] == "outage"


def test_a_PINNED_model_never_relays(monkeypatch):
    """The load-bearing invariant of every benchmark that pins a model — LoCoMo declares its answerer and judge,
    and a silent relay would make the declaration a LIE: the report would say it measured with one model while
    having measured with another. Failing open is the honest outcome there."""
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "k")
    monkeypatch.setattr(memllm, "resolve", lambda t: (_DS, "deepseek-v4-flash", "k", False))
    seen = _stub_attempts(monkeypatch, {"deepseek/deepseek-v4-flash": "OK"})
    out = memllm.chat_sync("rem", "s", "u", model_override="openai/gpt-4.1-mini", url_override=_AIML)
    assert out is None, "un modelo pinchado que falla devuelve None, no la respuesta de OTRO modelo"
    assert seen == ["openai/gpt-4.1-mini"], f"no debió tocar ningún otro escalón: {seen}"


# ── the CORAZÓN resolves its own titular, and only borrows the ORDER ───────────────────────────────────────────
def test_the_heart_keeps_its_own_titular_at_the_front(monkeypatch):
    """`distill`'s config keys are the historical `mem_processor_*` (with env fallbacks, synchronized across three
    deploy sites), so `memllm.resolve("distill")` does NOT know its endpoint — it would silently fall through to
    `_DEFAULTS["rem"]`. The heart must resolve its own titular and borrow only the fallback ORDER."""
    monkeypatch.setattr(MP, "_url", lambda: "http://localhost:11434/v1")
    monkeypatch.setattr(MP, "_model", lambda: "qwen2.5:7b-instruct")
    rungs = MP._rung_chain()
    assert rungs[0] == ("http://localhost:11434/v1", "qwen2.5:7b-instruct")


def test_the_heart_still_writes_when_the_fallback_catalog_explodes(monkeypatch):
    """A bad day for the fallback catalog must not become a bad day for every memory write."""
    monkeypatch.setattr(MP, "_url", lambda: _DS)
    monkeypatch.setattr(MP, "_model", lambda: "deepseek-v4-flash")
    monkeypatch.setattr(memllm, "failover_rungs", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("nope")))
    assert MP._rung_chain() == [(_DS, "deepseek-v4-flash")]


# ── an EMPTY answer is a failure, not an answer ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("content", ["", "   ", None])
def test_an_empty_answer_from_a_rung_is_treated_as_a_FAILURE(monkeypatch, content):
    """The direct DeepSeek endpoint returns `content=""` with `finish_reason=length` when reasoning eats the
    budget — no exception at all. In `chat_sync` that would hand the caller silence with a success flag; in the
    HEART it is worse, because `_parse("")` returns `[]`, and `[]` is this module's contract for «the model RAN and
    decided nothing is memorable» — so the caller would NOT fall back to the heuristic. Silence dressed as a
    decision, which is the one thing a write path must never produce."""
    import json as _json

    class _Resp:
        def read(self):
            return _json.dumps({"choices": [{"message": {"content": content}}]}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    with pytest.raises(Exception):
        memllm._attempt(_DS, "deepseek-v4-flash", "k", False, system="s", user="u",
                        max_tokens=8, temperature=0, timeout=5)
