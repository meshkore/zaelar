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
def test_the_chain_is_titular_then_broker(monkeypatch):
    """El ORDEN es lo que se fija aquí: primero el endpoint directo (titular) y detrás el broker.

    Se llamaba `..._then_openai` y afirmaba `models[-1] == "openai/gpt-4.1-mini"`. El 2026-08-21 la norma del
    operador —ningún modelo de OpenAI puede ser lo que CORRE sin que nadie lo elija; en el catálogo sí— sacó ese
    escalón, así que la aserción pasó a fijar una política derogada. Se cambia por lo que la norma sí garantiza y
    por lo que este fichero existe para vigilar: que el último recurso NO sea de OpenAI. Fijar el nombre exacto
    del último modelo volvería a atar el test a una elección de catálogo que puede cambiar mañana."""
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "k")
    monkeypatch.setattr(memllm, "resolve", lambda t: (_DS, "deepseek-v4-flash", "k", False))
    hosts = [u for u, _m, _k, _dt in memllm.chain("rem")]
    assert hosts[0] == _DS, "el directo es el titular, no un escalón de relevo"
    assert hosts[1:] == [_AIML, _AIML]
    models = [m for _u, m, _k, _dt in memllm.chain("rem")]
    assert len(models) == 3, models
    assert not any(m.lower().startswith("openai/") for m in models), \
        f"un escalón de relevo corre SIN que nadie lo elija: {models}"


