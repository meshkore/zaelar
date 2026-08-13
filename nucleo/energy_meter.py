#
# ENERGY METERING (INI-018, added 2026-07-24; extended 2026-08-05 — INI-019 addenda) — real usage →
# real cost → "Energy" units.
#
# Zaelar's product concept of "Energy" (web/src/components/Pricing.astro/Energy.astro,
# project/concept/docs/product/energy-model.md) had NO real conversion rate or ledger anywhere —
# confirmed by a full repo search before writing this. This module converts ACTUAL provider usage
# (LLM tokens, TTS characters, STT audio-seconds, Brain Worker tokens) into a real €-cost estimate,
# then into Energy units, and reports it fire-and-forget to the control-plane's persistent
# per-account ledger (see _post_usage_cloud_account).
#
# SCOPE: fires for real cloud accounts (`ZAELAR_USER_ID` — nucleo/cloud_account.py, wired
# 2026-08-05). The operator's own local install and every self-host install don't set it →
# enabled() False → zero cost, zero network calls.
#
# 2026-08-05 FINDING (see INI-019 addenda for the full incident writeup): report_llm_usage() was only
# ever called from the FlashBrain's voice turn (nucleo/flash/fast_client.py), and the rate table only
# covered "x.ai"/"api.openai.com" — but the FlashBrain's actual production model runs on AIMLAPI
# (a multi-model broker, config/v2.json §fast), which matched NEITHER row. Every real voice turn was
# metering silently to zero cost. Fixed by: (a) per-MODEL rates for the AIMLAPI broker (a single
# base_url covers dozens of differently-priced models — a base_url-only table cannot express that),
# (b) a non-None FALLBACK rate for any (base_url, model) this table doesn't yet know about, so a
# future unlisted provider degrades to "probably overcharges a little" instead of "silently free" —
# under-metering loses real money, over-metering by a small margin on a rare/unknown provider does not.
# Brain Workers (nucleo/workers/, Claude Code CLI relayed to Z.AI/Moonshot/local license) are metered
# too (report_worker_usage) — they were computing real usage/cost already (claude_session.py's stream-
# json "result" message) but discarding it into a UI chip, never into Energy.
#
# NUMBERS BELOW ARE DEFAULTS, NOT FINAL PRICING — flagged explicitly wherever they are business
# decisions, not technical facts:
#   - Per-provider/per-model $/token rates: real published pricing as of 2026-08-05 (web search) —
#     re-verify against the provider's own pricing page periodically, don't treat as permanently
#     accurate. Same norm as the rest of the repo (see V2-035's "never assume, verify" note).
#   - EUR_PER_ENERGY_UNIT (1 Energy = €0.01) and MARGIN_MULTIPLIER (4x raw cost) are OPERATOR
#     business decisions defaulted here for a working system — confirm/adjust, don't treat as final.
#   - The FALLBACK rate for an unmapped (base_url, model) is a deliberate business choice: better to
#     mildly over-meter an unknown provider (logged loudly so it gets a real rate added) than to ever
#     silently meter it as free.
#
import os
import time

import httpx
from loguru import logger

# $ per 1M tokens, (input, output), matched by substring against `base_url`. Covers providers that
# serve a single (or effectively single-priced) model directly — NOT brokers like AIMLAPI, which
# serve dozens of models at very different prices (see _MODEL_RATES below, which is consulted FIRST).
# Source: public provider pricing, 2026-08-05 — RE-VERIFY periodically, provider pricing changes.
_RATES_PER_1M_TOKENS_USD: dict[str, tuple[float, float]] = {
    "x.ai": (0.20, 0.50),               # Grok 4.1 Fast tier
    "api.openai.com": (0.40, 1.60),     # gpt-4.1-mini tier (OpenAI direct is no longer a default anywhere)
    "api.z.ai": (1.40, 4.40),           # GLM-5.2 — the Brain Workers' primary relay tier (code_agent)
    "moonshot.ai": (0.95, 4.00),        # Kimi K2.6 — the Brain Workers' secondary relay tier
}

