"""nucleo/memllm.py — Internal model ROUTER for the MEMORY MODULE (V2-056, 2026-07-20).

The memory module has several LLM tasks with distinct profiles, each selectable BY CONFIG and with credentials
resolved BY ENDPOINT (lesson from the 2026-07-19 audit: a loose env key sent to the wrong endpoint took down the
HEART silently for 2 days). One seam for all of them:

  - `distill`  → the writing HEART (implemented by `nucleo/mem_processor.py` with its own queue/semantics;
                 this router does NOT replace it — it is documented here as a catalogue task).
  - `rem`      → deep-sleep SYNTHESIS (`memory/rem.py` receives it INJECTED — memory does not import
                 nucleo; the loop wires `synthesize_concept_groups` as a hook, `summarize_fn` pattern).
  - (future)   → `context_router` (dossier retrieval), pill-quality judges…

Everything runs OFF the hot path (never during the voice turn). Each task reads
`config §memory.<task>_model/_base_url/_api_key`, falling back to defaults; an empty key is resolved by endpoint
(OpenAI/AIMLAPI/xAI/Groq → corresponding env). Benchmarks supporting the defaults:
`zaelar-model-benchmarks.md §12` (write-completeness + REM synthesis).
"""
from __future__ import annotations

import json
import os
import urllib.request

from loguru import logger

# Last-resort fallback (if `config §memory` cannot be read). Must match the default in
# `config/v2.py §memory` — pointing to OpenAI here meant always failing in the cloud: there is no OPENAI_API_KEY
# among the secrets injected by the provisioner (2026-08-09, same fix as in mem_processor).
# Each entry: (base_url, model, disable_thinking). `disable_thinking` is a PER-TASK decision, not inferred
# from the endpoint — see the routing policy note below `_ENDPOINTS` in `nucleo/provider_keys.py`. Getting this
# wrong is a real correctness bug, not just a style choice: §12.3/§12.4 of `zaelar-model-benchmarks.md` crowned
# `deepseek-v4-flash` for `rem`/`distill`-shaped tasks while it could ONLY reason (AIMLAPI ignored the disable
# field) — moving a task to the direct endpoint without ALSO deciding this flag silently swaps in an unmeasured
# reasoning-off variant of the model. `turn_complete`/`directed` are genuinely latency-critical (hot path,
# per-turn) and were benchmarked disabled from the start — those two disable it. Every off-hot-path task keeps
# reasoning ON by default, matching the benchmark that picked the model, even after moving off AIMLAPI.
_DEFAULTS = {
    "rem": ("https://api.deepseek.com", "deepseek-v4-flash", False),
    # i18n (V2-089): translation of the UI into a new language during INITIALIZATION (i18n/init). Off-hot-path,
    # quality matters (non-Latin scripts: Arabic, Chinese, Japanese…) → strong model. Override in config §memory.
    #
    # 2026-08-09 — it pointed to OpenAI DIRECT (gpt-4o) and was the last remnant of that account in memory: in
    # the cloud has no OPENAI_API_KEY, so generating a new language bundle would have failed silently (same
    # the same pattern that took down the HEART in July and REM until yesterday). Operator rule: EVERYTHING through
    # the AIMLAPI broker, one account to manage. Probe the REAL batch size (`_BATCH=50`, ja/ar/zh, 15 keys with
    # placeholder) before choosing a replacement:
    # ⚠️ 2026-08-19 — OPERATOR RULE: DeepSeek V4 Pro DIRECT and nothing else. This task was the LAST one
    # still choosing an Anthropic model, with a 2026-08-09 measurement behind it (§12.5) saying that
    # `deepseek-v4-flash` was accurate but REASONED for 6-8× the tokens it delivered, 50-60 s per batch. That finding
    # remains true and remains documented, but it concerned **v4-FLASH through the BROKER**, precisely the
    # combination where `thinking:disabled` is accepted and ignored (V2-097). The NATIVE endpoint OBEYS the parameter,
    # so the reason DeepSeek was rejected here disappears with the endpoint change.
    # If it reasons too much again, measure it and document it — do not return to another provider out of habit.
    # It remains the system's least price-sensitive task: it is paid for ONCE per language (514 keys ≈ 11
    # batches), so what matters is that the batch is not lost, not what it costs.
    "i18n": ("https://api.deepseek.com", "deepseek-v4-pro", True),
    # turn_complete (V2-102): the voice pipeline's turn-completeness judge (nucleo/flash/segmenter.py::judge).
    # Fires per AMBIGUOUS fragment, mid-conversation — genuinely latency-critical (hot path, user-visible),
    # benchmarked reasoning-OFF from the start. DeepSeek DIRECT: per zaelar-model-benchmarks.md §11/CLAUDE.md's
    # V2-097 finding, the AIMLAPI broker doesn't honor `thinking:disabled` for this model (~8.6s TTFT) while the
    # direct endpoint does (~1s) — same model, same price, just obedient. `DEEPSEEK_API_KEY` resolves via
    # `nucleo/provider_keys.py`.
    "turn_complete": ("https://api.deepseek.com", "deepseek-v4-flash", True),
    # directed (2026-08-16): voice/attention.py's content-based gate for "always" (open-mic) mode — with no
    # wake-word, the only signal for "is this ambient noise or aimed at me" is the NATURE of the utterance
    # (operator ask, live incident: 5-7 background-noise fragments each ran a full turn, one even completed a
    # real ~3s web_search, before finally getting discarded as superseded — real cost for zero value). Same
    # profile as `turn_complete`: fires on every non-wake-word turn in the hot path, needs the DIRECT DeepSeek
    # endpoint's ~1s TTFT and the same reasoning-OFF choice.
    "directed": ("https://api.deepseek.com", "deepseek-v4-flash", True),
    # errand_scope (2026-08-24): with an errand already live, is a NEW escalation a SEPARATE errand or is it
    # ABOUT the live one? `dispatch.find_duplicate` answers the direct half (a reformulation of the same
    # request) and structurally cannot answer this one: «¿alguna novedad ya?» shares no content word with
    # «busca una guitarra acústica», so containment reads 0 and it spawns a second worker with its own sheet.
    # Measured that day — ONE guitar search produced THREE errands and four cards on the operator's screen.
    # OFF the voice turn (the dispatcher already answered) but still in front of a worker the operator is
    # waiting on, so the same reasoning-OFF direct endpoint as its two neighbours above.
    "errand_scope": ("https://api.deepseek.com", "deepseek-v4-flash", True),
    # paraphrase (V2-031 T2, 2026-08-17): 1-2 reformulations of a durable pill, generated off-hot-path
    # from REM (never during the turn) to index extra vectors that close the vocab gap during retrieval. Same
    # profile as `rem`: no latency pressure → DIRECT per the routing policy.
    #
    # ⚠️ reasoning-OFF, and this one IS measured (2026-08-18). It shipped `False` on the stated principle that
    # "no benchmark measures this task with thinking off, so it isn't assumed" — conservative, and it made the
    # whole third retrieval channel DEAD ON ARRIVAL. Measured against the real endpoint with the real
    # `_PARAPHRASE_SYSTEM`: reasoning consumed the ENTIRE budget and the answer came back empty, at BOTH
    # budgets tried — `max_tokens=300` → `finish_reason=length`, `reasoning_tokens=300`, `content=''`; and
    # `max_tokens=1200` → `reasoning_tokens=1200`, `content=''`. Raising the budget does not help: the model
    # just reasons more. With `thinking:{"type":"disabled"}` the SAME call returns the JSON array correctly on
    # the first try, well inside 300 tokens. So the flag is no longer an assumption in either direction, and
    # the cost of the cautious default was a silent 0 rows in `vec_paraphrases` — see the fail-open note in
    # `generate_paraphrases`, which is why nothing ever reported it.
    #
    # Generalization worth keeping: this task asks for STRICT JSON under a long instruction, which is the shape
    # that makes a reasoning model burn its budget before emitting a token. The two hot-path judges
    # (`turn_complete`/`directed`) were disabled for LATENCY; this one is disabled for it to work at all.
    "paraphrase": ("https://api.deepseek.com", "deepseek-v4-flash", True),
}

