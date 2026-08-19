"""nucleo/memllm.py — ROUTER interno de modelos del MÓDULO DE MEMORIA (V2-056, 2026-07-20).

El módulo de memoria tiene varias tareas de LLM con perfiles distintos, cada una elegible POR CONFIG y con la
credencial resuelta POR ENDPOINT (lección de la auditoría 2026-07-19: una key suelta de env enviada al endpoint
equivocado tumbó el CORAZÓN 2 días en silencio). Una sola costura para todas:

  - `distill`  → el CORAZÓN de escritura (lo implementa `nucleo/mem_processor.py` con su cola/semántica propia;
                 este router NO lo reemplaza — queda aquí documentado como tarea del catálogo).
  - `rem`      → la SÍNTESIS del sueño profundo (`memory/rem.py` la recibe INYECTADA — la memoria no importa
                 nucleo; el loop cablea `synthesize_concept_groups` como hook, patrón `summarize_fn`).
  - (futuras)  → `context_router` (repesca del dossier), jueces de calidad de píldora…

Todo va OFF-hot-path (jamás en el turno de voz). Cada tarea lee `config §memory.<task>_model/_base_url/_api_key`
con fallback a defaults; la key vacía se resuelve por endpoint (OpenAI/AIMLAPI/xAI/Groq → env correspondiente).
Benchmarks que sustentan los defaults: `zaelar-model-benchmarks.md §12` (write-completeness + síntesis REM).
"""
from __future__ import annotations

import json
import os
import urllib.request

from loguru import logger