# $ per 1M tokens, (input, output), matched by substring against the MODEL name. Consulted FIRST for
# every provider, not just brokers (changed 2026-08-13 — it used to be AIMLAPI-only).
#
# Why model-first is the general case: a base_url→rate row can only be right where one endpoint serves
# one price. That assumption has now broken TWICE. First with AIMLAPI (a broker, dozens of models at
# very different prices) — which is why this table was born. Then with xAI: the "x.ai" row said
# (0.20, 0.50), the Grok 4.1 Fast tier, but a Brain Worker on Grok Build runs **grok-4.5 at $2/$6** —
# 10x the input rate. A worker on Grok would have metered at a TWELFTH of its output cost. The model
# is what has a price; the endpoint is just where it is served. So the model decides, and base_url is
# only the fallback for endpoints that really do serve a single price.
_MODEL_RATES: dict[str, tuple[float, float]] = {
    # Serves TWO pieces since 2026-08-09: the FlashBrain (config §fast) and the memory CORAZÓN
    # (config §memory.mem_processor_model — see zaelar-model-benchmarks.md §12.3). Measured cost of
    # one distilled turn: ~4076 in + ~389 out tokens => ~$0.00068, i.e. $0.68 per 1000 turns.
    "deepseek-v4-flash": (0.14, 0.28),
    "claude-haiku-4.5": (1.00, 5.00),          # FlashBrain's _FALLBACK_MODEL
    # CORAZÓN fallback chain (§12.3), rated so a failover never meters as the generic fallback rate.
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gpt-4.1-mini": (0.40, 1.60),              # previous CORAZÓN titular; last link of the chain
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "grok-4-fast": (0.20, 0.50),
    "kimi-k2": (0.95, 4.00),
    "glm-4.7": (0.40, 1.75),
    "ministral-8b": (0.10, 0.10),
    "llama-3.3-70b": (0.59, 0.79),
    # Brain Workers conducidos por Grok Build (backend `grok_build`, 2026-08-13). Su CLI habla con xAI
    # DIRECTAMENTE (no por la cadena de relevo Anthropic), así que la sesión no reporta base_url y sin
    # una fila POR MODELO caería al fallback — cobrando la mitad del input, que es donde está el gasto
    # de un worker (73.851 in vs 1.231 out en una corrida medida). Precios verificados 2026-08-13 en la
    # tarifa pública de xAI. El input CACHEADO sí se modela (ver `_CACHED_READ_RATES_USD`, medido a
    # $0.30/1M). Lo que NO se modela todavía es el tramo LARGO de grok-4.5 ($4/$12 por encima de 200K de
    # prompt): con 500K de contexto una sesión larga puede cruzarlo y ahí volveríamos a cobrar de menos.
    "grok-4.5": (2.00, 6.00),
    "grok-4.6": (2.00, 6.00),
    "grok-4.3": (3.00, 15.00),
    # Los del relay de los workers, también por modelo (la fila por base_url se queda de respaldo).
    "glm-5.2": (1.40, 4.40),
    "kimi-k2.6": (0.95, 4.00),
    "deepseek-v4-pro": (0.28, 0.42),
}

# Applied when neither table above has a row for the (base_url, model) actually used. Deliberately NOT
# the cheapest rate seen (that would risk under-charging real usage on an unlisted provider) — see
# module docstring. Logged loudly (once per distinct unmapped key) so an operator notices and adds a
# real rate instead of this staying the permanent answer.
_FALLBACK_RATE_USD: tuple[float, float] = (1.00, 5.00)
_warned_unmapped: set[str] = set()

# Business decisions (see module docstring) — single constants, easy to tune without touching the
# calculation logic below.
EUR_PER_ENERGY_UNIT = float(os.getenv("ENERGY_EUR_PER_UNIT", "0.01"))   # 1 Energy = €0.01 (default)
MARGIN_MULTIPLIER = float(os.getenv("ENERGY_MARGIN_MULTIPLIER", "4.0"))  # retail vs raw compute cost


def enabled() -> bool:
    """Energy metering exists for real cloud accounts (ZAELAR_USER_ID set, 2026-08-05). Routes
    through the single-purpose accessor so neither this module nor its callers need to know the
    shape of the gate."""
    from nucleo import cloud_account
    return cloud_account.is_cloud_account()


def _is_local_endpoint(base_url: str) -> bool:
    u = (base_url or "").lower()
    return "11434" in u or "localhost" in u or "127.0.0.1" in u