# ── FAILOVER: the operator's provider ORDER, as data (2026-08-19) ─────────────────────────────────────────────
# Standing rule: **DeepSeek V4 DIRECT first, the AIMLAPI broker second, an OpenAI/Anthropic model last.** Until
# today this router had NO chain at all — `chat_sync` resolved ONE endpoint, tried it, and on any failure returned
# None for the caller to fail open. That was survivable while the titular WAS the broker; it stopped being
# survivable the day every off-hot-path task moved to the direct endpoint, because a DeepSeek outage then meant
# REM synthesis and the paraphrase channel producing nothing at all, quietly. The rule describes three rungs and
# the code had one.
#
# Rungs here come AFTER the titular `resolve()` returns (config > `_DEFAULTS`), and a rung is SKIPPED when its
# credential is absent: a request with no key buys a 401 and a slower failure, never a chance.
#
# ⚠️ Only OFF-HOT-PATH tasks get a chain. `turn_complete`/`directed` fire mid-conversation and their callers
# already fail open to a safe default in milliseconds; a second attempt through a broker measured at ~8.6 s TTFT
# (V2-097) would hurt the operator far more than the default they degrade to. Being slow at the right answer is
# the failure this repo banned a model over.
_AIML = "https://api.aimlapi.com/v1"
# DeepSeek V4 Flash on its OWN endpoint. It is BOTH the checked-in titular of most memory tasks AND the first
# fallback rung of all of them, which is not a contradiction: `failover_rungs` skips a rung the config already
# promoted to titular, so listing it here costs nothing in the usual setup and is what keeps the operator's rule
# («DeepSeek V4 Flash through its provider as the failover», 2026-08-19) true when the titular is something else —
# a LOCAL Ollama, say. Before this it was only ever the titular, so pointing the titular at Ollama silently left
# the direct endpoint out of the chain entirely and the first fallback became the broker.
_DS = "https://api.deepseek.com"

