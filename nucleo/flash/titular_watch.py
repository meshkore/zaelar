"""titular_watch.py — GETTING BACK TO THE TITULAR, and getting the light back to green (V2-750).

WHAT WAS WRONG. The provider light had many writers and ONE clearer. `health_state.record("llm", …)` is
written by every path that sees a model fail; the only thing that ever cleared it was the first chunk of a
successful VOICE turn (`fast_client.stream`). So a single failed turn painted the panel red for the full
600 s TTL, and nothing short of the operator opening a microphone and being answered could repaint it.

Measured 2026-09-22 on his own engine. One turn failed at 12:21:02 (`Cerebro rápido caído — turno
degradado`). At 12:27 the panel still read «deepseek-v4-pro · DeepSeek · no responde» while, probed
directly in that same minute, DeepSeek answered `/models` 200, reported a $2.77 balance and completed a
chat in 1.22 s. His words: «el agente local en el browser me sigue marcando una alarma diciendo que no
responde». The provider had been fine for six minutes and nobody was asking.

THE FIX IS TO ASK. This is the only piece in the engine that probes a provider on its own initiative, and it
exists because every other health signal here is reactive by necessity (the note at the top of
`voice/health_state.py` says so: no balance endpoint, so we learn by failing). A liveness probe needs no
balance endpoint — it needs one cheap request and an HTTP status.

THE CADENCE IS THE OPERATOR'S, verbatim (2026-09-22): «haría comprobaciones de forma recursiva, en plan
primero cada 10 segundos, luego cada 60 segundos, luego cada 3 minutos, hasta que consiguiéramos volver al
principal». It backs off because a provider that has been down for ten minutes is not likely to come back in
the next ten seconds, and because the probe itself costs a request against his account.

⚠️ IT ONLY EVER CLEARS. This watcher can turn a light GREEN and lift a cooldown; it can never turn a light
red or open one. A prober that could condemn a provider would be a second opinion competing with the real
turns, and the real turns are the ones that matter — they carry the actual prompt, the actual tools and the
actual latency. A probe that says «fine» while every turn fails must lose, so it is not allowed to vote.
"""
from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request

from loguru import logger

#: The operator's ladder. After the last step it stays there — a provider down for an hour is checked every
#: three minutes, not every ten seconds.
BACKOFF_S = (10.0, 60.0, 180.0)

_PROBE_TIMEOUT_S = 8.0
_IDLE_TICK_S = 5.0       # how often we look at whether there is anything to watch at all (no network)

_state = {"running": False, "step": 0, "last_probe": 0.0, "last_ok": 0.0, "probes": 0}


def snapshot() -> dict:
    """What the watcher is doing, for the status panel and for an incident."""
    return dict(_state)


def _titular() -> dict | None:
    """The voice titular as the chain sees it — same source the turn uses, never a second copy."""
    try:
        from nucleo.flash import provider_chain as pc
        ch = pc.chain(pc.ROLE_VOICE)
        return ch[0] if ch else None
    except Exception:  # noqa: BLE001
        return None


def ailing() -> bool:
    """Is there anything to get back FROM? Either the panel is showing a model fault, or the titular is
    sitting in a cooldown some real failure opened. Both are cleared by the same good news."""
    try:
        from voice import health_state
        if health_state.get("llm"):
            return True
    except Exception:  # noqa: BLE001
        pass
    t = _titular()
    if not t:
        return False
    try:
        from nucleo.flash import provider_chain as pc
        return not pc.tier_available(t)
    except Exception:  # noqa: BLE001
        return False


def probe(tier: dict) -> tuple[bool, str]:
    """One cheap request. TRUE on any HTTP 200 — deliberately not on the CONTENT.

    A DeepSeek reasoner spends a small `max_tokens` budget on thinking and returns a 200 with an empty body
    (measured: `deepseek-v4-pro`, 400 tokens, 7.47 s, ''). Reading that as a failure would be this module
    condemning a healthy provider for answering the way it always answers — and the question here is only
    «is anybody home», which a status line answers and a body does not.
    """
    url = (tier.get("base_url") or "").rstrip("/") + "/chat/completions"
    key = (tier.get("api_key") or "").strip()
    if not key:
        try:
            from nucleo.provider_health import token_for
            key = token_for(tier)
        except Exception:  # noqa: BLE001
            key = ""
    if not key or not tier.get("model"):
        return False, "sin credencial"
    body = json.dumps({"model": tier["model"], "max_tokens": 1,
                       "messages": [{"role": "user", "content": "ping"}]}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=_PROBE_TIMEOUT_S) as r:
            return (200 <= r.status < 300), str(r.status)
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__


def _recovered(tier: dict) -> None:
    """The titular answered. Lift what the failure left behind, and SAY so — a recovery nobody can see is
    the same invisible state this whole module exists to end."""
    try:
        from nucleo.flash import provider_chain as pc
        pc.clear(tier.get("name") or "")
    except Exception:  # noqa: BLE001
        pass
    try:
        from voice import health_state
        health_state.clear("llm")
    except Exception:  # noqa: BLE001
        pass
    _state["last_ok"] = time.time()
    _state["step"] = 0
    try:
        from voice.observer import emit
        emit("session", "✅ el titular vuelve a responder — se recupera el principal",
             extra={"model": tier.get("model"), "provider": tier.get("provider"),
                    "probes": _state["probes"]})
    except Exception:  # noqa: BLE001
        pass
    _state["probes"] = 0


async def _tick() -> None:
    if not ailing():
        _state["step"] = 0
        _state["probes"] = 0
        return
    wait = BACKOFF_S[min(_state["step"], len(BACKOFF_S) - 1)]
    if time.time() - _state["last_probe"] < wait:
        return
    tier = _titular()
    if not tier:
        return
    _state["last_probe"] = time.time()
    _state["probes"] += 1
    ok, detail = await asyncio.to_thread(probe, tier)
    if ok:
        _recovered(tier)
        return
    # Still down: step ONE rung down the ladder, never past its end.
    _state["step"] = min(_state["step"] + 1, len(BACKOFF_S) - 1)
    logger.debug(f"titular_watch: {tier.get('model')} sigue sin responder ({detail}) — "
                 f"siguiente intento en {BACKOFF_S[min(_state['step'], len(BACKOFF_S) - 1)]:.0f}s")


async def run() -> None:
    """The loop. Cheap when everything is fine: `ailing()` touches no network, so a healthy engine spends one
    dictionary lookup every `_IDLE_TICK_S` and never calls a provider."""
    _state["running"] = True
    try:
        while True:
            try:
                await _tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — a watcher that dies leaves the light stuck forever, which
                logger.warning(f"titular_watch: {e!r}")   # is precisely the bug it was written to fix
            await asyncio.sleep(_IDLE_TICK_S)
    finally:
        _state["running"] = False