# Token assumption for a PAID call whose provider reported no usage at all. 2026-08-13: the fallback
# RATE (above) covered "we don't know the price"; nothing covered "we don't know the volume", and that
# second hole was worse — a rate is a number that gets looked up, a missing volume multiplies to
# exactly zero and reports success. Every provider that streams without `stream_options:
# {include_usage: true}`, and every SDK response read for its text only, landed there.
#
# So: same never-silently-free stance as _FALLBACK_RATE_USD, one level up. A call with no usage is
# charged this floor and logged loudly, which is deliberately the WRONG number — it exists to be
# noticed and fixed at the call site (ask the provider for usage), not to be a permanent estimate.
# Marked `estimated` in the report so reconciliation can find every one of them later.
_MISSING_USAGE_FLOOR = (
    int(os.getenv("ENERGY_MISSING_USAGE_IN_TOKENS", "2000")),
    int(os.getenv("ENERGY_MISSING_USAGE_OUT_TOKENS", "500")),
)
_warned_missing_usage: set[str] = set()


def _resolve_tokens(
    base_url: str, model: str | None, prompt_tokens: int | None, completion_tokens: int | None
) -> tuple[int, int, bool]:
    """`(prompt, completion, estimated)`. Both counters absent on a PAID endpoint → the floor, warned
    once per (endpoint, model). A call that reports 0/0 explicitly is NOT this case: zero is an
    answer, `None` is a missing answer, and conflating them is what made this hole invisible."""
    if prompt_tokens is None and completion_tokens is None and not _is_local_endpoint(base_url):
        key = f"{(base_url or '').lower()}::{(model or '').lower()}"
        if key not in _warned_missing_usage:
            _warned_missing_usage.add(key)
            logger.warning(
                f"energy_meter: NO usage reported for base_url={base_url!r} model={model!r} — charging "
                f"the floor {_MISSING_USAGE_FLOOR} tokens so it is not free. FIX THE CALL SITE: ask the "
                f"provider for usage (streaming needs stream_options={{'include_usage': True}})."
            )
        return _MISSING_USAGE_FLOOR[0], _MISSING_USAGE_FLOOR[1], True
    return prompt_tokens or 0, completion_tokens or 0, False


def _rate_for(base_url: str, model: str | None) -> tuple[float, float]:
    """Never returns None — local endpoints are filtered by the caller BEFORE this is reached
    (llm_cost_to_energy). Every real cloud endpoint gets a rate: exact if we have one, a per-model
    AIMLAPI rate if the broker is AIMLAPI, else the fallback (logged once)."""
    u = (base_url or "").lower()
    m = (model or "").lower()
    # EL MODELO MANDA (2026-08-13). Antes esta tabla solo se consultaba si el endpoint era AIMLAPI, y por
    # eso un worker de Grok Build —que no reporta base_url, porque su CLI habla con xAI directamente— caía
    # al fallback y se cobraba a la mitad. El precio es del MODELO; el endpoint solo es dónde se sirve.
    # Se ordena por longitud del patrón para que el más específico gane («grok-4.5» antes que «grok-4»).
    if m:
        for needle in sorted(_MODEL_RATES, key=len, reverse=True):
            if needle in m:
                return _MODEL_RATES[needle]
    for needle, rates in _RATES_PER_1M_TOKENS_USD.items():
        if needle in u:
            return rates
    key = f"{u}::{m}"
    if key not in _warned_unmapped:
        _warned_unmapped.add(key)
        logger.warning(
            f"energy_meter: no rate row for base_url={base_url!r} model={model!r} — charging the "
            f"fallback rate {_FALLBACK_RATE_USD} $/1M tokens. Add a real rate to energy_meter.py."
        )
    return _FALLBACK_RATE_USD