_FAILOVER: dict[str, tuple[tuple[str, str], ...]] = {
    # rem — §12.2 measured `gpt-4.1-mini` at 100% on THIS task. That result stands and is why the model is still
    # OFFERED in the catalogue; what it stopped being (2026-08-21) is a rung that RUNS without anyone choosing it,
    # per the operator's standing no-OpenAI norm — the same norm already written at the i18n rung below. The seat
    # goes to the model `distill` already trusts for its own third rung, so this is not a new bet.
    "rem": ((_DS, "deepseek-v4-flash"), (_AIML, "deepseek/deepseek-v4-flash"), (_AIML, "google/gemini-2.5-flash")),
    # distill — the WRITE HEART. `nucleo/mem_processor.py` makes the call AND resolves its own TITULAR (its config
    # keys are the historical `mem_processor_*`, with env fallbacks, and that name is synchronized across three
    # deploy sites — `config/v2.py`, `fly.accounts.toml`, the cloud provisioner). What lives HERE is only its
    # ORDER of FALLBACKS, so there is exactly one list of them; it reads them via `failover_rungs`, not `chain`.
    # The rungs are the ones §12.3 already named after sweeping 21 candidates × 34 cases. ⛔ NOT `gpt-4o-mini`:
    # cheaper and VETOED (puts an allergy stated in English into `slot=operator.diet`, which a later diet change
    # would erase).
    # 2026-08-21: the fourth rung (`openai/gpt-4.1-mini`) is gone — no-OpenAI norm. Three rungs remain, two of
    # them from the §12.3 sweep, so nothing here is running on an unmeasured model.
    "distill": ((_DS, "deepseek-v4-flash"), (_AIML, "deepseek/deepseek-v4-flash"),
                (_AIML, "google/gemini-2.5-flash")),
    # paraphrase — NO DeepSeek rung on the broker, deliberately. This task only works with reasoning OFF (measured
    # 2026-08-18: with it on the entire budget goes to reasoning and `content` comes back EMPTY at every budget
    # tried) and the broker ACCEPTS `thinking:disabled` while ignoring it. That rung would answer 200 with nothing
    # in it, and a rung that reports success while delivering silence is worse than no rung. Non-reasoners only.
    # ⚠️ DeepSeek DIRECT is the FIRST rung here and the broker's DeepSeek is absent, which is the opposite of the
    # other tasks — because this one needs reasoning OFF and only the direct endpoint obeys the flag (see below).
    # 2026-08-21 — this one PAYS for the no-OpenAI norm and it is worth stating plainly: `openai/gpt-4.1-mini`
    # was the ONLY broker rung that satisfied the constraint above (reasoning genuinely off), so removing it
    # leaves paraphrase with a single rung and no failover. The alternative was worse: any reasoning model on the
    # broker answers 200 with EMPTY content here, and a rung that reports success while delivering silence is not
    # a fallback. Tolerable because this task is OFFLINE — it runs inside the REM cycle (`memory/rem.py`), so a
    # lost run costs paraphrase coverage until the next cycle, never a turn the operator is waiting on.
    "paraphrase": ((_DS, "deepseek-v4-flash"),),
    # i18n — titular DeepSeek DIRECT like everything else, so its rung is the SAME model on the broker. One is
    # enough to stop a lost batch from meaning 50 English strings in the UI. It used to be `openai/gpt-4.1`, and
    # that is out on two counts: the operator's standing norm (no OpenAI models) and the fact that it was never
    # measured for placeholder fidelity on non-Latin scripts, which is the whole point of §12.5. ⚠️ On the broker
    # `thinking:disabled` is accepted and IGNORED (V2-097), so this rung may reason a lot and be slow — tolerable
    # here, where the task is paid ONCE per language and a lost batch is the only real failure.
    "i18n": ((_AIML, "deepseek/deepseek-v4-pro"),),
}


def _has_credential(url: str, key: str) -> bool:
    """A local endpoint legitimately needs no key (`key_for_endpoint`'s `"local"` sentinel); a cloud one that
    resolves to it has a MISSING credential, and trying it anyway just delays the real answer."""
    if key and key != "local":
        return True
    return any(h in (url or "").lower() for h in ("localhost", "127.0.0.1", "11434"))


