"""The memory PROCESSOR: one operator turn in, 0..N curated PILLS out (V2-013 · T123).

For every pill it decides whether it is kept, WHERE (state / short / long / discard), its importance, TTL and
canonical `slot`. Invariants:

  - **LLM on WRITE, never on READ.** Called only from the async, off-hot-path ingest; the voice turn never waits
    here. Reading is always direct queries (retriever / state / recent_short).
  - **Fail-open.** No model, a failure or garbage → `process()` returns `None` and the caller falls back to the
    cheap heuristic (`memory_agent.classify`) — memory is never left unwritten.
  - **Serial.** At most `_CONCURRENCY` distillations at once (a local model piling up on the GPU cut the voice);
    a turn that finds the slot busy WAITS in a short bounded queue instead of being dropped.

One pill (`process()` returns `list[dict]`)::

    {"text": str,  "dest": "state"|"short"|"long",  "kind": str,  "importance": 0..1,  "ttl_days": float|None,
     "slot": str|None,  "value": str|None,  "change": "none"|"update"|"correction",  "concepts": [str ≤3],
     "state_patch": dict (only for dest=state),  "supersedes": [int] (V2-565, ids offered as recent)}

`kind` follows the pill grammar in `nucleo.memory_agent.writer`: the processor never produces a `result`.
"""
from __future__ import annotations

import asyncio
import json
import os
import time

from loguru import logger

from nucleo.memory_agent import writer as _writer
from nucleo.memory_agent.processor import distill_config as cfg
from nucleo.memory_agent.processor import distill_health as health
from nucleo.memory_agent.processor import distill_prompt as prompt



class _PermanentError(RuntimeError):
    """Not retryable (4xx auth / bad request): permanent on THIS rung, the next rung is still tried."""


_CONCURRENCY = max(1, int(os.getenv("MEM_PROCESSOR_CONCURRENCY", "1")))
_sem = asyncio.Semaphore(_CONCURRENCY)
_QUEUE_MAX = max(0, int(os.getenv("MEM_PROCESSOR_QUEUE_MAX", "2")))
_QUEUE_WAIT = float(os.getenv("MEM_PROCESSOR_QUEUE_WAIT", "15"))   # s max wait for the slot
_waiters = 0
_last_usage: dict = {}


def _is_local(url: str) -> bool:
    return any(h in url for h in ("11434", "localhost", "127.0.0.1"))


def _perf(msg: str, **kw) -> None:
    try:
        from voice.observer import perf
        perf(msg, module="memory", func="mem_processor.process", **kw)
    except Exception:
        pass


async def process(text: str, *, state: dict | None = None) -> list[dict] | None:
    """Distil `text` into memory pills. NEVER raises. The return value matters to the caller:
      - **`None`** = the model is unavailable / disabled / failed → the caller falls back to the heuristic.
      - **`[]`**   = the model RAN and found nothing memorable → a legitimate discard (no fallback).
      - `[pills]`  = curated pills to store."""
    global _waiters
    t = (text or "").strip()
    if not t or not cfg.enabled():
        return None
    if _sem.locked() and _waiters >= _QUEUE_MAX:
        _perf(f"CORAZÓN mem_processor SKIP (GPU ocupada, cola llena {_waiters}/{_QUEUE_MAX})")
        return None
    payload = {"model": cfg.model(), "temperature": 0, "messages": prompt.messages(t, state)}
    rungs = cfg.rung_chain()
    local = _is_local(rungs[0][0])
    t0 = time.time()
    try:
        from voice.observer import mark_busy as _mb   # contention mark while a LOCAL heart holds the GPU
    except Exception:
        _mb = None
    _waiters += 1
    try:
        await asyncio.wait_for(_sem.acquire(), timeout=_QUEUE_WAIT)
    except (asyncio.TimeoutError, TimeoutError):
        _perf(f"CORAZÓN mem_processor SKIP (espera de slot > {_QUEUE_WAIT:g}s)")
        return None
    finally:
        _waiters -= 1
    try:
        if _mb and local:
            _mb("corazon", True)
        try:
            atoms, served = await _through_rungs(rungs, payload)
            if served is None:
                return None
        finally:
            if _mb and local:
                _mb("corazon", False)
    finally:
        _sem.release()
    _report(t, atoms, served, rungs, local, round((time.time() - t0) * 1000))
    return atoms


