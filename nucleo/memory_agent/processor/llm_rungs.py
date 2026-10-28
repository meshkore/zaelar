"""The RUNGS of a task: who is asked, in which order, and which rung is stepped over before it is tried.

A LOCAL titular is preferred when it is there and stepped over when it is not («Ollama as titular when available,
but the system must work NON-STOP», operator, 2026-08-19). Its probe is cached but never LATCHED (`_LOCAL_TTL_S`:
recovery needs no restart) and asks whether the MODEL is served, not just the server — Ollama answers `/api/tags`
while serving a model you never pulled.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

from loguru import logger

from nucleo.memory_agent.processor import llm_routes as routes

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1", "11434")
_LOCAL_TTL_S = float(os.getenv("ZAELAR_LOCAL_PROBE_TTL_S", "60"))
_local_probe: dict[str, tuple[float, bool]] = {}     # "{url}|{model}" -> (checked_at, ready)
_warned_pairs: set[str] = set()


def is_local_endpoint(url: str) -> bool:
    return any(h in (url or "").lower() for h in _LOCAL_HOSTS)


def local_titular_ready(url: str, model: str) -> bool:
    """True if this local endpoint is answering AND serving `model`. Cached for `_LOCAL_TTL_S`, fail-CLOSED: a
    wrong «yes» spends the write on a rung that cannot answer, a wrong «no» only uses the next cloud rung."""
    key = f"{url}|{model}"
    hit = _local_probe.get(key)
    now = time.monotonic()
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
        # `name` == `name:latest`, but `name:7b` != `name:14b` — the tag is only ignored
        # when the CONFIG omitted it.
        ready = any(n == want or (":" not in want and n.split(":")[0] == want) for n in names)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"memllm: local probe {url} failed ({str(e)[:80]}) -> skipping the local titular")
    _local_probe[key] = (now, ready)
    return ready


def reset_local_probe() -> None:
    """Drop the cached verdicts and the once-per-pair warnings (tests, and after the operator changes the profile)."""
    _local_probe.clear()
    _warned_pairs.clear()


def pair_incoherent(url: str, model: str) -> bool:
    """True when `model` is an Ollama-style tag (`name:tag`, no vendor slash) and `url` is NOT local: a model named
    without its endpoint, a pair that can only 404. A SHAPE check on purpose — the pair is equally broken whichever
    config layer (env, profile, store, default) produced each half."""
    m = (model or "").strip()
    if not m or "/" in m or ":" not in m:
        return False
    return not is_local_endpoint(url)


def note_incoherent_pair(where: str, url: str, model: str, *, served: str | None = None) -> None:
    """Said ONCE per pair: a configuration error repeats on every write, and a repeated warning is scrolled past."""
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
    """The FALLBACK rungs given whoever the caller resolved as titular (the HEART resolves its own). Skips a rung
    that is already the titular and one whose credential is absent."""
    rungs: list[tuple[str, str, str, bool]] = []
    for f_url, f_model in routes._FAILOVER.get(task, ()):
        if (f_url, f_model) == titular:
            continue
        f_key = endpoint_key(f_url)
        if not routes.has_credential(f_url, f_key):
            continue
        rungs.append((f_url, f_model, f_key, disable_thinking))
    return rungs


def chain(task: str) -> list[tuple[str, str, str, bool]]:
    """Ordered `(url, model, key, disable_thinking)`: the titular first, then its fallbacks.

    The titular is kept even without a credential — dropping it would substitute a different model silently. A
    LOCAL titular that is not answering, or an incoherent pair, IS stepped over. Never an EMPTY chain: with nowhere
    to relay to, the titular stays so the real error reaches the log and the ◉."""
    url, model, key, disable_thinking = resolve(task)
    head = [(url, model, key, disable_thinking)]
    if is_local_endpoint(url) and not local_titular_ready(url, model):
        head = []
    elif pair_incoherent(url, model):
        head = []
    rungs = head + failover_rungs(task, titular=(url, model), disable_thinking=disable_thinking)
    if not head and rungs and pair_incoherent(url, model):
        note_incoherent_pair(f"memllm[{task}]", url, model, served=rungs[0][1])
    return rungs or [(url, model, key, disable_thinking)]


def note_relay(task: str, model: str, url: str, failures: list[str]) -> None:
    """A relay means the titular is DOWN — that belongs in the ◉. Fail-open: reporting can never break the relay."""
    detail = " · ".join(failures)[:200]
    logger.warning(f"memllm[{task}]: relevo a {model} @ {url} tras {detail}")
    try:
        from voice import health_state
        health_state.record("memory", "degraded", f"{task}: relevo a {model} ({detail})")
    except Exception:  # noqa: BLE001
        pass


def resolve(task: str) -> tuple[str, str, str, bool]:
    """(url, model, key, disable_thinking) for a task. Config wins; an empty key is resolved by endpoint.
    `disable_thinking` is not config-overridable: it is a per-task quality decision, not an endpoint."""
    base_url, model, disable_thinking = routes._DEFAULTS.get(task, routes._DEFAULTS["rem"])
    key = ""
    try:
        from config import v2 as _v2
        mem = _v2.get("memory") or {}
        base_url = (mem.get(f"{task}_base_url") or "").strip() or base_url
        model = (mem.get(f"{task}_model") or "").strip() or model
        key = (mem.get(f"{task}_api_key") or "").strip()
    except Exception:
        pass
    return base_url, model, key or endpoint_key(base_url), disable_thinking


def endpoint_key(url: str) -> str:
    from nucleo.provider_keys import key_for_endpoint     # the single BY-ENDPOINT resolver (V2-098)
    return key_for_endpoint(url, default="local")