# ── LOCAL TITULAR: preferred when it is there, stepped over when it is not (2026-08-19, operator's rule) ───────
# «Locally we can use Ollama as titular when available, but the system must work NON-STOP.» Those
# two halves pull in opposite directions and the whole design is in reconciling them: a local titular is free and
# private, and it is also the one rung that can simply not be there — the model not pulled, Ollama not started, its
# queue full because a 41 GB model owns the GPU (observed twice in production, 2026-08-18 and again today).
#
# So a local titular is HEALTH-GATED and the gate EXPIRES. Two decisions worth stating because the opposite of each
# is the bug this repo has already paid for:
#   · The verdict is CACHED but never LATCHED (`_LOCAL_TTL_S`). `memory/embeddings.py::_resolve_backend` cached a
#     single probe for the whole process and one transient hiccup at boot demoted the vector space for 300 s — the
#     defect V2-103 traced 51.6% of vector-less rows to. Non-stop means recovery must need no restart.
#   · The gate asks whether the MODEL is there, not just the server. Ollama answers `/api/tags` perfectly while
#     serving a model you never pulled — so a server-only probe would hand the write path a rung that 404s on
#     every call, which is indistinguishable from the profile bug this shipped alongside (a local model NAME sent
#     to a cloud endpoint, 400 on every write, every turn silently on the lossy heuristic).
# A local rung that is NOT ready is skipped, and the chain starts at DeepSeek V4 Flash direct — never at nothing.
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1", "11434")
_LOCAL_TTL_S = float(os.getenv("ZAELAR_LOCAL_PROBE_TTL_S", "60"))
_local_probe: dict[str, tuple[float, bool]] = {}     # "{url}|{model}" -> (checked_at, ready)


def is_local_endpoint(url: str) -> bool:
    return any(h in (url or "").lower() for h in _LOCAL_HOSTS)


def local_titular_ready(url: str, model: str) -> bool:
    """True if this local endpoint is answering AND serving `model`. Cached for `_LOCAL_TTL_S`, fail-CLOSED.

    Fail-closed is the right default HERE, against the fail-open posture of the rest of this module: a wrong «yes»
    spends the write on a rung that cannot answer, while a wrong «no» just uses the cloud rung that was going to be
    next anyway. The cost of the two mistakes is not symmetric, so the default is not either."""
    import time as _t
    key = f"{url}|{model}"
    hit = _local_probe.get(key)
    now = _t.monotonic()
    if hit and (now - hit[0]) < _LOCAL_TTL_S:
        return hit[1]
    ready = False
    try:
        # `/api/tags` hangs off the ROOT, not under the OpenAI-compatible `/v1` the chat calls use.
        root = (url or "").rstrip("/")
        for suffix in ("/v1", "/api"):
            if root.endswith(suffix):
                root = root[: -len(suffix)]
        req = urllib.request.Request(root + "/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3.0) as r:
            names = [str((m or {}).get("name") or "") for m in (json.loads(r.read().decode()).get("models") or [])]
        want = (model or "").strip()
        # `embeddinggemma` and `embeddinggemma:latest` are the same model; `qwen2.5:7b` and `qwen2.5:14b` are not,
        # so the tag is only ignored when the CONFIG omitted it.
        ready = any(n == want or (":" not in want and n.split(":")[0] == want) for n in names)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"memllm: local probe {url} failed ({str(e)[:80]}) -> skipping the local titular")
    _local_probe[key] = (now, ready)
    return ready


def reset_local_probe() -> None:
    """Drop the cached verdicts (tests, and after an operator changes the profile). Also clears the
    once-per-pair incoherence warnings, so a test that fixes a config sees it complain again."""
    _local_probe.clear()
    _warned_pairs.clear()


# ── A MODEL NAMED WITHOUT ITS ENDPOINT ──────────────────────────────────────────────────────────────────────
# An Ollama tag (`name:tag`, no vendor slash) can only be served by an Ollama endpoint: every broker in the
# catalogue names its models `vendor/model`. So «local tag @ cloud endpoint» is not a model that MIGHT be
# missing — it is a pair that cannot work, and asking anyway buys a guaranteed 404 on every single call.
_warned_pairs: set[str] = set()


def pair_incoherent(url: str, model: str) -> bool:
    """True when `model` is an Ollama-style tag and `url` is NOT a local endpoint.

    This is the SHAPE of the trap a config falls into when a model is named without its endpoint: the two halves
    come from different layers (a profile, an env var, the store, a default) and nothing checks that they describe
    the same provider. Measured 2026-08-20 in every sandboxed `use_cases` round — ~8-10 per round: a stale
    `MEM_PROCESSOR_MODEL=qwen2.5:3b` in the operator's env file beat the checked-in cloud default, because the env
    fallback applies whenever the store has no value and a fresh workspace has no store. Every distillation paid a
    404 to AIMLAPI first; before the failover chain existed (2026-08-19) it paid three and then wrote through the
    lossy heuristic, silently.

    Deliberately a SHAPE check and not a provenance check: the same pair is equally broken whether it came from an
    env var, a half-written profile, or an operator typing a local model into the ⚙ while the endpoint stayed in
    the cloud — and the caller cannot always tell which layer won."""
    m = (model or "").strip()
    if not m or "/" in m or ":" not in m:
        return False
    return not is_local_endpoint(url)


def note_incoherent_pair(where: str, url: str, model: str, *, served: str | None = None) -> None:
    """Say it ONCE per pair. This is a configuration error, not an event: it repeats on every write, and a warning
    that repeats 10 times a round is a warning the operator learns to scroll past."""
    key = f"{where}|{url}|{model}"
    if key in _warned_pairs:
        return
    _warned_pairs.add(key)
    tail = f" -> writing through {served}" if served else ""
    logger.warning(f"{where}: «{model}» is an Ollama tag but {url} is not a local endpoint — a model was named "
                   f"without its endpoint, so this pair can only 404{tail}. Fix the pair (model AND base_url) in "
                   f"config §memory, or clear the stale MEM_PROCESSOR_MODEL/URL env override.")
    try:
        from voice import health_state
        health_state.record("memory", "degraded", f"config incoherente: {model} @ {url}")
    except Exception:  # noqa: BLE001
        pass