async def _through_rungs(rungs: list[tuple[str, str]], payload: dict) -> tuple[list[dict] | None, tuple | None]:
    """OUTER loop = rungs (provider order), INNER = retries within a rung. A 429/5xx/timeout is «this provider may
    work in a second» (retry it); a 4xx is «this rung is misconfigured» (never retry, but DO try the next one)."""
    fails: list[str] = []
    for rung_url, rung_model in rungs:
        payload["model"] = rung_model        # the model name travels WITH its endpoint (the broker prefixes it)
        # A LOCAL rung gets ONE attempt and its own timeout: retrying a big local model would stall the write for
        # minutes, and the cloud rung right behind it is the better second try.
        is_local = _is_local(rung_url)
        tries = 1 if is_local else cfg.RETRIES + 1
        timeout_s = cfg.LOCAL_TIMEOUT if is_local else cfg.TIMEOUT
        for attempt in range(tries):
            try:
                data = await _post(rung_url, payload, timeout_s)
                content = data["choices"][0]["message"]["content"]
                # An EMPTY answer is a FAILURE, not a discard: reasoning that ate the budget returns content=""
                # and `_parse("")` would read as «the model decided nothing is memorable».
                if not (content or "").strip():
                    raise RuntimeError(f"respuesta vacía de {rung_model} (finish_reason="
                                       f"{(data.get('choices') or [{}])[0].get('finish_reason')})")
                atoms = _parse(content)
                record_usage(data.get("usage"), base_url=rung_url, model=rung_model)
                health.mark_ok()
                served = (rung_url, rung_model)
                health.served_rung = served      # V2-758: the panel asks `status()` who is answering
                if served != (rungs[0][0], rungs[0][1]):
                    _note_relay(served, fails)
                return atoms, served
            except _PermanentError as e:
                fails.append(f"{rung_model}: {e}")
                break
            except Exception as e:  # noqa: BLE001  (timeout / connection / 429 / 5xx = TRANSIENT → retry)
                if attempt < tries - 1:
                    await asyncio.sleep(cfg.RETRY_BACKOFF * (attempt + 1))
                    continue
                fails.append(f"{rung_model}: {type(e).__name__}: {e}")
                break
    health.mark_fail(" · ".join(fails)[:300] or "sin proveedor")
    return None, None


async def _post(rung_url: str, payload: dict, timeout_s: float) -> dict:
    import aiohttp

    from nucleo import llm_egress
    url = rung_url.rstrip("/") + "/chat/completions"
    # EGRESS (T304): with mediated egress neither the destination nor the credential is the provider's.
    base, tok, extra = llm_egress.route(rung_url, cfg.endpoint_key(rung_url))
    dest = base.rstrip("/") + "/chat/completions" if extra else url
    headers = {"Authorization": f"Bearer {tok}", **(extra or {})}
    if not extra:
        headers["User-Agent"] = cfg.BROWSER_UA
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s)) as s:
        async with s.post(dest, headers=headers, json=payload) as r:
            # ANY 2xx is a good answer: AIMLAPI returns HTTP 201 with a valid completion for some models.
            if not (200 <= r.status < 300):
                body = (await r.text())[:200]
                if 400 <= r.status < 500 and r.status != 429:
                    raise _PermanentError(f"HTTP {r.status} de {url}: {body}")
                raise RuntimeError(f"HTTP {r.status} de {url}: {body}")
            return await r.json()


def last_usage() -> dict:
    """Tokens of the LAST distillation (`{prompt_tokens, completion_tokens, total_tokens}`), `{}` if the provider
    did not return them. Diagnostics / bench only."""
    return dict(_last_usage)