def test_a_rung_the_config_already_promoted_is_not_tried_twice(monkeypatch):
    """An operator who points `rem_base_url`/`rem_model` at the broker's DeepSeek has made it the titular; keeping
    it in the fallback list would burn a retry on the endpoint that just failed.

    Asserts the ABSENCE of that one pair rather than the exact remaining list: pinning the full list makes this test
    fail every time a rung is added for an unrelated reason (it did, when DeepSeek direct became the first
    fallback), and a test that has to be edited to stay green stops being read."""
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "k")
    promoted = (_AIML, "deepseek/deepseek-v4-flash")
    rungs = memllm.failover_rungs("rem", titular=promoted)
    assert promoted not in [(u, m) for u, m, _k, _dt in rungs]
    assert rungs, "quitar el titular de la lista no puede dejar la cadena sin escalones"


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
    `_DEFAULTS["rem"]`. The heart must resolve its own titular and borrow only the fallback ORDER.

    Both hidden dependencies are PINNED, and that is the point of this note: as first written this test passed for
    the wrong reasons and failed only in the FULL suite. It asserted a LOCAL titular stays in front while (a)
    `_endpoint_key` was the real resolver, so whether the fallbacks existed at all depended on another test having
    imported `server.common` and loaded the credential store, and (b) the local gate was the real one, so the
    answer depended on whether THIS machine had `qwen2.5:7b-instruct` pulled. Neither is what this test is about."""
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "k")
    monkeypatch.setattr(memllm, "local_titular_ready", lambda *a: True)
    monkeypatch.setattr(MP, "_url", lambda: "http://localhost:11434/v1")
    monkeypatch.setattr(MP, "_model", lambda: "qwen2.5:7b-instruct")
    rungs = MP._rung_chain()
    assert rungs[0] == ("http://localhost:11434/v1", "qwen2.5:7b-instruct")
    assert rungs[1] == (_DS, "deepseek-v4-flash"), "y el failover del operador va justo detrás"


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


# ── the operator's rule, 2026-08-19: Ollama titular WHEN AVAILABLE, DeepSeek V4 Flash direct as the failover ────
def _tags(names: list[str]):
    """A fake `/api/tags` response, plus a counter so the TTL cache can be observed."""
    import json as _json
    calls: list[str] = []

    class _R:
        def read(self):
            return _json.dumps({"models": [{"name": n} for n in names]}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, *a, **k):
        calls.append(getattr(req, "full_url", str(req)))
        return _R()

    return fake, calls


def test_deepseek_direct_is_the_FIRST_fallback_of_every_memory_task():
    """The rule names DeepSeek V4 Flash **through its provider** as the failover. Before this it was only ever the
    TITULAR, so pointing the titular at a local Ollama silently left the direct endpoint out of the chain and the
    first fallback became the broker — the opposite of the stated order."""
    for task in ("distill", "rem", "paraphrase"):
        first = memllm._FAILOVER[task][0]
        assert first == (_DS, "deepseek-v4-flash"), f"{task} no empieza por el directo: {first}"


def test_a_local_endpoint_is_recognised_and_a_cloud_one_is_not():
    for url in ("http://localhost:11434/v1", "http://127.0.0.1:11434", "http://0.0.0.0:11434/v1"):
        assert memllm.is_local_endpoint(url)
    for url in (_DS, _AIML, "https://api.openai.com/v1"):
        assert not memllm.is_local_endpoint(url)


def test_ready_asks_the_ROOT_for_tags_not_the_openai_path(monkeypatch):
    """`/api/tags` hangs off the root; the chat calls use the OpenAI-compatible `/v1`. Asking `/v1/api/tags` 404s,
    which fail-closed would read as «model absent» — the local titular would never be used on a healthy machine."""
    memllm.reset_local_probe()
    fake, calls = _tags(["qwen2.5:7b-instruct"])
    monkeypatch.setattr("urllib.request.urlopen", fake)
    assert memllm.local_titular_ready("http://localhost:11434/v1", "qwen2.5:7b-instruct")
    assert calls == ["http://localhost:11434/api/tags"]


def test_the_gate_asks_whether_the_MODEL_is_there_not_just_the_server(monkeypatch):
    """Ollama answers `/api/tags` perfectly while serving a model nobody pulled. A server-only probe would hand the
    write path a rung that 404s on every call — indistinguishable from the profile bug this shipped alongside."""
    memllm.reset_local_probe()
    fake, _ = _tags(["embeddinggemma:latest"])
    monkeypatch.setattr("urllib.request.urlopen", fake)
    assert not memllm.local_titular_ready("http://localhost:11434/v1", "qwen2.5:7b-instruct")


def test_a_tagless_config_matches_latest_but_two_real_tags_never_match(monkeypatch):
    """`embeddinggemma` and `embeddinggemma:latest` are the same model; `qwen2.5:7b` and `qwen2.5:14b` are NOT, and
    treating them as equal would silently run a different model than the config names."""
    memllm.reset_local_probe()
    fake, _ = _tags(["embeddinggemma:latest", "qwen2.5:14b-instruct"])
    monkeypatch.setattr("urllib.request.urlopen", fake)
    assert memllm.local_titular_ready("http://localhost:11434", "embeddinggemma")
    assert not memllm.local_titular_ready("http://localhost:11434", "qwen2.5:7b-instruct")


def test_the_probe_FAILS_CLOSED_when_the_server_does_not_answer(monkeypatch):
    """Deliberately the opposite posture to the rest of this module. A wrong «yes» spends the write on a rung that
    cannot answer; a wrong «no» just uses the cloud rung that was next anyway. The costs are not symmetric."""
    memllm.reset_local_probe()

    def boom(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert not memllm.local_titular_ready("http://localhost:11434/v1", "qwen2.5:7b-instruct")


def test_the_verdict_is_cached_but_NEVER_latched(monkeypatch):
    """`memory/embeddings._resolve_backend` cached one probe for a whole process and a single boot hiccup demoted
    the vector space for 300s — the defect V2-103 traced 51.6% of vector-less rows to. Non-stop means recovery
    must need no restart, so the cache has a TTL and `reset_local_probe` exists."""
    memllm.reset_local_probe()
    fake, calls = _tags(["qwen2.5:7b-instruct"])
    monkeypatch.setattr("urllib.request.urlopen", fake)
    for _ in range(4):
        memllm.local_titular_ready("http://localhost:11434/v1", "qwen2.5:7b-instruct")
    assert len(calls) == 1, f"la sonda se repitió {len(calls)} veces dentro del TTL"
    memllm.reset_local_probe()
    memllm.local_titular_ready("http://localhost:11434/v1", "qwen2.5:7b-instruct")
    assert len(calls) == 2, "tras invalidar la caché debe volver a sondear"


def test_a_DEAD_local_titular_is_stepped_over_and_the_chain_starts_at_deepseek(monkeypatch):
    memllm.reset_local_probe()
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "k")
    monkeypatch.setattr(memllm, "resolve", lambda t: ("http://localhost:11434/v1", "qwen2.5:7b-instruct", "local", False))
    monkeypatch.setattr(memllm, "local_titular_ready", lambda *a: False)
    chain = memllm.chain("rem")
    assert chain[0][0] == _DS and chain[0][1] == "deepseek-v4-flash", chain


def test_a_LIVE_local_titular_stays_in_front(monkeypatch):
    memllm.reset_local_probe()
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "k")
    monkeypatch.setattr(memllm, "resolve", lambda t: ("http://localhost:11434/v1", "qwen2.5:7b-instruct", "local", False))
    monkeypatch.setattr(memllm, "local_titular_ready", lambda *a: True)
    chain = memllm.chain("rem")
    assert chain[0][1] == "qwen2.5:7b-instruct" and chain[1][0] == _DS, chain


def test_the_chain_is_NEVER_empty(monkeypatch):
    """Local titular down AND every fallback uncredentialed: returning [] would make `chat_sync` report «0 rungs
    exhausted», a true statement that hides the real cause. Keeping the titular lets the actual error surface."""
    memllm.reset_local_probe()
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "local")
    monkeypatch.setattr(memllm, "resolve", lambda t: ("http://localhost:11434/v1", "qwen2.5:7b-instruct", "local", False))
    monkeypatch.setattr(memllm, "local_titular_ready", lambda *a: False)
    assert len(memllm.chain("rem")) == 1


def test_the_HEART_steps_over_a_dead_local_titular_only_if_there_is_somewhere_to_go(monkeypatch):
    monkeypatch.setattr(MP, "_url", lambda: "http://localhost:11434/v1")
    monkeypatch.setattr(MP, "_model", lambda: "qwen2.5:7b-instruct")
    monkeypatch.setattr(memllm, "local_titular_ready", lambda *a: False)
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "k")
    assert MP._rung_chain()[0] == (_DS, "deepseek-v4-flash")
    # No credentialed fallback anywhere → the local titular is all there is, and it must still be attempted.
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "local")
    assert MP._rung_chain() == [("http://localhost:11434/v1", "qwen2.5:7b-instruct")]


# ── a model named WITHOUT its endpoint (measured 2026-08-20 in every sandboxed use_cases round) ────────────────
# `MEM_PROCESSOR_MODEL=qwen2.5:3b` sat in the operator's env file with no matching `MEM_PROCESSOR_URL`. The env
# fallback applies whenever the store has no value, and a fresh workspace (every sandbox, every new self-host) has
# no store — so a LOCAL Ollama tag became the titular of a CLOUD endpoint and every distillation paid a 404 before
# relaying. What is asserted is the SHAPE rule, not the env var: the same pair is equally impossible whichever
# layer produced each half.
@pytest.mark.parametrize("url,model,incoherent", [
    (_AIML, "qwen2.5:3b", True),                        # the measured case
    (_DS, "qwen3.6:27b-mlx", True),                     # any Ollama tag at any cloud endpoint
    ("http://localhost:11434/v1", "qwen2.5:3b", False),  # the pair the tag is FOR
    ("http://127.0.0.1:11434", "qwen3.6:27b-mlx", False),
    (_AIML, "deepseek/deepseek-v4-flash", False),        # broker form: vendor/model
    (_AIML, "openai/gpt-4.1-mini", False),
    (_DS, "deepseek-v4-flash", False),                   # direct form: bare name
    (_AIML, "", False),                                  # nothing named ≠ named wrong
])
def test_an_ollama_tag_at_a_cloud_endpoint_is_a_pair_that_cannot_work(url, model, incoherent):
    assert memllm.pair_incoherent(url, model) is incoherent


def test_the_HEART_skips_the_impossible_pair_instead_of_paying_the_404(monkeypatch):
    """This is the fix for the ~8-10 `HTTP 404 Model not found` per round the tester was seeing. Note it is NOT
    the local-titular gate: that one probes a REACHABLE endpoint to see whether it serves the model, and would
    happily let this pair through because `api.aimlapi.com` is not local."""
    memllm.reset_local_probe()
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "k")
    monkeypatch.setattr(MP, "_url", lambda: _AIML)
    monkeypatch.setattr(MP, "_model", lambda: "qwen2.5:3b")
    rungs = MP._rung_chain()
    assert (_AIML, "qwen2.5:3b") not in rungs, "un par imposible no se intenta, se salta"
    assert rungs[0] == (_DS, "deepseek-v4-flash"), "y la escritura entra por el failover del operador"


def test_the_impossible_pair_is_KEPT_when_there_is_nowhere_to_relay(monkeypatch):
    """Same asymmetry as the local gate: skipping is only right when there is somewhere to skip TO. With no
    credentialed fallback, keeping it is what makes the real 404 reach the log and the ◉ instead of «0 escalones»."""
    memllm.reset_local_probe()
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "local")   # no cloud credential anywhere
    monkeypatch.setattr(MP, "_url", lambda: _AIML)
    monkeypatch.setattr(MP, "_model", lambda: "qwen2.5:3b")
    assert MP._rung_chain() == [(_AIML, "qwen2.5:3b")]


def test_a_catalog_task_skips_it_too(monkeypatch):
    """The trap is in the config layer, not in the write path, so REM/paraphrase can fall into it identically."""
    memllm.reset_local_probe()
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "k")
    monkeypatch.setattr(memllm, "resolve", lambda t: (_AIML, "qwen2.5:3b", "k", False))
    assert (_AIML, "qwen2.5:3b") not in [(u, m) for u, m, _k, _dt in memllm.chain("rem")]


def test_the_incoherent_pair_is_reported_ONCE_not_once_per_write(monkeypatch, caplog):
    """A config error repeats on every write. Ten identical warnings per round is a warning nobody reads — and the
    ◉ is where a degradation belongs anyway (the lesson this module already paid for three times)."""
    memllm.reset_local_probe()
    monkeypatch.setattr(memllm, "_endpoint_key", lambda url: "k")
    monkeypatch.setattr(MP, "_url", lambda: _AIML)
    monkeypatch.setattr(MP, "_model", lambda: "qwen2.5:3b")
    said = []
    monkeypatch.setattr(memllm.logger, "warning", lambda msg, *a, **k: said.append(str(msg)))
    for _ in range(5):
        MP._rung_chain()
    assert len(said) == 1, f"debería decirse una vez, se dijo {len(said)}"
    assert "qwen2.5:3b" in said[0] and _AIML in said[0], "y tiene que traer el PAR, no solo la queja"