# Fallback de última instancia (si `config §memory` no se puede leer). Debe coincidir con el default de
# `config/v2.py §memory` — apuntar a OpenAI aquí significaba, en la nube, fallar siempre: no hay OPENAI_API_KEY
# entre los secretos que inyecta el provisioner (2026-08-09, misma corrección que en mem_processor).
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
    # i18n (V2-089): traducción del UI a un idioma nuevo en la INICIALIZACIÓN (i18n/init). Off-hot-path, calidad
    # importa (scripts no-latinos: árabe, chino, japonés…) → modelo fuerte. Override en config §memory.
    #
    # 2026-08-09 — apuntaba a OpenAI DIRECTO (gpt-4o) y era el último resto de esa cuenta en la memoria: en la
    # nube no hay OPENAI_API_KEY, así que generar el bundle de un idioma nuevo habría fallado en silencio (mismo
    # patrón que tumbó el CORAZÓN en julio y el REM hasta ayer). Norma del operador: TODO por el broker AIMLAPI,
    # una sola cuenta que gestionar. Sonda al tamaño REAL del lote (`_BATCH=50`, ja/ar/zh, 15 claves con
    # placeholder) antes de elegir sustituto:
    # ⚠️ 2026-08-19 — NORMA DEL OPERADOR: DeepSeek V4 Pro DIRECTO y nada más. Esta tarea era la ÚLTIMA que
    # seguía eligiendo un modelo de Anthropic, con una medición del 2026-08-09 detrás (§12.5) que decía que
    # `deepseek-v4-flash` acertaba pero RAZONABA 6-8× los tokens que entregaba, 50-60 s por lote. Ese hallazgo
    # sigue siendo cierto y sigue escrito, pero era sobre **v4-FLASH por el BROKER**, que es justo la
    # combinación donde `thinking:disabled` se acepta y se ignora (V2-097). Por el endpoint NATIVO el parámetro
    # se OBEDECE, así que el motivo por el que se descartó DeepSeek aquí desaparece con el cambio de endpoint.
    # Si vuelve a razonar de más, se mide y se escribe — no se vuelve a otro proveedor por costumbre.
    # Sigue siendo la tarea menos sensible al precio del sistema: se paga UNA vez por idioma (514 claves ≈ 11
    # lotes), así que lo que importa es que el lote no se pierda, no lo que cuesta.
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
    # paraphrase (V2-031 T2, 2026-08-17): 1-2 reformulaciones de una píldora durable, generadas off-hot-path
    # desde REM (nunca en el turno) para indexar vectores extra que cierren el vocab-gap en la lectura. Mismo
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
    # rem — §12.2 measured `gpt-4.1-mini` at 100% on THIS task, so the last rung is evidence, not hope.
    "rem": ((_DS, "deepseek-v4-flash"), (_AIML, "deepseek/deepseek-v4-flash"), (_AIML, "openai/gpt-4.1-mini")),
    # distill — the WRITE HEART. `nucleo/mem_processor.py` makes the call AND resolves its own TITULAR (its config
    # keys are the historical `mem_processor_*`, with env fallbacks, and that name is synchronized across three
    # deploy sites — `config/v2.py`, `fly.accounts.toml`, the cloud provisioner). What lives HERE is only its
    # ORDER of FALLBACKS, so there is exactly one list of them; it reads them via `failover_rungs`, not `chain`.
    # The rungs are the ones §12.3 already named after sweeping 21 candidates × 34 cases. ⛔ NOT `gpt-4o-mini`:
    # cheaper and VETOED (puts an allergy stated in English into `slot=operator.diet`, which a later diet change
    # would erase).
    "distill": ((_DS, "deepseek-v4-flash"), (_AIML, "deepseek/deepseek-v4-flash"),
                (_AIML, "google/gemini-2.5-flash"), (_AIML, "openai/gpt-4.1-mini")),
    # paraphrase — NO DeepSeek rung on the broker, deliberately. This task only works with reasoning OFF (measured
    # 2026-08-18: with it on the entire budget goes to reasoning and `content` comes back EMPTY at every budget
    # tried) and the broker ACCEPTS `thinking:disabled` while ignoring it. That rung would answer 200 with nothing
    # in it, and a rung that reports success while delivering silence is worse than no rung. Non-reasoners only.
    # ⚠️ DeepSeek DIRECT is the FIRST rung here and the broker's DeepSeek is absent, which is the opposite of the
    # other tasks — because this one needs reasoning OFF and only the direct endpoint obeys the flag (see below).
    "paraphrase": ((_DS, "deepseek-v4-flash"), (_AIML, "openai/gpt-4.1-mini")),
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
# «En local podemos poner Ollama si está disponible como titular, pero el sistema debe funcionar NON-STOP.» Those
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
    """Drop the cached verdicts (tests, and after an operator changes the profile)."""
    _local_probe.clear()


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
    rungs = head + failover_rungs(task, titular=(url, model), disable_thinking=disable_thinking)
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
    # EGRESS (T304): si el despliegue media la salida, ni la URL ni la clave son las del proveedor.
    from nucleo import llm_egress
    url, key, _extra = llm_egress.route(url, key)
    req = urllib.request.Request(
        url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 # AIMLAPI va tras Cloudflare y 403ea al UA por defecto de urllib → UA de navegador
                 # (mismo workaround que fast_client)
                 "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    content = data["choices"][0]["message"]["content"]
    if not (content or "").strip():
        raise RuntimeError("respuesta vacía (razonamiento se comió el presupuesto)")
    _record_usage(data.get("usage"), url, model)
    return content


def chat_sync(task: str, system: str, user: str, *, max_tokens: int = 900,
              temperature: float = 0.2, timeout: float = 60.0,
              model_override: str | None = None, url_override: str | None = None) -> str | None:
    """Chat SÍNCRONO (urllib, sin deps) — pensado para correr DENTRO de un `asyncio.to_thread` (el sueño REM) o
    en scripts/benches. Devuelve el content, o None si NINGÚN escalón responde (el llamador hace fail-open).

    Recorre `chain(task)` en orden: titular → broker → OpenAI/Anthropic (norma del operador, 2026-08-19).

    ⚠️ Un `model_override`/`url_override` DESACTIVA la cadena, a propósito. Los pasa quien PINCHA un modelo
    concreto —un banco, el respondedor/juez de LoCoMo— y ahí un relevo silencioso convertiría la declaración del
    experimento en una mentira: el informe diría que midió con un modelo y habría medido con otro."""
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


# ── CONSUMO REAL (2026-08-09) — mismo cierre que en `mem_processor`: las tareas de LLM de la memoria son
# llamadas de nube como cualquier otra y no reportaban a Energy, así que en una cuenta cloud el sueño REM (y la
# generación de bundles i18n) consumían tokens gratis en el contador. `last_usage()` además da los tokens REALES
# al bench de síntesis (§12.4) para calcular el coste por sueño con números medidos. Fail-open siempre: medir
# NUNCA puede tumbar una consolidación.
_last_usage: dict = {}


def last_usage() -> dict:
    """Tokens de la última llamada (`{prompt_tokens, completion_tokens, total_tokens}`), `{}` si el proveedor no
    los devolvió. Solo diagnóstico/bench."""
    return dict(_last_usage)


def _record_usage(usage: dict | None, base_url: str, model: str) -> None:
    global _last_usage
    # Sin `usage` NO se sale: se reporta igual con los contadores a None, y `energy_meter` aplica su
    # suelo (2026-08-13). Salirse aquí era gratis para el proveedor que no informa — el mismo fallo
    # que la tarifa a cero de 2026-08-05, un nivel más arriba: la llamada se hizo y se pagó.
    if not isinstance(usage, dict):
        _last_usage = {}
        usage = {}
    else:
        _last_usage = {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    from nucleo import energy_meter as _energy
    _energy.meter_openai_response({"usage": usage}, base_url=base_url, model=model)


# ── SÍNTESIS del sueño REM (el hook que el loop inyecta en memory/rem.py) ─────────────────────────────────────
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
    """Nombre nativo del idioma CANÓNICO de la memoria (decisión 2026-07-10: la memoria es MONOLINGÜE, en el
    idioma del operador — mismo campo `state.language` que lee `nucleo/mem_processor.py::_render` para el
    CORAZÓN de escritura). Fail-open a español si la memoria o el catálogo de idiomas no están disponibles."""
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
    """Hook de síntesis para `memory/rem.py` (SÍNCRONO — REM corre en to_thread). `groups` =
    [{"concept": str, "pills": [str, …]}, …] → [{"concept": str, "insight": str|None}, …]. Fail-open: []."""
    if not groups:
        return []
    user = json.dumps(
        [{"concept": g["concept"], "recuerdos": g["pills"][:12]} for g in groups],
        ensure_ascii=False, indent=1,
    )
    # `.replace`, NO `.format` (fix 2026-08-09): el prompt TERMINA con un ejemplo de JSON literal
    # —[{"concept": str, "insight": str|null}]— y `str.format` interpreta esas llaves como marcadores →
    # `KeyError: '"concept"'` en CADA llamada. `rem.synthesize` captura la excepción y devuelve 0 con un
    # `logger.warning`, así que la fase de INSIGHTS del sueño profundo llevaba rota EN SILENCIO desde que se
    # añadió la interpolación `{lang}` de la regla monolingüe (los números de §12.2 son anteriores a ese
    # cambio). Mismo idioma que `mem_processor`, que ya usaba `.replace` para su catálogo de slots.
    # Cubierto por tests/memory/unit/test_rem_prompt.py para que no pueda repetirse.
    system = _REM_SYSTEM.replace("{lang}", _canonical_lang_native())
    # TIMEOUT GENEROSO (2026-08-09): el sueño REM corre UNA vez al día, de madrugada, en `to_thread` — no hay
    # nadie esperando. El default de 60s se quedaba corto: el modelo titular emite ~2.200 tokens de salida para
    # los 8 grupos, y en una tanda lenta del broker se pasa de 60s → la noche entera sin consolidar por prisa
    # que nadie tenía. Escribir puede ser LENTO (invariante V2-013); leer es lo que no puede.
    # `max_tokens` HOLGADO y timeout GENEROSO (2026-08-09). El sueño REM corre UNA vez al día, de madrugada, en
    # `to_thread`: no hay nadie esperando, y escribir puede ser LENTO (invariante V2-013) — leer es lo que no.
    #   · max_tokens 1200 → 4000: con 8 grupos, un modelo verboso o que RAZONA (deepseek-v4-flash piensa aunque
    #     se le pida que no) agota el presupuesto ANTES de cerrar el array → JSON truncado → `_parse` devuelve []
    #     → "sin insights" SIN error. Medido: con 1200 fallaba 1 de cada 3 llamadas (una topó exactamente en
    #     1200); con 4000, 3/3 válidas emitiendo solo ~1.100 tokens. El techo alto NO cuesta: se paga lo emitido.
    #   · timeout 60 → 240s: una tanda lenta del broker se comía la noche entera de consolidación por una prisa
    #     que nadie tenía.
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


# ── V2-104: segunda opinión de fidelidad — llamada FRESCA, independiente de la que generó el insight ──────────
_GROUNDING_SYSTEM = (
    "Verificas la fidelidad de un INSIGHT de memoria contra los DATOS que lo originaron. Responde SOLO la "
    "palabra true si CADA afirmación del insight está respaldada directamente por los datos (sin inventar "
    "nombres, cifras, fechas, ni generalizar más de lo que los datos permiten). Responde SOLO la palabra false "
    "si el insight añade CUALQUIER cosa que no esté en los datos. Nada más en tu respuesta."
)


def verify_insight_grounded(insight: str, pills: list[str], *, model_override: str | None = None,
                            url_override: str | None = None) -> bool:
    """Hook opcional de `memory/rem.py::synthesize()` (inyectado por el loop junto a `synthesize_concept_groups`,
    mismo patrón `summarize_fn`). Segunda opinión, EN OTRA LLAMADA — el autocriterio dentro de la misma
    respuesta que generó el insight es más débil que un juicio independiente sobre el resultado ya terminado.
    Fail-CLOSED (a diferencia del resto de tareas de memoria, que son fail-open): sin respuesta clara, se trata
    como NO fiable — perder un insight legítimo sale más barato que dejar pasar uno inventado, ahora que
    `writer.demote_summarized` hace que desplace los hechos correctos en vez de solo competir con ellos
    (V2-103)."""
    if not insight or not pills:
        return False
    user = json.dumps({"insight": insight, "datos": pills[:12]}, ensure_ascii=False, indent=1)
    content = chat_sync("rem", _GROUNDING_SYSTEM, user, max_tokens=200, timeout=60.0,
                        model_override=model_override, url_override=url_override)
    if not content:
        return False
    return content.strip().lower().startswith("true")


# ── V2-031 T2: reformulaciones para el índice de paráfrasis (off-hot-path, desde REM) ──────────────────────────
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
    """1-2 reformulaciones de `text`, para `writer.index_paraphrases()`. Fail-open: [] si el modelo no responde
    o la respuesta no parsea — sin paráfrasis, la píldora se sigue recuperando por su propio embedding, igual
    que siempre; esto solo AÑADE superficie de recuperación, nunca es la única vía."""
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