def record_usage(usage: dict | None, *, base_url: str | None = None, model: str | None = None) -> None:
    """Metered against the rung that ACTUALLY served: a relay billed at the titular's row is silent mis-billing."""
    global _last_usage
    if not isinstance(usage, dict):
        _last_usage = {}
        return
    _last_usage = {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    from nucleo import energy_meter as _energy
    _energy.meter_openai_response({"usage": usage}, base_url=base_url or cfg.url(), model=model or cfg.model())


def _note_relay(served: tuple[str, str], fails: list[str]) -> None:
    # A relay means the titular is DOWN — visible in the ◉, never a lone log line.
    logger.warning(f"CORAZÓN: relevo a {served[1]} @ {served[0]} tras {' · '.join(fails)[:200]}")
    try:
        from voice import health_state
        health_state.record("memory", "degraded", f"destilador: relevo a {served[1]} ({' · '.join(fails)[:160]})")
    except Exception:  # noqa: BLE001
        pass


def _report(t: str, atoms: list[dict], served: tuple[str, str], rungs: list, local: bool, ms: int) -> None:
    # The model reported is the one that SERVED, not the titular: the timeline is where a quality change is chased.
    try:
        from voice.observer import emit
        emit("memory", "procesador", role="system", text=f"«{t[:50]}» → {len(atoms)} píldora(s)",
             extra={"layer": "write", "model": served[1], "engine": "local" if local else "remote",
                    "proc_ms": ms, "relayed": served != (rungs[0][0], rungs[0][1])})
    except Exception:
        pass
    _perf(f"CORAZÓN mem_processor {served[1]} {ms}ms" + (" ⚠️LOCAL/GPU" if local else ""), ms=ms)


def _parse(content: str) -> list[dict]:
    """Extract the JSON array even when wrapped in text / ```json. Returns only well-formed pills."""
    txt = (content or "").strip()
    start, end = txt.find("["), txt.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        arr = json.loads(txt[start:end + 1])
    except Exception:
        return []
    return [p for p in (_pill(a) for a in arr if isinstance(a, dict)) if p]


def _pill(a: dict) -> dict | None:
    text = (a.get("text") or "").strip()
    dest = (a.get("dest") or "").strip().lower()
    if not text or dest not in ("state", "short", "long"):
        return None
    try:
        imp = float(a.get("importance", 0.5))
    except (TypeError, ValueError):
        imp = 0.5
    ttl = a.get("ttl_days")
    try:
        ttl = float(ttl) if ttl is not None else None
    except (TypeError, ValueError):
        ttl = None
    patch = a.get("state_patch") if isinstance(a.get("state_patch"), dict) else {}
    # concepts (T126): 1-3 light category labels → graph nodes. Tolerant: a loose string, None or garbage → [].
    raw_c = a.get("concepts")
    if isinstance(raw_c, str):
        raw_c = [raw_c]
    concepts = [str(c).strip().lower() for c in raw_c if str(c).strip()][:3] if isinstance(raw_c, list) else []
    # `value` lets the host build the state patch mechanically; `change` is the model's multilingual change signal
    # that the anti-garble gate consumes — never a host regex.
    change = (a.get("change") or "none").strip().lower()
    if change not in ("none", "update", "correction"):
        change = "none"
    value = (str(a.get("value")).strip()[:120] if a.get("value") is not None else "") or None
    # V2-565: ids this fact corrects. Ints only, capped; the REAL guard is the ingest whitelist and the writer.
    supersedes = []
    for x in (a.get("supersedes") if isinstance(a.get("supersedes"), list) else [])[:4]:
        try:
            supersedes.append(int(x))
        except (TypeError, ValueError):
            continue
    return {
        "text": text[:400],
        "dest": dest,
        "kind": _writer.distilled_kind(a.get("kind")),
        "importance": max(0.0, min(1.0, imp)),
        "ttl_days": ttl,
        "slot": (a.get("slot") or None) or None,
        "value": value,
        "change": change,
        "concepts": concepts,
        "state_patch": patch if dest == "state" else {},
        "supersedes": supersedes,
    }