# $ per 1M CACHED-READ input tokens, by model. A cached read is a real billed line and it is NOT
# included in `input_tokens` (Anthropic-shaped usage reports the three counters separately), so ignoring
# it undercharges — badly, because in a long agentic session the same prompt prefix is re-read on every
# turn and cached reads end up SEVERAL TIMES the fresh input. Measured on a real worker run: 211k cached
# reads against 74k fresh input, i.e. 29% of the bill missing.
#
# The grok rate is DERIVED FROM MEASUREMENT, not from a pricing page: two independent calls of very
# different sizes (384 and 62.720 cached tokens) both solve to exactly $0.30/1M against the cost xAI's own
# CLI reports, while the figure blogs quote ($0.50) does not fit either. GLM's is Z.AI's published
# cached-input price. Anything unmapped falls to a fraction of the input rate — the same
# never-silently-free stance as _FALLBACK_RATE_USD, logged once.
_CACHED_READ_RATES_USD: dict[str, float] = {
    "grok-4.5": 0.30,          # medido (ver arriba), no publicado
    "grok-4.6": 0.30,
    "glm-5.2": 0.26,           # precio público de Z.AI para input cacheado
}
_CACHED_READ_FALLBACK_FRACTION = 0.25      # del rate de input, cuando no hay fila propia


def _cached_rate_for(base_url: str, model: str | None, in_rate: float) -> float:
    m = (model or "").lower()
    for needle in sorted(_CACHED_READ_RATES_USD, key=len, reverse=True):
        if needle in m:
            return _CACHED_READ_RATES_USD[needle]
    key = f"cache::{m}"
    if key not in _warned_unmapped:
        _warned_unmapped.add(key)
        logger.warning(
            f"energy_meter: no cached-read rate for model={model!r} — charging "
            f"{_CACHED_READ_FALLBACK_FRACTION:.0%} of the input rate. Measure it and add a real row."
        )
    return in_rate * _CACHED_READ_FALLBACK_FRACTION


def llm_cost_to_energy(
    *, base_url: str, model: str | None = None, prompt_tokens: int | None, completion_tokens: int | None,
    cached_tokens: int | None = None,
) -> float | None:
    """Pure. Returns Energy units for one LLM call, or None only for a local/free endpoint (Ollama —
    11434/localhost/127.0.0.1). Every real cloud endpoint always returns a value (exact rate if known,
    fallback otherwise) — see module docstring for why this changed from the original fail-open design.

    `cached_tokens` = `cache_read_input_tokens` of Anthropic-shaped usage: a SEPARATE counter, not part of
    `prompt_tokens`, and a real billed line (see `_CACHED_READ_RATES_USD`). Optional and defaulting to 0 so
    a caller that has no cache figure behaves exactly as before."""
    if _is_local_endpoint(base_url):
        return None
    in_rate, out_rate = _rate_for(base_url, model)
    pt = prompt_tokens or 0
    ct = completion_tokens or 0
    cached = cached_tokens or 0
    raw_usd = (pt / 1_000_000) * in_rate + (ct / 1_000_000) * out_rate
    if cached:
        raw_usd += (cached / 1_000_000) * _cached_rate_for(base_url, model, in_rate)
    retail_eur = raw_usd * MARGIN_MULTIPLIER  # treats USD≈EUR for simplicity — fine at these magnitudes
    return retail_eur / EUR_PER_ENERGY_UNIT


# $ per 1000 characters synthesized. Source: elevenlabs.io/pricing/api, 2026-07-24 (Flash/Turbo
# v2.5 API pay-as-you-go rate) — RE-VERIFY periodically, provider pricing changes without notice.
_TTS_USD_PER_1K_CHARS = float(os.getenv("ENERGY_TTS_USD_PER_1K_CHARS", "0.05"))

# $ per minute of audio, streaming/real-time. Source: deepgram.com/pricing, 2026-07-24 (Nova-3,
# Pay-As-You-Go tier, monolingual) — RE-VERIFY periodically.
_STT_USD_PER_MIN = float(os.getenv("ENERGY_STT_USD_PER_MIN", "0.0048"))


def tts_cost_to_energy(*, characters: int | None) -> float:
    """Pure. Energy units for one TTS synthesis call. Never None — TTS has one flat rate, no
    per-provider table (only ElevenLabs runs in the cloud profile; kokoro_local is filtered by the
    caller before this is ever invoked, same pattern as the metrics_collected hook in agent.py)."""
    chars = characters or 0
    raw_usd = (chars / 1000.0) * _TTS_USD_PER_1K_CHARS
    retail_eur = raw_usd * MARGIN_MULTIPLIER
    return retail_eur / EUR_PER_ENERGY_UNIT


def stt_cost_to_energy(*, audio_seconds: float | None) -> float:
    """Pure. Energy units for one STT transcription call (audio_duration from STTMetrics)."""
    secs = audio_seconds or 0.0
    raw_usd = (secs / 60.0) * _STT_USD_PER_MIN
    retail_eur = raw_usd * MARGIN_MULTIPLIER
    return retail_eur / EUR_PER_ENERGY_UNIT


