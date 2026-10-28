"""The engine's synchronous off-hot-path LLM client: `chat_sync(task, system, user)` through the task's rungs.

Runs INSIDE `asyncio.to_thread` (REM sleep), in scripts and benches, and for the small judges (`turn_complete`,
`directed`) — never the voice brain. Fail-open: `None` when no rung answers, and the caller degrades.
"""
from __future__ import annotations

import json
import urllib.request

from loguru import logger

from nucleo.memory_agent.processor import llm_rungs as rungs

# One shared keep-alive client: a fresh connection per call paid a full DNS+TCP+TLS handshake (~150-400 ms) in
# front of the hot-path judges. httpx ships with `openai`; without it this degrades to urllib, never to a failure.
_HTTP_POOL = None   # httpx.Client (thread-safe, keep-alive) | False = unavailable, use urllib
_last_usage: dict = {}


def _post_json(full_url: str, payload: dict, *, headers: dict, timeout: float) -> dict:
    """POST JSON and decode the JSON reply over the pooled connection. HTTP errors raise."""
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
    """ONE request to ONE rung. Raises on anything that isn't usable content — including an EMPTY answer
    (reasoning that ate `max_tokens`: `finish_reason=length`, `content=""`, no exception)."""
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    # Only DeepSeek's direct endpoint honours this field, and only tasks benchmarked reasoning-OFF ask for it.
    if disable_thinking and "deepseek" in model.lower() and "api.deepseek.com" in url.lower():
        payload["thinking"] = {"type": "disabled"}
    # EGRESS (T304): with mediated egress neither the URL nor the key is the provider's; the `extra` headers name
    # the provider family, or a stand-in on another provider is sent to the wrong upstream.
    from nucleo import llm_egress
    r_url, r_key, extra = llm_egress.route(url, key)
    data = _post_json(
        r_url.rstrip("/") + "/chat/completions",
        payload,
        headers={"Authorization": f"Bearer {r_key}", "Content-Type": "application/json",
                 # AIMLAPI sits behind Cloudflare and 403s urllib's default UA → browser UA
                 "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
                 **extra},
        timeout=timeout,
    )
    content = data["choices"][0]["message"]["content"]
    if not (content or "").strip():
        raise RuntimeError("respuesta vacía (razonamiento se comió el presupuesto)")
    _record_usage(data.get("usage"), url, model)     # priced by the PROVIDER's URL, not the egress one
    return content


def chat_sync(task: str, system: str, user: str, *, max_tokens: int = 900,
              temperature: float = 0.2, timeout: float = 60.0,
              model_override: str | None = None, url_override: str | None = None) -> str | None:
    """SYNCHRONOUS chat through `rungs.chain(task)` in order. Returns the content, or None if NO rung answers.

    ⚠️ A `model_override`/`url_override` DISABLES the chain on purpose: whoever pins a model (a benchmark, the
    LoCoMo judge) would otherwise report one model while having measured another."""
    if url_override or model_override:
        url, model, key, disable_thinking = rungs.resolve(task)
        if url_override:
            url, key = url_override, rungs.endpoint_key(url_override)
        if model_override:
            model = model_override
        try:
            return _attempt(url, model, key, disable_thinking, system=system, user=user,
                            max_tokens=max_tokens, temperature=temperature, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"memllm[{task}]: {model} @ {url} falló: {str(e)[:160]} → fail-open (pinned)")
            return None

    chain = rungs.chain(task)
    failures: list[str] = []
    for pos, (url, model, key, disable_thinking) in enumerate(chain):
        try:
            content = _attempt(url, model, key, disable_thinking, system=system, user=user,
                               max_tokens=max_tokens, temperature=temperature, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{model}: {str(e)[:120]}")
            continue
        if pos:
            rungs.note_relay(task, model, url, failures)
        return content
    logger.warning(f"memllm[{task}]: {len(chain)} escalón(es) agotados ({' · '.join(failures)[:200]}) → fail-open")
    try:
        from voice import health_state
        health_state.record("memory", "outage", f"{task}: sin proveedor ({' · '.join(failures)[:160]})")
    except Exception:  # noqa: BLE001
        pass
    return None


def last_usage() -> dict:
    """Tokens of the last call (`{prompt_tokens, completion_tokens, total_tokens}`), `{}` if not returned."""
    return dict(_last_usage)


def _record_usage(usage: dict | None, base_url: str, model: str) -> None:
    global _last_usage
    # Without `usage` the call is still metered, with None counters: `energy_meter` applies its floor. A provider
    # that does not report must not be free.
    if not isinstance(usage, dict):
        _last_usage = {}
        usage = {}
    else:
        _last_usage = {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    from nucleo import energy_meter as _energy
    _energy.meter_openai_response({"usage": usage}, base_url=base_url, model=model)
