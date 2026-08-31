"""nucleo/flash/fast_client.py — client for the FlashBrain's FAST non-reasoning model (V2-004 · T60).

Own port of `brains/duo/fast_client.py` (which dies with Hermes in V2-009), with the KEY difference of
the v2 brain:

  - **Model PER INVOCATION** (hard project rule): model/base_url/api_key/provider are passed on EACH
    `stream()` inside a `ModelSpec`, NEVER read from a global model env — so two concurrent sessions
    can use different models without stepping on each other. `spec_from_config()` builds the default spec from `config/v2`
    (managed by the UI), but the caller is free to pass another.
  - **Non-reasoning**: thinking is always OFF. A reasoner does not close the turn in time → voice goes silent.
  - OpenAI-compatible interface with **real tool-calling** (escalation and control use function-calling, not
    keyword lists — language-agnostic). Streaming of `delta.content` + accumulation of
    `delta.tool_calls`, with `on_tool_call(name, args)` fired once per complete call.
  - **Degradation**: `stream()` propagates the transport/provider error; the voice provider (`nucleo.py`) catches
    it and replies with a fallback phrase — it NEVER stays silent or speaks the raw error.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator

from loguru import logger

# Browser UA: AIMLAPI is behind Cloudflare and intermittently 403s the OpenAI SDK's default User-Agent (403/1010,
# observed in production). It is spoofed ONLY on the AIMLAPI endpoint (no effect on Ollama/others).
_BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
# The turn's output ceiling. It was 200, and 200 does not FIT the most important tool call in the system:
# `escalate_to_slowbrain` writes ~1000-1400 characters of JSON on its own, and the same budget has to also
# cover the sentence zaelar says out loud. The provider cut the stream with `finish_reason="length"`, the
# arguments arrived as half a JSON object, and the action was dropped — 67 times across 27 measured runs, 48 of
# them escalations that therefore never reached a Brain Worker (V2-171).
#
# Raising it costs NOTHING on an ordinary turn, and that was measured before changing it rather than assumed —
# a cap is a ceiling, not a target, so the model still stops when it is done (deepseek-v4-pro, 2026-08-20,
# 3 runs each, same short conversational turn):
#
#     max_tokens=200   TTFT 0.99s   total 1.45s   55 chars
#     max_tokens=1200  TTFT 0.91s   total 1.28s   49 chars
#
# So the old value protected no latency invariant that can be measured; it only truncated the turns that were
# doing the most work. 1200 fits a full escalation with room for the spoken sentence.
_DEFAULT_MAX_TOKENS = int(os.getenv("FAST_MAX_TOKENS", "1200"))

# Retry on TRANSIENTS (2026-07-25): AIMLAPI is behind Cloudflare and intermittently returns `Connection error`/403/5xx.
# A SINGLE blip during the connection phase must NOT kill the turn (real symptom: the operator chat was left without
# a response or with "Uf, se me ha ido"). Retry ONLY the connection phase (before the stream's first token) →
# safe (nothing already sent is re-emitted). Configurable `FAST_CONNECT_RETRIES` (default: 2 retries).
_CONNECT_RETRIES = int(os.getenv("FAST_CONNECT_RETRIES", "2"))
_RETRY_BACKOFF_S = float(os.getenv("FAST_RETRY_BACKOFF_S", "0.4"))


# Actions the system threw away, kept just long enough to be said in the NEXT turn. Same remedy as
# `widgets/navegador/tasks.recently_finished()` (V2-150) and `dispatch._EXPIRED_CONFIRM` (V2-190): a fact that
# only exists for one turn is a fact the conversation loses.
_RECENT_DROPS: list[dict] = []
_DROP_MEMORY_S = 180.0     # the immediate conversation, no more: an action dropped ten minutes ago is history


def recent_drops(now: float | None = None) -> list[dict]:
    """Actions dropped in the last few minutes — for the live state, so the next turn can say so."""
    now = time.time() if now is None else now
    return [d for d in _RECENT_DROPS if now - float(d.get("at") or 0) <= _DROP_MEMORY_S]


def clear_drops() -> None:
    """Called once the fact has been said, so it is not repeated forever."""
    _RECENT_DROPS.clear()


def _drop_tool_call(metrics: dict, name: str, raw_args: str) -> None:
    """An action the model decided to take and the system could not read. Record it as a FACT.

    It used to be a bare `continue` under a `logger.warning`, and that is why V2-171 was invisible for three
    days: the user was told «te pongo con ello», nothing ran, and neither the operator, nor the judge, nor the
    Master had any way to know. From a conversation log it reads as the assistant lying. It did not lie — its
    action was thrown away.

    Raising the cap (see `_DEFAULT_MAX_TOKENS`) removes the cause that was measured, but not the class: any
    model can emit malformed JSON. What this guarantees is that when it happens the loss is KNOWN, which is
    the whole difference between a bug and a mystery. Best-effort throughout — reporting a dropped action must
    never be able to drop the turn as well.
    """
    reason = "cortada por el tope de tokens" if str(metrics.get("finish_reason") or "") == "length" \
        else "argumentos ilegibles"
    logger.warning(f"tool call {name} DESCARTADA ({reason}): {(raw_args or '')[:200]!r}")
    dropped = metrics.setdefault("dropped_tool_calls", [])
    dropped.append({"name": name, "reason": reason, "chars": len(raw_args or "")})
    # V2-176 frente 2: and the fact has to OUTLIVE this turn. V2-171 recorded the drop in the turn's own metrics and in
    # observability, which the operator can inspect afterwards — but the NEXT turn saw nothing, so the
    # conversation carried on as if the action had gone out. The sentence «te pongo con ello» was already
    # spoken by then; what can still be fixed is the turn after it.
    _RECENT_DROPS.append({"name": name, "reason": reason, "at": time.time()})
    del _RECENT_DROPS[:-4]
    try:
        from voice.observer import emit
        emit("tool_dropped", "⚠️ acción descartada",
             text=f"{name}: {reason}", extra={"tool": name, "reason": reason,
                                              "finish_reason": metrics.get("finish_reason") or ""})
    except Exception:
        pass


def _is_transient(e: Exception) -> bool:
    """Is the error a transient network/provider blip (worth retrying), and NOT a request error (4xx for
    authentication/quota/input, which retrying cannot fix)?"""
    name = type(e).__name__.lower()
    if any(k in name for k in ("connection", "timeout", "apiconnection", "apitimeout", "internalserver")):
        return True
    s = str(e).lower()
    if any(k in s for k in ("connection error", "timed out", "timeout", "temporarily", "bad gateway",
                            "service unavailable", "502", "503", "504", "cloudflare", "reset by peer")):
        return True
    status = getattr(e, "status_code", None) or getattr(e, "status", None)
    return status in (408, 429, 500, 502, 503, 504)


async def _raise_with_body(resp) -> None:
    """`resp.raise_for_status()`, but with the response BODY included in the exception message. Without
    this, a Z.AI 429 arrives as httpx's generic message («429 Too Many Requests», with no further detail), and the
    downstream failure classifier (`nucleo.flash.provider_chain.classify_failure`, and its sibling in
    `nucleo.workers.providers`) cannot distinguish «WEEKLY quota exhausted, reset Thursday» (the model must be replaced) from
    a temporary rate limit (retried automatically) — both produce the SAME bare 429. No-op if the response is OK.

    THIS IS A COROUTINE: it must be called with AWAIT. Without await it throws absolutely nothing —Python only creates the
    coroutine and discards it—so a 429/500 was treated as successful and the code continued with `resp.json()` on an error
    body, turning a clear provider failure into a confusing parse error later. This happened right here, in
    `_complete_zai` (2026-08-09): it was only noticed because Python warned («coroutine never awaited»)."""
    import httpx
    if resp.status_code < 400:
        return
    try:
        await resp.aread()          # no-op if already buffered (normal Response); essential for streaming
        body = (resp.text or "")[:400]
    except Exception:
        body = ""
    err = httpx.HTTPStatusError(f"{resp.status_code} {resp.reason_phrase}" + (f" — {body}" if body else ""),
                                request=resp.request, response=resp)
    err.status_code = resp.status_code   # let `_is_transient` detect it by status_code too, not only by text
    raise err


def _keepalive_expiry() -> float:
    """Seconds for which the HTTP pool keeps an idle connection ALIVE (PHASE 1 cold-start). httpx closes it by default
    after ~5s → prewarming does not reach the first turn. We raise it substantially (default: 30 min). Configurable via `FAST_HTTP_KEEPALIVE_S`.
    The SAME value feeds the `cold_estimate` heuristic (gap > keepalive ⇒ connection probably cold)."""
    try:
        return float(os.getenv("FAST_HTTP_KEEPALIVE_S", "1800"))
    except Exception:
        return 1800.0


def _http_client():
    """httpx client with LONG keepalive + pool, so the prewarmed TLS connection survives the first turn and
    the gaps between turns (PHASE 1). Best-effort: if httpx does not support the signature, return None → AsyncOpenAI uses its default."""
    try:
        import httpx
        ka = _keepalive_expiry()
        limits = httpx.Limits(max_keepalive_connections=8, max_connections=16, keepalive_expiry=ka)
        return httpx.AsyncClient(limits=limits, timeout=httpx.Timeout(60.0, connect=10.0))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"http_client keepalive setup skipped (usando default httpx): {e}")
        return None



# `ModelSpec` moved to model_spec.py (2026-08-17 modularization pass) — re-exported here since many callers
# import it by name from this module (`from nucleo.flash.fast_client import ModelSpec`, etc.).
from nucleo.flash.model_spec import (  # noqa: F401 — re-export
    ModelSpec, spec_from_config, available, _FALLBACK_MODEL,
)

# Chars por token. El 4.0 de siempre es la regla del pulgar del INGLÉS; medido contra el registro real (114 turnos
# con `usage` del proveedor Y los chars de sus dos bloques) nuestro input va a **3,36 chars/token** — castellano con
# tildes, más el JSON del catálogo de tools. El sesgo era sistemático, no ruido: el ratio estimado/real cabía entre
# 0,823 y 0,857 en las 114 muestras.
#
# Importa porque este estimado NO es solo observabilidad: es lo que FACTURA un turno cancelado, donde el `usage` del
# proveedor nunca llega (viaja en el último chunk). Con el 4.0 se cobraba **un 16% de menos** en el 70% de los turnos
# de una sesión real de dictado. Va contra la política fijada el 2026-08-13 al cerrar los cuatro agujeros de Energy:
# *«perder dinero por sub-cobrar es peor que sobre-cobrar un poco»*.
#
# Se deja en 3,3 y no en 3,36 a propósito: redondear hacia ABAJO el divisor estima de MÁS (~2%), que es el lado
# seguro y el mismo criterio que la tarifa de seguridad del medidor.
_CHARS_PER_TOKEN = 3.3


def est_tokens(chars: int) -> int:
    """Cheap token estimate from the number of chars. Two uses, and the second is what determines the constant:

    1. **Observability** — distinguish a «100-token prompt» from a «50k prompt», the axis the operator needs to
       determine whether latency comes from the MODEL or the prompt SIZE. Here the divisor hardly matters.
    2. **The bill for a CANCELLED turn** — the provider's real `usage` arrives in the stream's LAST chunk, so
       a turn cut off by barge-in never receives it and this estimate is all we have. Here the divisor is money
       (see `_CHARS_PER_TOKEN`).

    If the provider returns `usage`, it always takes precedence (see `stream`).
    """
    return int(round((chars or 0) / _CHARS_PER_TOKEN))


class _AnthropicSSE:
    """PURE state machine for the Anthropic Messages SSE stream (the protocol spoken by direct Z.AI). Deliberately
    separate from HTTP transport → testable with synthetic `data:` objects (see tests). `feed(obj)` receives ONE
    JSON object from a `data:` line and returns a list of events: `("text", str)` for each `text_delta`, and
    `("tool", name, input_dict)` when a `tool_use` block closes (accumulating `input_json_delta.partial_json`)."""

    def __init__(self) -> None:
        self._blocks: dict[int, dict] = {}   # index → {"type","name","json"}

    def feed(self, obj: dict) -> list[tuple]:
        out: list[tuple] = []
        t = obj.get("type")
        if t == "content_block_start":
            cb = obj.get("content_block") or {}
            self._blocks[obj.get("index")] = {"type": cb.get("type"), "name": cb.get("name", ""), "json": ""}
        elif t == "content_block_delta":
            d = obj.get("delta") or {}
            dt = d.get("type")
            if dt == "text_delta" and d.get("text"):
                out.append(("text", d["text"]))
            elif dt == "input_json_delta":
                b = self._blocks.get(obj.get("index"))
                if b is not None:
                    b["json"] += d.get("partial_json", "") or ""
        elif t == "content_block_stop":
            b = self._blocks.get(obj.get("index"))
            if b and b.get("type") == "tool_use" and b.get("name"):
                try:
                    inp = json.loads(b["json"] or "{}")
                except Exception:
                    inp = {}
                out.append(("tool", b["name"], inp))
        return out


class FastClient:
    """Streaming client for the fast model. STATELESS with respect to the model: each `stream()` receives its `ModelSpec`.
    Underlying AsyncOpenAI clients are cached by (base_url, api_key, ua) to reuse connections."""

    # timestamp of the LAST call per client key → cold/warm heuristic (gap > keepalive ⇒ connection probably
    # cold, TLS is renegotiated). Cold-start observability (PHASE 1). Class-level: shared by all instances.
    _last_call_at: dict[tuple, float] = {}

    _clients: dict[tuple, Any] = {}

    def _client_key(self, spec: ModelSpec) -> tuple:
        # EGRESS (T303). Where the deployment declares mediated egress, `llm_egress` decides the destination
        # and credential, not the spec: the spec still says WHICH model is wanted, but no longer says
        # which key pays for it. Without mediated egress this returns exactly what it did before, so the
        # self-host path does not change by a single byte.
        from nucleo import llm_egress
        raw_base = spec.resolved_base_url()
        base, key, extra = llm_egress.route(raw_base, spec.resolved_api_key())
        if not key:
            raise RuntimeError(f"sin credencial para el modelo rápido ({spec.model} @ {base})")
        # The browser User-Agent is for Cloudflare in front of AIMLAPI. With mediated egress the other
        # end talks to AIMLAPI, so it is not needed here.
        ua = _BROWSER_UA if (spec._is_aimlapi() and not extra) else ""
        return (base, key, ua, tuple(sorted(extra.items())))

    def _client_for(self, spec: ModelSpec):
        # lazy import: a missing key must not break package/session-setup import.
        from openai import AsyncOpenAI

        ck = self._client_key(spec)
        base, _key, ua, extra = ck
        cli = FastClient._clients.get(ck)
        if cli is None:
            headers = dict(extra)
            if ua:
                headers["User-Agent"] = ua
            headers = headers or None
            # PHASE 1 (cold-start): the HTTP client keeps the TLS connection ALIVE much longer than httpx's default
            # (~5s). Without this, prewarming heats the connection at startup but it EXPIRES before the first turn →
            # TLS+handshake is redone = the first cold turn takes ~3.8s. With long keepalive, the prewarmed connection
            # survives until the first turn and BETWEEN turns → the hot model (~1.2s) is always perceived.
            okw = dict(api_key=_key, base_url=base, default_headers=headers)
            _hc = _http_client()
            if _hc is not None:
                okw["http_client"] = _hc
            cli = AsyncOpenAI(**okw)
            FastClient._clients[ck] = cli
        return cli

    async def complete(
        self,
        messages: list[dict],
        *,
        spec: ModelSpec | None = None,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        on_tool_call=None,
        no_thinking: bool = False,
    ) -> str:
        """NON-streaming call (returns the complete text). Same client/keys/spec as `stream()` — the SAME
        engine, only without chunking the output. Used by the cluster channel (V2-069): off-voice needs no streaming, and a
        REASONING tier (GLM-5.2 via AIMLAPI) emits NO deltas until it finishes thinking → with `stream=True` the call
        appears to hang (measured: >115s vs 3.4s without streaming). Raises the provider error just like `stream`.

        Si se pasan `tools` (function-calling OpenAI-compatible, V2-076), se ofrecen con `tool_choice='auto'` y, al
        volver, `on_tool_call(name, args_dict)` se dispara una vez por llamada del modelo (best-effort: una con JSON
        inválido se salta, nunca lanza). Es el mismo mecanismo que `stream()` pero sin trocear — para que el turno de
        cluster (que DEBE ir no-streaming por el reasoner) pueda REUSAR el catálogo del FlashBrain. Sin `tools` el
        comportamiento es byte-idéntico a antes (cero regresión)."""
        spec = spec or spec_from_config()
        if spec._is_zai():
            return await self._complete_zai(messages, spec, max_tokens, tools=tools, on_tool_call=on_tool_call,
                                            no_thinking=no_thinking)
        extra_body: dict[str, Any] = {}
        r = spec.reasoning_effort()
        if r:
            extra_body["reasoning_effort"] = r
        if no_thinking:
            # The caller wants the ANSWER, not the deliberation — see `no_thinking` in the docstring. Same field
            # and same caveat as the voice path below: the broker accepts it and reasons anyway, the direct
            # endpoint obeys it.
            extra_body.setdefault("thinking", {"type": "disabled"})
        if spec.is_local():
            extra_body["keep_alive"] = "30m"
        call_kwargs: dict[str, Any] = dict(
            model=spec.model,
            messages=messages,
            max_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
            stream=False,
        )
        if extra_body:
            call_kwargs["extra_body"] = extra_body
        if tools:
            call_kwargs["tools"] = tools
            call_kwargs["tool_choice"] = "auto"
        # Reintento en transitorios (no-streaming → reintentar la llamada entera es seguro).
        _attempt = 0
        while True:
            try:
                resp = await self._client_for(spec).chat.completions.create(**call_kwargs)
                break
            except Exception as e:  # noqa: BLE001
                if _attempt >= _CONNECT_RETRIES or not _is_transient(e):
                    raise
                _attempt += 1
                logger.warning(f"fast_client.complete: blip transitorio ({type(e).__name__}), "
                               f"reintento {_attempt}/{_CONNECT_RETRIES}")
                await asyncio.sleep(_RETRY_BACKOFF_S * _attempt)
        try:
            msg = resp.choices[0].message
        except (IndexError, AttributeError):
            return ""
        if tools and on_tool_call:                       # function-calling no-streaming (V2-076)
            import json as _json
            for tc in (getattr(msg, "tool_calls", None) or []):
                try:
                    fn = tc.function
                    args = _json.loads(fn.arguments or "{}") if isinstance(fn.arguments, str) else (fn.arguments or {})
                    on_tool_call(fn.name, args if isinstance(args, dict) else {})
                except Exception:                        # una tool-call malformada se salta, nunca tira el turno
                    continue
        return (getattr(msg, "content", None) or "").strip()

    async def _complete_zai(self, messages: list[dict], spec: ModelSpec, max_tokens: int | None, *,
                            tools: list[dict] | None = None, on_tool_call=None,
                            no_thinking: bool = False) -> str:
        """Z.AI directo (V2-069 cost-fix, 2026-07-26): su endpoint Anthropic-compatible (`/v1/messages`, la cuenta
        'coding plan') habla un wire format DISTINTO del resto de `FastClient` (OpenAI chat/completions) — de ahí
        un método aparte en vez de forzarlo por `AsyncOpenAI`. Antes el canal de cluster pagaba GLM-5.2 vía AIMLAPI
        (proxy con margen) aunque el operador ya tenía cuenta Z.AI directa; el propio `/chat/completions`
        OpenAI-compatible de Z.AI usa OTRO saldo (pay-as-you-go, distinto del plan de coding) — probado en vivo:
        ese devuelve 429 sin fondos mientras `/v1/messages` sí responde. `tools` (OpenAI-compatible, V2-076) se
        traduce al formato de tool-use de Anthropic — necesario para evaluar de verdad la fiabilidad de
        tool-calling de un candidato (§v2077 A/B), no solo el canal de cluster que nunca las ofrece."""
        import httpx
        system = "\n\n".join(m.get("content", "") for m in messages if m.get("role") == "system")
        turns = [{"role": m["role"], "content": m["content"]} for m in messages if m.get("role") in ("user", "assistant")]
        if not turns:
            turns = [{"role": "user", "content": system}]
            system = ""
        payload: dict[str, Any] = {"model": spec.model, "max_tokens": max_tokens or _DEFAULT_MAX_TOKENS, "messages": turns}
        if no_thinking:
            # GLM thinks by default here, and the thinking block is charged against `max_tokens` — so a caller
            # with a normal budget gets a TRUNCATED answer, or an empty one, with a 200 and no error anywhere.
            # Measured 2026-08-27 on the research composer's real prompt: thinking ON needed 8.000 tokens and
            # 67,7 s to emit a parseable brief; thinking OFF answered the same brief in 22,3 s inside the
            # ordinary 1.600 budget. Whoever only wants the answer must be able to say so.
            payload["thinking"] = {"type": "disabled"}
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [
                {"name": t["function"]["name"], "description": t["function"].get("description", ""),
                 "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}}}
                for t in tools if t.get("type") == "function" and t.get("function", {}).get("name")
            ]
            payload["tool_choice"] = {"type": "auto"}
        headers = {"x-api-key": spec.resolved_api_key(), "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        url = spec.resolved_base_url().rstrip("/") + "/v1/messages"
        _attempt = 0
        while True:
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    await _raise_with_body(resp)      # sin await no lanza NADA: ver el aviso de abajo
                break
            except Exception as e:  # noqa: BLE001
                if _attempt >= _CONNECT_RETRIES or not _is_transient(e):
                    raise
                _attempt += 1
                logger.warning(f"fast_client._complete_zai: blip transitorio ({type(e).__name__}), "
                               f"reintento {_attempt}/{_CONNECT_RETRIES}")
                await asyncio.sleep(_RETRY_BACKOFF_S * _attempt)
        data = resp.json()
        parts = data.get("content") or []
        if tools and on_tool_call:
            for p in parts:
                if p.get("type") == "tool_use" and p.get("name"):
                    try:
                        on_tool_call(p["name"], p.get("input") or {})
                    except Exception:                    # una tool-call malformada se salta, nunca tira el turno
                        continue
        return "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()

    async def _stream_zai(self, messages: list[dict], spec: ModelSpec, *, max_tokens: int | None = None,
                          tools: list[dict] | None = None, on_tool_call=None,
                          metrics: dict | None = None) -> AsyncIterator[str]:
        """STREAMING para Z.AI directo (V2-077 A/B, 2026-07-31): el endpoint Anthropic-compatible (`/v1/messages`
        con `stream:true`) emite SSE en el wire format de Anthropic Messages (`content_block_delta` con
        `text_delta`), DISTINTO del `chat/completions` de OpenAI que usa `stream()`. Hasta hoy Z.AI solo tenía
        `complete()` (no-streaming) → un GLM-4.5-Air como FlashBrain de VOZ no era evaluable (la voz necesita
        deltas para TTS incremental). Esto lo hace posible; queda LATENTE hasta configurar FAST=Z.AI (el path de
        voz vivo va por otro endpoint). El parser de SSE es `_AnthropicSSE` (puro, con test unitario). NOTA: sin
        verificar end-to-end contra un GLM-4.5-Air con fondos (pay-as-you-go da 429 sin saldo) — pendiente A/B."""
        import httpx
        system = "\n\n".join(m.get("content", "") for m in messages if m.get("role") == "system")
        turns = [{"role": m["role"], "content": m["content"]} for m in messages if m.get("role") in ("user", "assistant")]
        if not turns:
            turns = [{"role": "user", "content": system}]
            system = ""
        payload: dict[str, Any] = {"model": spec.model, "max_tokens": max_tokens or _DEFAULT_MAX_TOKENS,
                                   "messages": turns, "stream": True}
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [
                {"name": t["function"]["name"], "description": t["function"].get("description", ""),
                 "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}}}
                for t in tools if t.get("type") == "function" and t.get("function", {}).get("name")
            ]
            payload["tool_choice"] = {"type": "auto"}
        headers = {"x-api-key": spec.resolved_api_key(), "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        url = spec.resolved_base_url().rstrip("/") + "/v1/messages"
        m = metrics if metrics is not None else {}
        m.update({"model": spec.model, "provider": spec.provider,
                  "prompt_chars": sum(len(str(x.get("content") or "")) for x in messages)})
        parser = _AnthropicSSE()
        _completion_chars = 0
        # Reintento SOLO de la fase de conexión (aún sin emitir tokens), como el path OpenAI de `stream()`.
        _attempt = 0
        while True:
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                    async with client.stream("POST", url, json=payload, headers=headers) as resp:
                        await _raise_with_body(resp)
                        async for line in resp.aiter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            raw = line[5:].strip()
                            if not raw or raw == "[DONE]":
                                continue
                            try:
                                obj = json.loads(raw)
                            except Exception:                # una línea SSE malformada no tira el turno
                                continue
                            for ev in parser.feed(obj):
                                if ev[0] == "text":
                                    _completion_chars += len(ev[1])
                                    yield ev[1]
                                elif ev[0] == "tool" and on_tool_call:
                                    try:
                                        on_tool_call(ev[1], ev[2])
                                    except Exception:        # tool-call malformada se salta, nunca tira el turno
                                        continue
                return
            except Exception as e:  # noqa: BLE001
                if _completion_chars or _attempt >= _CONNECT_RETRIES or not _is_transient(e):
                    raise                                    # ya emitimos, o no es transitorio → no reintentar
                _attempt += 1
                logger.warning(f"fast_client._stream_zai: blip transitorio al conectar ({type(e).__name__}), "
                               f"reintento {_attempt}/{_CONNECT_RETRIES}")
                await asyncio.sleep(_RETRY_BACKOFF_S * _attempt)
            finally:
                try:
                    m["completion_chars"] = _completion_chars
                    m["completion_tokens_est"] = est_tokens(_completion_chars)
                except Exception:
                    pass

    async def stream(
        self,
        messages: list[dict],
        *,
        spec: ModelSpec | None = None,
        tools: list[dict] | None = None,
        on_tool_call=None,
        max_tokens: int | None = None,
        metrics: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Thin wrapper over `_stream_inner()` that tracks "a real model request is in flight" for
        `nucleo.runstate`'s deferred stop (V2-092 addenda, 2026-08-15): the ⏻ switch must never cut a request
        mid network-call, but the wait is NOT a timer — it is this counter reaching zero, which only ever
        happens when a real stream actually ends (success, provider error, or cancellation). One choke point
        for both branches of `_stream_inner` (the Z.AI SSE path and the OpenAI-compatible path), since a
        `try/finally` around a delegating `async for` covers whatever the inner generator does, wherever inside
        it something raises. See `_stream_inner` for the unchanged streaming logic."""
        from nucleo import runstate

        runstate.enter_inflight()
        try:
            async for chunk in self._stream_inner(
                messages, spec=spec, tools=tools, on_tool_call=on_tool_call,
                max_tokens=max_tokens, metrics=metrics, **kwargs,
            ):
                yield chunk
        finally:
            await runstate.exit_inflight()

    async def _stream_inner(
        self,
        messages: list[dict],
        *,
        spec: ModelSpec | None = None,
        tools: list[dict] | None = None,
        on_tool_call=None,
        max_tokens: int | None = None,
        metrics: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Async generator: emits each chunk's text as it arrives (to push it to TTS immediately). Raises
        on transport/provider error (the caller speaks a clean fallback — never the raw error).

        If `tools` (OpenAI-compatible functions) are passed, they are offered with `tool_choice='auto'`; the
        `delta.tool_calls` are accumulated by index and, when the stream ends, `on_tool_call(name, args_dict)` is
        fired once per complete call (best-effort: one with invalid JSON is skipped and never raises)."""
        spec = spec or spec_from_config()
        # Z.AI directo habla Anthropic Messages SSE (no OpenAI chat/completions) → ruta aparte (paridad con
        # `complete()`, que ya bifurca a `_complete_zai`). Latente hasta configurar FAST=Z.AI.
        if spec._is_zai():
            async for _t in self._stream_zai(messages, spec, max_tokens=max_tokens, tools=tools,
                                             on_tool_call=on_tool_call, metrics=metrics):
                yield _t
            return
        extra_body: dict[str, Any] = {}
        r = spec.reasoning_effort()
        if r:
            extra_body["reasoning_effort"] = r
        if "deepseek" in (spec.model or "").lower():
            # VOZ = NO-RAZONADOR (invariante duro). DeepSeek V4 Flash PIENSA por defecto → en el A/B (2026-07-31)
            # el modo thinking sobre-actuaba (abrió un widget en un turno de contradicción) y bajaba el routing
            # (4/5→3/5 intel); el non-thinking iguala al titular anterior en inteligencia (5/5) con MENOS TTFT. Forzamos
            # non-thinking en el path rápido — campo `thinking` (api-docs.deepseek.com, OpenAI/Anthropic-compat).
            #
            # ⚠️ **Este parámetro se manda igual por los dos endpoints, pero solo UNO lo OBEDECE.** Medido el
            # 2026-08-14 con el prompt real de voz (13.488 chars, 23 tools), 6 turnos por brazo:
            #
            #   AIMLAPI `thinking:disabled` → TTFT p50 4,24 s · max 14,71 s · **2.138 tokens de razonamiento**
            #   DIRECTO `thinking:disabled` → TTFT p50 1,01 s · max  1,30 s · **0**
            #
            # O sea que el broker acepta el campo y razona de todas formas (ya se sospechaba el 2026-08-02 por el
            # tiempo: «lo reduce, no lo apaga»; ahora se LEE en `usage.completion_tokens_details.reasoning_tokens`,
            # que es la prueba que entonces no teníamos). El titular de voz es por eso `api.deepseek.com`.
            extra_body.setdefault("thinking", {"type": "disabled"})
        if spec.is_local():
            # Mantén el modelo local caliente durante toda la sesión (evita recargas de ~60s tras un hueco).
            extra_body["keep_alive"] = "30m"
        call_kwargs = dict(
            model=spec.model,
            messages=messages,
            max_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
            stream=True,
        )
        if extra_body:
            call_kwargs["extra_body"] = extra_body
        if tools:
            call_kwargs["tools"] = tools
            call_kwargs["tool_choice"] = "auto"
        call_kwargs.update(kwargs)

        # ── TOTALIZADORES DE TAMAÑO (observabilidad, premisa del operador) ──────────────────────────────────
        # Chars EXACTOS del input (mensajes + esquemas de tools) + tokens ESTIMADOS. Distingue «lento por el
        # modelo» de «lento por prompt gigante». Todo en `metrics` (best-effort; nunca rompe el turno).
        m = metrics if metrics is not None else {}
        try:
            import json as _json
            prompt_chars = sum(len(str(msg.get("content") or "")) for msg in messages)
            sys_chars = sum(len(str(msg.get("content") or "")) for msg in messages if msg.get("role") == "system")
            tools_chars = len(_json.dumps(tools)) if tools else 0
            ck = self._client_key(spec)
            now = time.time()
            last = FastClient._last_call_at.get(ck)
            gap_s = (now - last) if last else None
            # keepalive del pool (FASE 1); si el gap lo supera, la conexión estaba probablemente FRÍA (TLS de nuevo).
            _ka = _keepalive_expiry()
            m.update({
                "model": spec.model, "provider": spec.provider,
                "prompt_chars": prompt_chars, "system_chars": sys_chars,
                "n_msgs": len(messages), "n_tools": len(tools) if tools else 0, "tools_chars": tools_chars,
                "prompt_tokens_est": est_tokens(prompt_chars + tools_chars),
                "gap_since_last_s": round(gap_s, 1) if gap_s is not None else None,
                "cold_estimate": (gap_s is None) or (gap_s > _ka),
            })
            FastClient._last_call_at[ck] = now
        except Exception:
            pass

        # Reintento SOLO de la fase de conexión (aún no se ha emitido ningún token) → seguro ante blips transitorios.
        _attempt = 0
        while True:
            try:
                stream = await self._client_for(spec).chat.completions.create(**call_kwargs)
                break
            except Exception as e:  # noqa: BLE001
                if _attempt >= _CONNECT_RETRIES or not _is_transient(e):
                    raise
                _attempt += 1
                logger.warning(f"fast_client: blip transitorio al conectar ({type(e).__name__}), "
                               f"reintento {_attempt}/{_CONNECT_RETRIES}")
                await asyncio.sleep(_RETRY_BACKOFF_S * _attempt)
        calls: dict[int, dict] = {}
        _completion_chars = 0
        _seen_output = False     # ¿ha contestado ya el proveedor? (→ retirar el fallo registrado, ver abajo)
        _usage = None
        _t_start = time.time()
        try:
            # try/finally (no "recorre y luego dispara"): el consumidor puede `return` desde DENTRO de su propio
            # `async for` (p. ej. deriva de idioma) → cierra este generador con GeneratorExit a mitad. Sin el
            # finally, una tool call ya acumulada se perdería en silencio (bug real corregido en duo 2026-07-08).
            async for chunk in stream:
                # `usage` REAL si el proveedor lo incluye en algún chunk (muchos lo mandan en el último). No lo
                # PEDIMOS con stream_options (riesgo de 400 en proxies que no lo soportan) — lo leemos si viene.
                _u = getattr(chunk, "usage", None)
                if _u is not None:
                    _usage = _u
                try:
                    delta = chunk.choices[0].delta
                except (IndexError, AttributeError):
                    continue
                # WHY the stream ended, which nothing used to read. That is what turned a truncated tool call
                # into a mystery: a clean finish and a hard cut looked identical from here, so the only trace
                # left of a dropped action was a `logger.warning` in the process log. One line, and the failure
                # is visible for good — in the metrics of every turn, not just when someone greps.
                _fr = getattr(chunk.choices[0], "finish_reason", None)
                if _fr:
                    m["finish_reason"] = str(_fr)
                # LATIDO DEL STREAM (2026-08-12) — el dato que faltaba, y costó turnos de verdad. Este generador solo
                # YIELDEA cuando el chunk trae TEXTO: los chunks de una tool-call (que llegan con `content` vacío y
                # los argumentos goteando en `tool_calls`) se consumen aquí dentro y no salen. Para quien nos
                # recorre, un turno cuya respuesta es una ACCIÓN —«muéstrame los resultados», «cierra eso»— es
                # indistinguible de un modelo colgado. El plazo de silencio del turno mataba esos turnos SANOS: el
                # 2026-08-12 a las 13:49/13:50 se cortaron tres seguidos justo cuando el operador pedía ver los
                # resultados, con `ttft=1.5s` (el modelo había contestado) y `spoken_chars=0`. Sellamos el avance
                # AQUÍ, en el sitio que sí ve cada chunk, y el plazo de arriba consulta esto antes de declarar nada.
                m["chunks"] = int(m.get("chunks") or 0) + 1
                m["last_chunk_ts"] = time.time()
                # SALUD: el proveedor ha CONTESTADO → se retira cualquier fallo anterior del modelo rápido. Va aquí,
                # en el único punto por el que pasan TODAS las llamadas del turno, y no al final del turno
                # conversacional, que es donde estaba (2026-08-12): esa función tiene una docena de `return`
                # tempranos —turno de solo-tool, `show_widget`, gate de atención, fragmento descartado— y cada uno
                # se saltaba el `clear`. Efecto medido: el ◉ enseñó «un turno se atascó» durante 40 MINUTOS
                # mientras el modelo respondía decenas de veces. Un panel que afirma el presente con evidencia
                # rancia es el mismo fallo que el agente caído pintado en azul.
                if not _seen_output:
                    _seen_output = True
                    try:
                        from voice import health_state
                        health_state.clear("llm")
                    except Exception:
                        pass
                text = getattr(delta, "content", None) or ""
                if text:
                    _completion_chars += len(text)
                    yield text
                for tc in (getattr(delta, "tool_calls", None) or []):
                    slot = calls.setdefault(getattr(tc, "index", 0), {"name": "", "arguments": ""})
                    fn = getattr(tc, "function", None)
                    if fn and getattr(fn, "name", None):
                        slot["name"] = fn.name
                    if fn and getattr(fn, "arguments", None):
                        slot["arguments"] += fn.arguments
        finally:
            # cierre de TOTALIZADORES: chars de salida + tokens (reales del proveedor si vinieron, si no estimados)
            # + tiempo total. El TTFT lo mide el llamador (primer yield). Best-effort.
            try:
                m["completion_chars"] = _completion_chars
                m["completion_tokens_est"] = est_tokens(_completion_chars)
                m["total_ms"] = round((time.time() - _t_start) * 1000, 1)
                if _usage is not None:
                    pt = getattr(_usage, "prompt_tokens", None)
                    ctk = getattr(_usage, "completion_tokens", None)
                    tt = getattr(_usage, "total_tokens", None)
                    # HIT DE CACHÉ (2026-08-14). DeepSeek directo reporta `prompt_cache_hit_tokens`, y aquí importa
                    # más que en cualquier otro sitio: el system prompt de voz son ~10k tokens CONSTANTES, así que
                    # en una conversación de verdad la mayor parte del input es un hit, y el input domina 14:1.
                    # Va DENTRO de `prompt_tokens` (verificado: pt = hit + miss), así que se DESCUENTA, no se suma
                    # — ver `energy_meter.llm_cost_to_energy`, donde los dos contadores son parámetros distintos
                    # precisamente para que nadie los confunda y cobre dos veces.
                    _hit = getattr(_usage, "prompt_cache_hit_tokens", None)
                    if _hit is None:
                        _det = getattr(_usage, "prompt_tokens_details", None)
                        _hit = getattr(_det, "cached_tokens", None) if _det is not None else None
                    if _hit is not None:
                        m["prompt_cache_hit_tokens"] = _hit
                    if pt is not None:
                        m["prompt_tokens"] = pt
                    if ctk is not None:
                        m["completion_tokens"] = ctk
                    if tt is not None:
                        m["total_tokens"] = tt
                    m["usage_source"] = "provider"
                else:
                    m["usage_source"] = "estimate"
            except Exception:
                pass
            # ENERGY METERING (INI-018, 2026-07-24) — no-op everywhere except a demo Machine (see
            # nucleo/energy_meter.py). Uses REAL provider usage when available, falls back to the
            # char-based estimate already computed above (m["*_tokens_est"]) otherwise — some real
            # signal beats none for a cost meter, even if provider usage never arrived this call.
            try:
                from nucleo import energy_meter as _energy
                _energy.report_llm_usage(
                    base_url=spec.resolved_base_url(),
                    model=spec.model,
                    prompt_tokens=m.get("prompt_tokens", m.get("prompt_tokens_est")),
                    completion_tokens=m.get("completion_tokens", m.get("completion_tokens_est")),
                    cache_hit_tokens=m.get("prompt_cache_hit_tokens"),
                )
            except Exception:
                pass
            if on_tool_call and calls:
                import json
                for call in calls.values():
                    if not call["name"]:
                        continue
                    try:
                        args = json.loads(call["arguments"] or "{}")
                    except Exception:
                        _drop_tool_call(m, call["name"], call["arguments"])
                        continue
                    on_tool_call(call["name"], args if isinstance(args, dict) else {})

    def describe(self, spec: ModelSpec | None = None) -> str:
        spec = spec or spec_from_config()
        return f"{spec.model} @ {spec.resolved_base_url()} (reasoning={spec.reasoning_effort() or 'default'})"