# $ per SEARCH REQUEST — this family is priced per call, not per token, so it needs its own table
# rather than a row in the LLM one. Added 2026-08-13: web search had no rate at all, which meant a
# paid search key would have billed at zero the way the FlashBrain did before 2026-08-05.
#
# `""` is the deliberate catch-all (same never-silently-free stance as _FALLBACK_RATE_USD). Free
# providers are NOT in this table and are NOT charged — they are filtered by the caller, because
# "free" is a fact about the provider, not a rate of zero to be looked up. Source: public pricing,
# 2026-08-13 — RE-VERIFY, and note these are entry-tier rates that volume discounts move.
_SEARCH_USD_PER_REQUEST: dict[str, float] = {
    "perplexity": 0.005,     # Sonar, incl. the synthesised answer
    "tavily": 0.008,         # advanced depth (the depth this repo asks for)
    "brave": 0.005,
    "": 0.008,               # unmapped paid provider → the most expensive known, logged once
}
_warned_search = set()


def search_cost_to_energy(*, provider: str) -> float:
    """Pure. Energy units for ONE paid search request. The caller decides what is paid: a free
    provider must never reach here (see `websearch`)."""
    p = (provider or "").lower()
    if p not in _SEARCH_USD_PER_REQUEST and p not in _warned_search:
        _warned_search.add(p)
        logger.warning(
            f"energy_meter: no search rate for provider={provider!r} — charging the catch-all "
            f"{_SEARCH_USD_PER_REQUEST['']} $/request. Add a real rate to energy_meter.py."
        )
    raw_usd = _SEARCH_USD_PER_REQUEST.get(p, _SEARCH_USD_PER_REQUEST[""])
    return (raw_usd * MARGIN_MULTIPLIER) / EUR_PER_ENERGY_UNIT


# --- reporting: fire-and-forget POST to the right ledger, never blocks the turn/worker ---

_USAGE_ENDPOINT_PATH = "/usage"


async def _post_usage(energy: float, kind: str, meta: dict | None = None) -> None:
    await _post_usage_cloud_account(energy, kind, meta)


async def _post_usage_cloud_account(energy: float, kind: str, meta: dict | None = None) -> None:
    """Reports to the control-plane's PERSISTENT per-user Energy ledger (cloud/control-plane's
    POST /usage). The control-plane writes this SAME call into zaelar_user_events too (INI-019
    addenda, "Cambio A") — so `meta` (model/base_url ONLY — never content) doubles as the per-user
    activity timeline the backoffice reads. CONTROL_PLANE_URL/CONTROL_PLANE_SERVICE_TOKEN are
    injected by the provisioner at Machine creation
    (cloud/provisioner/src/machineConfig.js::accountMachineConfig) — guarded-until-configured:
    missing either → no-op, never raises.

    2026-08-09: the response already carries the account's new `balance` (control-plane's own
    /usage handler has always returned it) — this used to be discarded. Reading it here is the WHOLE
    gate: no separate balance-check endpoint was needed, just stop throwing the answer away. A
    depleted balance (nucleo/account_limits.should_close) requests the session close, fire-and-forget
    (nucleo/account_limits.py) — a failed close request never breaks the turn that triggered it."""
    from nucleo import account_limits, cloud_account

    control_plane_url = (os.getenv("CONTROL_PLANE_URL") or "").strip()
    user_id = cloud_account.my_user_id()
    if not control_plane_url or not user_id or energy <= 0:
        return
    service_token = (os.getenv("CONTROL_PLANE_SERVICE_TOKEN") or "").strip()
    headers = {"X-Service-Token": service_token} if service_token else {}
    payload = {"user_id": user_id, "energy": energy, "kind": kind}
    # SESIÓN DE TRABAJO (2026-08-09): el reporte dice a qué sesión pertenece el consumo, para que quien lo reciba
    # pueda agruparlo sin abrir otra vía. Cuesta un dict lookup y no manda NADA de contenido. Los EVENTOS no
    # viajan por aquí ni por ningún sitio: se quedan en esta máquina.
    try:
        from observability import identity as _ident
        payload["session_id"] = _ident.session_id()
    except Exception:
        pass
    if meta:
        payload["meta"] = meta
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(
                control_plane_url.rstrip("/") + _USAGE_ENDPOINT_PATH,
                json=payload,
                headers=headers,
            )
        balance = (resp.json() or {}).get("balance") if resp.status_code < 400 else None
        note_balance(balance)
        if account_limits.should_close(balance):
            account_limits.request_close("balance_depleted")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"energy_meter: cloud-account usage report failed (non-fatal): {e}")