def failover_rungs(task: str, *, titular: tuple[str, str],
                   disable_thinking: bool = False) -> list[tuple[str, str, str, bool]]:
    """The FALLBACK rungs for a task, given whoever the caller resolved as titular. Exists as its own entry point
    because `distill`'s titular is resolved by `nucleo/mem_processor.py` (see `_FAILOVER`), not by `resolve()` —
    it needs the ORDER without this module guessing its endpoint.

    Skips a rung the config already promoted to titular, and skips one whose credential is absent: a request with
    no key buys a 401 and a slower failure, never a chance."""
    rungs: list[tuple[str, str, str, bool]] = []
    for f_url, f_model in _FAILOVER.get(task, ()):
        if (f_url, f_model) == titular:
            continue
        f_key = _endpoint_key(f_url)
        if not _has_credential(f_url, f_key):
            continue
        # `disable_thinking` is per-TASK, but honoring it only means anything where the endpoint obeys it (see the
        # payload note in `_attempt`); carrying the task's own value keeps one decision instead of two.
        rungs.append((f_url, f_model, f_key, disable_thinking))
    return rungs


def chain(task: str) -> list[tuple[str, str, str, bool]]:
    """Ordered `(url, model, key, disable_thinking)` rungs: this task's titular first, then its fallbacks.

    The TITULAR is kept even without a credential — dropping it would silently substitute a different model for
    the one the config names, turning a visible misconfiguration into a wrong-model-answered-fine, which is the
    harder of the two bugs to ever notice.

    A LOCAL titular that is not answering is a DIFFERENT case and IS stepped over: a missing credential is a
    misconfiguration worth surfacing, while a local model being absent or its server busy is an ordinary,
    transient fact of a self-hosted machine — and the rule is that the system keeps working through it."""
    url, model, key, disable_thinking = resolve(task)
    head = [(url, model, key, disable_thinking)]
    if is_local_endpoint(url) and not local_titular_ready(url, model):
        head = []
    elif pair_incoherent(url, model):
        # Not «might be down» — CANNOT work (see `pair_incoherent`). Skipping it saves a 404 per call; the
        # `rungs or [...]` guard below still keeps it when there is nowhere to relay to, so a misconfigured
        # single-rung deployment gets the real error instead of silence.
        head = []
    rungs = head + failover_rungs(task, titular=(url, model), disable_thinking=disable_thinking)
    if not head and rungs and pair_incoherent(url, model):
        note_incoherent_pair(f"memllm[{task}]", url, model, served=rungs[0][1])
    # Never return an EMPTY chain: with the local titular down and every fallback uncredentialed there is nothing
    # to relay to, and handing back [] would make `chat_sync` report «0 rungs exhausted» — a true statement that
    # hides the actual cause. Keeping the titular makes the real error (connection refused / model not found)
    # reach the log and the ◉.
    return rungs or [(url, model, key, disable_thinking)]


def _note_relay(task: str, model: str, url: str, failures: list[str]) -> None:
    """A relay means the titular is DOWN — that belongs in the ◉, not in a log line nobody reads (the lesson this
    module already paid for three times). Fail-open: reporting a relay can never break the relay."""
    detail = " · ".join(failures)[:200]
    logger.warning(f"memllm[{task}]: relevo a {model} @ {url} tras {detail}")
    try:
        from voice import health_state
        health_state.record("memory", "degraded", f"{task}: relevo a {model} ({detail})")
    except Exception:  # noqa: BLE001
        pass


def resolve(task: str) -> tuple[str, str, str, bool]:
    """(url, model, key, disable_thinking) for a catalog task. Config wins; empty key → resolved by endpoint.
    `disable_thinking` is NOT config-overridable yet (it's a per-task quality decision, not an endpoint) — add
    `{task}_disable_thinking` to config/v2.py's `memory` block if/when that's genuinely needed, not before."""
    base_url, model, disable_thinking = _DEFAULTS.get(task, _DEFAULTS["rem"])
    key = ""
    try:
        from config import v2 as _v2
        mem = _v2.get("memory") or {}
        base_url = (mem.get(f"{task}_base_url") or "").strip() or base_url
        model = (mem.get(f"{task}_model") or "").strip() or model
        key = (mem.get(f"{task}_api_key") or "").strip()
    except Exception:
        pass
    return base_url, model, key or _endpoint_key(base_url), disable_thinking


def _endpoint_key(url: str) -> str:
    # Single BY-ENDPOINT resolver (`nucleo/provider_keys.py`, V2-098) — this used to know only 4 of the ~9
    # endpoints (missing gemini/mistral/z.ai/deepseek/moonshot).
    from nucleo.provider_keys import key_for_endpoint
    return key_for_endpoint(url, default="local")