# --- EL SALDO QUE EL OPERADOR VE (2026-08-13) --------------------------------------------------------------
#
# El saldo YA llegaba en la respuesta de cada reporte y solo se usaba para decidir el corte. Aquí se conserva,
# porque un saldo que solo sirve para apagarte es la peor forma de contarlo: el operador se enteró de que se le
# había agotado la energía por un cartel, sin haber visto nunca cuánta le quedaba. Es el mismo criterio que
# [[feedback_visible_state_over_silent_state]] — un estado que puede dejarte tirado tiene que VERSE antes.
#
# `capacity` = de cuánto se partía, para poder dibujar una PILA (cuánto queda de cuánto había) y no un número
# suelto. No se puede preguntar «cuánto compró»: solo se ve el saldo. Pero una recarga es, por definición, un
# saldo que SUBE — así que un salto hacia arriba fija la capacidad nueva y un descenso no la toca.
#
# Vive en `sys_kv`, NUNCA en el estado raíz: `memory.api.compose_state` vuelca cada escalar del estado al prompt
# como «Clave: valor.», así que un saldo ahí viajaría en todos los turnos de voz (misma razón que en
# `nucleo/rehydrate.py`).
_KV_KEY = "energy:balance"
_state: dict = {"balance": None, "capacity": None, "at": 0.0}
_loaded = False


def _load_once() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        from memory import api as memory
        d = memory.kv_get(_KV_KEY)          # kv_get/kv_set ya hacen el JSON: se guarda el dict tal cual
        if isinstance(d, dict):
            _state.update({"balance": d.get("balance"), "capacity": d.get("capacity"),
                           "at": float(d.get("at") or 0.0)})
    except Exception:
        pass


def note_balance(balance) -> None:
    """Registra el saldo que acaba de decir el control-plane. Nunca lanza: es contabilidad de PRESENTACIÓN,
    y un fallo aquí no puede tocar el turno ni el worker que la disparó."""
    try:
        if balance is None:
            return
        b = float(balance)
    except (TypeError, ValueError):
        return
    _load_once()
    prev = _state.get("balance")
    cap = _state.get("capacity")
    # Una RECARGA es un saldo que sube (o el primer saldo que vemos). Gastar no cambia de cuánto se partía.
    if cap is None or prev is None or b > float(prev):
        cap = b
    _state.update({"balance": b, "capacity": cap, "at": time.time()})
    try:
        from memory import api as memory
        import json as _json
        memory.kv_set(_KV_KEY, _json.dumps({"balance": b, "capacity": cap, "at": _state["at"]}))
    except Exception:
        pass
    # EN VIVO: la pila baja mientras el agente trabaja, sin que el frontend pregunte. Un `emit` no bloquea.
    try:
        from voice.observer import emit
        emit("energy", "saldo", extra={"balance": b, "capacity": cap})
    except Exception:
        pass


def snapshot() -> dict:
    """Lo que el frontend necesita para pintar la pila. `known=False` = todavía no hemos visto ningún saldo (la
    cuenta no ha gastado nada desde que arrancó y nadie nos lo ha dicho): la pila se pinta apagada, no a cero —
    «no lo sé» y «se te acabó» no pueden verse igual."""
    _load_once()
    b, cap = _state.get("balance"), _state.get("capacity")
    return {"cloud": enabled(), "known": b is not None, "balance": b, "capacity": cap,
            "at": _state.get("at") or 0.0}


def _reset_for_tests() -> None:
    global _loaded
    _state.update({"balance": None, "capacity": None, "at": 0.0})
    _loaded = False


def _fire_and_forget(energy: float, kind: str, meta: dict | None = None) -> None:
    """Shared tail of every report_*_usage(): schedule the POST without ever blocking or raising
    into the caller. No running loop (e.g. a unit test calling this directly) → drop silently."""
    import asyncio

    # EL ARRIENDO SE DESCUENTA AQUÍ, ANTES y SIN RED (2026-08-13, ADR-0005). Es el mismo gesto que
    # reportar, pero no espera respuesta: el techo local es una resta en proceso. Va delante del
    # `create_task` a propósito — si no hay loop y el POST se descarta, el gasto ya ocurrió igual y el
    # contador tiene que saberlo. Un contador que solo cuenta cuando la red va bien no es un techo.
    try:
        from nucleo import energy_lease
        energy_lease.note_spend(energy)
    except Exception:  # noqa: BLE001
        pass

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    asyncio.create_task(_post_usage(energy, kind, meta))


def report_llm_usage(
    *, base_url: str, model: str | None = None, prompt_tokens: int | None, completion_tokens: int | None
) -> None:
    """Call from the LLM streaming call site's `finally` block, AFTER usage/estimate is resolved.
    Fire-and-forget (asyncio.create_task) — never awaited by the caller, never adds latency to the
    turn. No-op with zero cost if not a metered account (enabled() False) or no running event loop."""
    if not enabled():
        return
    pt, ct, estimated = _resolve_tokens(base_url, model, prompt_tokens, completion_tokens)
    energy = llm_cost_to_energy(base_url=base_url, model=model, prompt_tokens=pt, completion_tokens=ct)
    if energy is None:
        return
    meta = {"model": model, "base_url": base_url}
    if estimated:
        meta["estimated"] = True
    _fire_and_forget(energy, "llm", meta)


def report_worker_usage(
    *, base_url: str, model: str | None = None, prompt_tokens: int | None, completion_tokens: int | None,
    cached_tokens: int | None = None,
) -> None:
    """Call from a Brain Worker session's completion (nucleo/workers/session.py::_finish), AFTER the
    stream-json "result" usage is known. Same rate table and fire-and-forget contract as
    report_llm_usage — a worker call IS an LLM call, just reached via the Claude Code CLI subprocess
    instead of an HTTP client. Deliberately does NOT use the CLI's own `total_cost_usd`: that figure is
    computed by the CLI against OFFICIAL Anthropic pricing, which is meaningless once the call was
    relayed to a flat-rate subscription tier (Z.AI/Moonshot, see nucleo/workers/providers.py) — pricing
    by our own per-model table keeps worker Energy consistent with every other metered call."""
    if not enabled():
        return
    pt, ct, estimated = _resolve_tokens(base_url, model, prompt_tokens, completion_tokens)
    energy = llm_cost_to_energy(
        base_url=base_url, model=model, prompt_tokens=pt, completion_tokens=ct, cached_tokens=cached_tokens,
    )
    if energy is None:
        return
    meta = {"model": model, "base_url": base_url}
    if estimated:
        meta["estimated"] = True
    _fire_and_forget(energy, "worker", meta)


def report_tts_usage(*, characters: int | None) -> None:
    """Call from the TTSMetrics branch of agent.py's metrics_collected hook, AFTER the caller has
    already excluded local backends (kokoro_local — free, not metered). Same no-op/fire-and-forget
    contract as report_llm_usage."""
    if not enabled():
        return
    energy = tts_cost_to_energy(characters=characters)
    if energy <= 0:
        return
    _fire_and_forget(energy, "tts")


def report_stt_usage(*, audio_seconds: float | None) -> None:
    """Call from the STTMetrics branch of agent.py's metrics_collected hook, AFTER the caller has
    already excluded local backends (whisper_local — free, not metered). Same no-op/fire-and-forget
    contract as report_llm_usage."""
    if not enabled():
        return
    energy = stt_cost_to_energy(audio_seconds=audio_seconds)
    if energy <= 0:
        return
    _fire_and_forget(energy, "stt")


def report_search_usage(*, provider: str) -> None:
    """Call from a PAID web-search provider's call site, after it answered. Same no-op/fire-and-forget
    contract as report_llm_usage. The caller must not invoke this for a free provider (Google via our
    own Chromium, DuckDuckGo): what is free is a property of the provider, and passing it through a
    rate table would turn 'free' into a number somebody can get wrong later."""
    if not enabled():
        return
    _fire_and_forget(search_cost_to_energy(provider=provider), "search", {"provider": provider})