# ── Pooled HTTP POST (2026-09-01, latency) ───────────────────────────────────────────────────────────────────
# The hot-path judges (`directed`, `turn_complete`) run BEFORE the brain request of almost every turn, and this
# module used to open a fresh urllib connection per call — a full DNS+TCP+TLS handshake (~150-400 ms measured) to
# api.deepseek.com every single time, on top of the model's own latency. One shared keep-alive client removes the
# handshake from every call after the first. httpx ships with the `openai` dependency the engine already requires;
# the urllib fallback keeps this module honest about its "no hard deps" promise — if httpx is somehow absent the
# behavior degrades to exactly what it was, never to a failure.
_HTTP_POOL = None   # httpx.Client (thread-safe, keep-alive) | False = unavailable, use urllib


def _post_json(full_url: str, payload: dict, *, headers: dict, timeout: float) -> dict:
    """POST JSON and decode the JSON reply, reusing one keep-alive connection pool across calls. HTTP errors
    raise (the caller's chain/fail-open logic handles them, same as with urllib)."""
    global _HTTP_POOL
    body = json.dumps(payload).encode()
    if _HTTP_POOL is None:
        try:
            import httpx
            _HTTP_POOL = httpx.Client()
        except Exception:
            _HTTP_POOL = False
    if _HTTP_POOL is not False:
        r = _HTTP_POOL.post(full_url, content=body, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json()
    req = urllib.request.Request(full_url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _attempt(url: str, model: str, key: str, disable_thinking: bool, *, system: str, user: str,
             max_tokens: int, temperature: float, timeout: float) -> str:
    """ONE request to ONE rung. Raises on anything that isn't usable content — including an EMPTY answer, which
    the direct DeepSeek endpoint produces when reasoning eats the whole `max_tokens` (`finish_reason=length`,
    `content=""`, no exception). Treating that as an answer would hand the caller silence with a success flag."""
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    # Per-task decision (see `_DEFAULTS` comment above), not inferred from the endpoint: DeepSeek reasons even
    # when told the turn can't afford it (V2-097), and only `api.deepseek.com` DIRECT honors this field at all
    # (AIMLAPI ignores it) — but honoring it is only correct for tasks benchmarked reasoning-OFF.
    if disable_thinking and "deepseek" in model.lower() and "api.deepseek.com" in url.lower():
        payload["thinking"] = {"type": "disabled"}
    # EGRESS (T304): if the deployment mediates egress, neither the URL nor the key belongs to the provider.
    from nucleo import llm_egress
    url, key, _extra = llm_egress.route(url, key)
    data = _post_json(
        url.rstrip("/") + "/chat/completions",
        payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 # AIMLAPI sits behind Cloudflare and 403s urllib's default UA → browser UA
                 # (same workaround as fast_client)
                 "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"},
        timeout=timeout,
    )
    content = data["choices"][0]["message"]["content"]
    if not (content or "").strip():
        raise RuntimeError("respuesta vacía (razonamiento se comió el presupuesto)")
    _record_usage(data.get("usage"), url, model)
    return content


def chat_sync(task: str, system: str, user: str, *, max_tokens: int = 900,
              temperature: float = 0.2, timeout: float = 60.0,
              model_override: str | None = None, url_override: str | None = None) -> str | None:
    """SYNCHRONOUS chat (urllib, no deps) — intended to run INSIDE an `asyncio.to_thread` (REM sleep) or
    in scripts/benches. Returns the content, or None if NO rung responds (the caller fails open).

    Traverses `chain(task)` in order: titular → broker → OpenAI/Anthropic (operator rule, 2026-08-19).

    ⚠️ Un `model_override`/`url_override` DESACTIVA la cadena, a propósito. Los pasa quien PINCHA un modelo
    concrete model —a benchmark, the LoCoMo responder/judge— and a silent relay would turn the experiment's
    declaration into a lie: the report would say it measured one model while it had measured another."""
    if url_override or model_override:
        url, model, key, disable_thinking = resolve(task)
        if url_override:
            url, key = url_override, _endpoint_key(url_override)
        if model_override:
            model = model_override
        try:
            return _attempt(url, model, key, disable_thinking, system=system, user=user,
                            max_tokens=max_tokens, temperature=temperature, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"memllm[{task}]: {model} @ {url} falló: {str(e)[:160]} → fail-open (pinned)")
            return None

    rungs = chain(task)
    failures: list[str] = []
    for pos, (url, model, key, disable_thinking) in enumerate(rungs):
        try:
            content = _attempt(url, model, key, disable_thinking, system=system, user=user,
                               max_tokens=max_tokens, temperature=temperature, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{model}: {str(e)[:120]}")
            continue
        if pos:
            _note_relay(task, model, url, failures)
        return content
    logger.warning(f"memllm[{task}]: {len(rungs)} escalón(es) agotados ({' · '.join(failures)[:200]}) → fail-open")
    try:
        from voice import health_state
        health_state.record("memory", "outage", f"{task}: sin proveedor ({' · '.join(failures)[:160]})")
    except Exception:  # noqa: BLE001
        pass
    return None


# ── ACTUAL USAGE (2026-08-09) — same closure as in `mem_processor`: memory LLM tasks are
# cloud calls like any other and were not reported to Energy, so in a cloud account REM sleep (and
# i18n bundle generation) consumed free tokens in the counter. `last_usage()` also gives the REAL tokens
# to the synthesis bench (§12.4) to calculate cost per sleep using measured numbers. Always fail-open: measuring
# must NEVER bring down a consolidation.
_last_usage: dict = {}


def last_usage() -> dict:
    """Tokens from the last call (`{prompt_tokens, completion_tokens, total_tokens}`), `{}` if the provider did not
    return them. Diagnostics/bench only."""
    return dict(_last_usage)


def _record_usage(usage: dict | None, base_url: str, model: str) -> None:
    global _last_usage
    # Without `usage`, do NOT return: report it with counters set to None, and `energy_meter` applies its
    # floor (2026-08-13). Returning here was free for the provider that does not report — the same failure
    # as the zero tariff of 2026-08-05, one level higher: the call was made and paid for.
    if not isinstance(usage, dict):
        _last_usage = {}
        usage = {}
    else:
        _last_usage = {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    from nucleo import energy_meter as _energy
    _energy.meter_openai_response({"usage": usage}, base_url=base_url, model=model)


# ── REM sleep SYNTHESIS (the hook injected by the loop into memory/rem.py) ─────────────────────────────────────
_REM_SYSTEM = (
    "Eres el consolidador de memoria de un asistente personal. Recibes GRUPOS de recuerdos del operador "
    "agrupados por concepto. Para cada grupo, destila 1 INSIGHT: una síntesis de ALTO NIVEL que un buen "
    "asistente sacaría de esos datos (patrón, gusto, situación, hábito) — no un resumen que repita la lista. "
    "Reglas DURAS: (1) SIEMPRE en {lang} (la memoria es MONOLINGÜE, en el idioma canónico del operador — "
    "traduce si los datos vienen en otro idioma); (2) 1-2 frases por insight, en 3ª persona; "
    "(3) CONSERVA nombres propios, cifras y fechas de los datos — nunca los generalices; (4) NO inventes nada "
    "que no esté en los datos; (5) si un grupo no da para un insight con sustancia, devuélvelo con insight null. "
    "Responde SOLO un array JSON: [{\"concept\": str, \"insight\": str|null}, …]"
)


def _default_lang() -> str:
    """`langs.current_code()` already reads ZAELAR_LANGUAGE and falls back to DEFAULT_LANG ("en")."""
    try:
        from voice.engine.core import langs
        return langs.current_code()
    except Exception:
        return "en"


def _canonical_lang_native() -> str:
    """Native name of the memory's CANONICAL language (decision 2026-07-10: memory is MONOLINGUAL, in the
    operator's language — the same `state.language` field read by `nucleo/mem_processor.py::_render` for the
    writing HEART). Fail open to Spanish if memory or the language catalogue is unavailable."""
    # The fallback is the ENGINE's single source of truth, not a hardcoded language. Writing "es" here made
    # this yet another independent opinion about which language the product speaks — and the one that wins when
    # the memory is unreachable, i.e. exactly on a cold first run.
    code = _default_lang()
    try:
        from memory import api as _memory
        code = (_memory.state().get("language") or code)
    except Exception:
        pass
    try:
        from voice.engine.core import langs
        return langs.spec(code).native
    except Exception:
        return "castellano"


def synthesize_concept_groups(groups: list[dict], *, model_override: str | None = None,
                              url_override: str | None = None) -> list[dict]:
    """Synthesis hook for `memory/rem.py` (SYNCHRONOUS — REM runs in to_thread). `groups` =
    [{"concept": str, "pills": [str, …]}, …] → [{"concept": str, "insight": str|None}, …]. Fail-open: []."""
    if not groups:
        return []
    user = json.dumps(
        [{"concept": g["concept"], "recuerdos": g["pills"][:12]} for g in groups],
        ensure_ascii=False, indent=1,
    )
    # `.replace`, NOT `.format` (fix 2026-08-09): the prompt ENDS with a literal JSON example
    # —[{"concept": str, "insight": str|null}]— y `str.format` interpreta esas llaves como marcadores →
    # `KeyError: '"concept"'` on EVERY call. `rem.synthesize` catches the exception and returns 0 with a
    # `logger.warning`, so the deep-sleep INSIGHTS phase had been silently broken since the `{lang}` interpolation
    # for the monolingual rule was added (the §12.2 numbers predate that change). Same language as `mem_processor`,
    # which already used `.replace` for its slot catalogue.
    # Covered by tests/memory/unit/test_rem_prompt.py so it cannot recur.
    system = _REM_SYSTEM.replace("{lang}", _canonical_lang_native())
    # `max_tokens` GENEROUS and timeout GENEROUS (2026-08-09). REM sleep runs ONCE per day, overnight, in
    # `to_thread`: nobody is waiting, and writing may be SLOW (V2-013 invariant) — reading may not.
    #   · max_tokens 1200 → 4000: with 8 groups, a verbose or REASONING model (deepseek-v4-flash thinks even when
    #     asked not to) exhausts the budget BEFORE closing the array → truncated JSON → `_parse` returns []
    #     → "no insights" WITHOUT an error. Measured: with 1200, 1 in 3 calls failed (one hit exactly 1200);
    #     with 4000, 3/3 were valid, emitting only ~1,100 tokens. The high ceiling costs NOTHING: emitted tokens are paid for.
    #   · timeout 60 → 240s: a slow broker batch consumed the entire consolidation night due to haste
    #     nobody needed.
    content = chat_sync("rem", system, user, max_tokens=4000, timeout=240.0,
                        model_override=model_override, url_override=url_override)
    if not content:
        return []
    try:
        start, end = content.find("["), content.rfind("]")
        arr = json.loads(content[start:end + 1])
        out = []
        for it in arr:
            if isinstance(it, dict) and it.get("concept"):
                ins = it.get("insight")
                out.append({"concept": str(it["concept"]),
                            "insight": (str(ins).strip() or None) if ins else None})
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning(f"memllm[rem]: respuesta no parseable: {str(e)[:120]}")
        return []


# ── V2-104: second fidelity opinion — a FRESH call, independent of the one that generated the insight ──────────
_GROUNDING_SYSTEM = (
    "Verificas la fidelidad de un INSIGHT de memoria contra los DATOS que lo originaron. Responde SOLO la "
    "palabra true si CADA afirmación del insight está respaldada directamente por los datos (sin inventar "
    "nombres, cifras, fechas, ni generalizar más de lo que los datos permiten). Responde SOLO la palabra false "
    "si el insight añade CUALQUIER cosa que no esté en los datos. Nada más en tu respuesta."
)


def verify_insight_grounded(insight: str, pills: list[str], *, model_override: str | None = None,
                            url_override: str | None = None) -> bool:
    """Optional hook for `memory/rem.py::synthesize()` (injected by the loop alongside
    `synthesize_concept_groups`, same `summarize_fn` pattern). Second opinion, IN A SEPARATE CALL — self-judgment
    within the same response that generated the insight is weaker than an independent judgment of the finished result.
    Fail-CLOSED (unlike the other memory tasks, which are fail-open): without a clear response, treat it as
    UNRELIABLE — losing a legitimate insight is cheaper than allowing an invented one through, now that
    `writer.demote_summarized` displaces the correct facts instead of merely competing with them (V2-103)."""
    if not insight or not pills:
        return False
    user = json.dumps({"insight": insight, "datos": pills[:12]}, ensure_ascii=False, indent=1)
    content = chat_sync("rem", _GROUNDING_SYSTEM, user, max_tokens=200, timeout=60.0,
                        model_override=model_override, url_override=url_override)
    if not content:
        return False
    return content.strip().lower().startswith("true")


# ── V2-031 T2: reformulations for the paraphrase index (off-hot-path, from REM) ──────────────────────────
_PARAPHRASE_SYSTEM = (
    "Reformulas una frase de memoria de un asistente personal para dar VOCABULARIO ALTERNATIVO — sinónimos, "
    "categoría/hiperónimo, forma de referirse al mismo hecho con OTRAS palabras — para que una pregunta con "
    "vocabulario distinto SIGA encontrando el mismo dato (vocab-gap). NO sirve reordenar o cambiar levemente "
    "la misma frase: 'toca la guitarra los sábados' → 'los sábados toca la guitarra' NO VALE, no aporta "
    "vocabulario nuevo. SÍ vale: 'toca la guitarra los sábados' → 'es músico, toca un instrumento de cuerda'. "
    "MANTIENES el significado exacto — ni añades ni quitas información, ni cifras, ni nombres — pero CAMBIAS "
    "las palabras de contenido por su categoría o un sinónimo real. Responde SOLO un array JSON de 1 a 2 "
    "strings, sin explicación: [\"reformulación 1\", \"reformulación 2\"]"
)


def generate_paraphrases(text: str, *, model_override: str | None = None,
                         url_override: str | None = None) -> list[str]:
    """1-2 reformulations of `text`, for `writer.index_paraphrases()`. Fail-open: [] if the model does not respond
    or the response does not parse — without paraphrases, the pill is still retrieved through its own embedding,
    as always; this only ADDS retrieval surface, it is never the sole path."""
    text = (text or "").strip()
    if not text:
        return []
    content = chat_sync("paraphrase", _PARAPHRASE_SYSTEM, text, max_tokens=300, timeout=60.0,
                        model_override=model_override, url_override=url_override)
    if not content:
        return []
    try:
        start, end = content.find("["), content.rfind("]")
        arr = json.loads(content[start:end + 1])
        return [str(s).strip() for s in arr if isinstance(s, str) and str(s).strip()][:2]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"memllm[paraphrase]: respuesta no parseable: {str(e)[:120]}")
        return []
