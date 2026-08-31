"""config/balances.py — BALANCE/status for external APIs (V2-043).

Dual nature, honest about what each provider lets us know:
  · PROACTIVE — for APIs that EXPOSE balance/usage, probe and return the number (ElevenLabs
    `/v1/user/subscription` gives used/limit characters). Cached with TTL (not probed on every request) and
    FAIL-OPEN (a failing/missing probe = `unknown`, never an exception that brings anything down).
  · REACTIVE — for APIs that DO NOT expose balance (AIMLAPI, xAI, Groq, search providers…), the only possible alert
    is the LAST classified error (`voice/health_state` + `voice/llm_health.classify`): `credit` → "NO BALANCE".

`summary()` merges both into one list per service, ready for the status dialog (alerts) and the configuration
area's API summary (amounts/extended data). It exposes NO key (presence only).
"""
from __future__ import annotations

import os
import threading
import time

import httpx

_TTL = 300.0                       # s — each balance is probed at most every 5 min
_TIMEOUT = 6.0
_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}    # service -> (ts, result)


# ── provider probes (only those that EXPOSE balance) ───────────────────────────────────────────────────────
def _probe_elevenlabs(key: str) -> dict | None:
    """ElevenLabs exposes cycle used/limit characters at /v1/user/subscription."""
    try:
        r = httpx.get("https://api.elevenlabs.io/v1/user/subscription",
                      headers={"xi-api-key": key}, timeout=_TIMEOUT)
        if r.status_code in (401, 403):
            # Distinguish an INVALID key from a VALID but scoped/restricted key: ElevenLabs allows keys without
            # `user_read` that DO perform TTS but cannot read the balance → NOT an alert, just "active, no balance
            # read permission" (unknown). Only a REAL auth failure is an error.
            body = (r.text or "").lower()
            if "missing_permission" in body or "user_read" in body or "permission" in body:
                return {"state": "unknown", "detail": "activa · la key no puede leer el saldo (permiso user_read)"}
            return {"state": "error", "detail": "credencial inválida o caducada"}
        if r.status_code == 429:
            return {"state": "error", "detail": "SIN SALDO/cuota"}
        if r.status_code >= 400:
            return {"state": "unknown", "detail": "no se pudo consultar"}
        d = r.json()
        used = int(d.get("character_count") or 0)
        limit = int(d.get("character_limit") or 0)
        remaining = max(0, limit - used) if limit else None
        pct = (used / limit) if limit else None
        state = "ok"
        if pct is not None and pct >= 0.98:
            state = "error"                       # agotado
        elif pct is not None and pct >= 0.85:
            state = "warn"                         # casi
        return {"state": state, "used": used, "limit": limit, "remaining": remaining,
                "unit": "caracteres", "tier": d.get("tier"),
                "detail": (f"{used:,}/{limit:,} caracteres" if limit else f"{used:,} caracteres")}
    except Exception:
        return None                                # fail-open → unknown


def _zai_credits_verdict(status_code: int, body: str) -> dict:
    """Map the 1-token probe's answer to a wallet state. Pure, so the mapping is testable without a network."""
    if status_code == 200:
        return {"state": "ok", "detail": "con saldo · MEDIDO: sirve completions (cartera de PAGO POR USO)"}
    low = (body or "").lower()
    if "1113" in low or "insufficient" in low:
        return {"state": "error", "detail": "sin saldo (1113) · cartera de pago por uso"}
    if status_code in (401, 403):
        return {"state": "error", "detail": "credencial inválida para paas/v4"}
    return {"state": "unknown", "detail": f"no se pudo medir (HTTP {status_code})"}


def _probe_zai_credits(key: str) -> dict | None:
    """Z.ai's SECOND wallet — pay-per-use credits at `paas/v4`, a different purse from the coding plan
    (V2-462 tells them apart by URL segment; V2-517 makes the panel tell them apart too). Z.ai exposes no
    public balance endpoint (404 on every candidate, measured 2026-08-31), so the only honest reading is a
    1-token completion: HTTP 200 = the wallet serves, error 1113 = out of balance. Costs ~1 token of
    glm-4.6, cached by `balance()`'s 5-min TTL, and only ever queried when the plan tier is down."""
    try:
        r = httpx.post("https://api.z.ai/api/paas/v4/chat/completions",
                       headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                       json={"model": "glm-4.6", "messages": [{"role": "user", "content": "hi"}],
                             "max_tokens": 1},
                       timeout=max(_TIMEOUT, 12.0))
        return _zai_credits_verdict(r.status_code, r.text or "")
    except Exception:
        return None                                # fail-open → unknown


# service -> (env vars that provide the key, probe). Only services with queryable balance.
_PROBES = {
    "elevenlabs": (["ELEVENLABS_API_KEY"], _probe_elevenlabs),
    "z.ai-creditos": (["Z_AI_API_KEY"], _probe_zai_credits),
}


def _key_for(envs: list[str]) -> str:
    for e in envs:
        v = (os.getenv(e) or "").strip()
        if v:
            return v
    return ""


def balance(service: str, refresh: bool = False) -> dict:
    """Balance for ONE service (cached). `{state: ok|warn|error|unknown|no_key, ...}`. Never raises."""
    envs, probe = _PROBES.get(service, (None, None))
    if probe is None:
        return {"state": "unknown", "detail": "el proveedor no expone saldo"}
    key = _key_for(envs)
    if not key:
        return {"state": "no_key", "detail": "sin credencial"}
    now = time.time()
    if not refresh:
        with _lock:
            hit = _cache.get(service)
        if hit and (now - hit[0]) < _TTL:
            return hit[1]
    res = probe(key) or {"state": "unknown", "detail": "no se pudo consultar"}
    with _lock:
        _cache[service] = (now, res)
    return res


# ── REACTIVE state (last classified error) for services that do not expose balance ─────────────────────────
def _reactive(service_keys: list[str]) -> dict:
    """Read the last failure recorded in health_state for these internal services (llm/stt/tts) and translate it to
    credit state. `credit` → no-balance error; `auth` → credential; `outage`/error → provider issue."""
    try:
        from voice import health_state
    except Exception:
        return {}
    worst = {}
    rank = {"credit": 3, "auth": 2, "outage": 1, "error": 1, "slow": 0}   # one stuck turn never hides an outage
    for sk in service_keys:
        rec = health_state.get(sk)
        if not rec:
            continue
        kind = rec.get("kind") or "error"
        if not worst or rank.get(kind, 0) > rank.get(worst.get("kind", ""), 0):
            worst = {"kind": kind, "text": rec.get("text", "")}
    return worst


# maps EXTERNAL service → INTERNAL services (health_state) through which its errors manifest.
_REACTIVE_MAP = {
    "aimlapi": ["llm"], "xai": ["llm"], "groq": ["llm"], "gemini": ["llm"],
    "deepgram": ["stt", "tts"], "mistral": ["stt"], "cartesia": ["tts"], "elevenlabs": ["tts"],
}
_CREDIT_KIND = {"credit": ("error", "SIN SALDO/cuota"), "auth": ("error", "credencial inválida"),
                "outage": ("warn", "el proveedor no responde"),
                # `slow` (2026-08-12) = ONE turn got stuck and was cut. It is a warning, not a provider outage:
                # saying "not responding" about something that answers before and after sends us hunting a non-bug.
                "slow": ("warn", "un turno se atascó")}


def summary(refresh: bool = False) -> list[dict]:
    """External-service state for the status dialog + the config API summary. Merges: key presence (doctor),
    proactive balance (if exposed), and last classified error (reactive). `[{key, enables, set, state, detail,
    balance?}]`. Never raises; never exposes the key."""
    try:
        from config import doctor
        creds = doctor.credentials()
    except Exception:
        creds = []
    out: list[dict] = []
    for c in creds:
        svc = c["key"]
        item = {"key": svc, "enables": c.get("enables", ""), "set": bool(c.get("set")),
                "state": "off", "detail": ""}
        if not c.get("set"):
            item["state"] = "off"
            item["detail"] = "sin credencial"
            out.append(item)
            continue
        # 1) proactive balance if the provider exposes it
        bal = balance(svc, refresh=refresh) if svc in _PROBES else None
        if bal and bal.get("state") not in (None, "no_key", "unknown"):
            item["state"] = bal["state"]
            item["detail"] = bal.get("detail", "")
            item["balance"] = {k: bal[k] for k in ("used", "limit", "remaining", "unit", "tier") if k in bal}
        else:
            item["state"] = "ok"
            item["detail"] = "activa" + (" · no expone saldo" if svc not in _PROBES else "")
        # 2) reactive: a recent error (credit/auth) WINS over "ok"
        react = _reactive(_REACTIVE_MAP.get(svc, []))
        if react:
            st, txt = _CREDIT_KIND.get(react["kind"], ("warn", "problema reciente"))
            item["state"] = st
            item["detail"] = txt
            item["last_error"] = (react.get("text") or "")[:120]
        out.append(item)
    return out


def worker_providers() -> list[dict]:
    """BRAIN WORKER provider tiers, in the same format as the rest of the services.

    This exact piece was missing (2026-08-02): the Z.AI plan exhausted its weekly quota mid-task and the alerts
    panel — which exists to warn about this — said nothing, because the worker provider was not in any map. The
    operator found out by reading "API Error … Weekly Limit Exhausted" where they expected their report."""
    try:
        from nucleo.workers import providers as prov
        tiers = prov.status()
    except Exception:
        return []
    out = []
    for t in tiers:
        # "IN USE" means it is WORKING, not that it would be chosen — those are two different things, and confusing
        # them made the row lie in both halves: it said "IN USE · available" for a provider that was serving nobody
        # (the relay had moved it aside) and whose window was still exhausted.
        mark = "EN USO · " if t.get("serving") else ("PRÓXIMO · " if t.get("active") else "")
        out.append({"key": f"worker:{t['name']}", "enables": f"procesos de fondo · {t.get('plan', '')}",
                    "set": True, "state": t["state"], "detail": mark + t.get("detail", "")})
    # V2-517 (operator, 2026-08-31): z.ai has TWO wallets — the coding-plan quota and the pay-per-use
    # credits (paas/v4). A flat red "z.ai sin cuota" reads as "z.ai dead", which is false when the OTHER
    # purse has balance: measured live, the plan was exhausted until 01 Sep while paas/v4 served a
    # completion. When the plan tier is down, measure the second wallet and SAY it, so the operator knows
    # whether this can still go well. (It is information, not a chain rung: the worker's relay stays
    # plan → DeepSeek → license.)
    if any(t["name"] == "z.ai" and t["state"] != "ok" for t in tiers):
        bal = balance("z.ai-creditos")
        if bal.get("state") not in (None, "no_key"):
            # The good news must survive the alerts() filter (the panel only shows warn/error rows), so it
            # rides ON the plan's red row — one row, the complete truth — besides its own summary row.
            note = {"ok": " · la 2ª cartera (pago por uso) CON saldo ✓ — medido",
                    "error": " · la 2ª cartera (pago por uso) también sin saldo"}.get(bal.get("state"), "")
            if note:
                for r in out:
                    if r["key"] == "worker:z.ai":
                        r["detail"] += note
            out.append({"key": "worker:z.ai-creditos", "enables": "la SEGUNDA cartera de z.ai (paas/v4)",
                        "set": True, "state": bal.get("state", "unknown"), "detail": bal.get("detail", "")})
    if tiers and all(t["state"] != "ok" for t in tiers):
        out.append({"key": "worker:sin-relevo", "enables": "procesos de fondo", "set": True, "state": "error",
                    "detail": "NINGÚN proveedor con cuota — los procesos de fondo no pueden correr"})
    # BLIND ≠ DOWN (2026-08-10). Separate row because it is a different problem with a different fix: the provider's
    # model responds, but its search/read tools are out of quota → the worker reasons without being able to inspect
    # anything. Without this row, the panel said "everything ok" while the worker delivered conclusions without
    # material.
    try:
        from voice import health_state
        rec = health_state.get("worker_tools")
        if rec:
            out.append({"key": "worker:tools", "enables": "búsqueda y lectura web DE los workers", "set": True,
                        "state": "error", "detail": rec.get("text") or "herramientas del proveedor sin cuota"})
    except Exception:
        pass
    return out


def cluster_providers() -> list[dict]:
    """Provider tiers for the CLUSTER BRAIN (`nucleo.flash.provider_chain`, 2026-08-03), same format as
    `worker_providers()`. This exact piece was missing: a Z.AI 429 in the cluster turn (heartbeat insisting on
    replying to a peer) did not appear anywhere in the panel — the operator only saw it in the raw log ("cluster
    brain turn failed: 429"), looping every time the heartbeat retried."""
    try:
        from nucleo.flash import provider_chain as pc
        tiers = pc.status()
    except Exception:
        return []
    out = []
    for t in tiers:
        out.append({"key": f"cluster:{t['name']}", "enables": f"cerebro de cluster (off-voz) · {t.get('plan', '')}",
                    "set": True, "state": t["state"],
                    "detail": ("EN USO · " if t.get("active") else "") + t.get("detail", "")})
    if tiers and all(t["state"] != "ok" for t in tiers):
        out.append({"key": "cluster:sin-relevo", "enables": "cerebro de cluster", "set": True, "state": "error",
                    "detail": "NINGÚN proveedor con cuota — el canal de cluster no puede responder"})
    return out


def summary_with_workers(refresh: bool = False) -> list[dict]:
    """summary() + worker tiers + cluster-brain tiers. What the status dialog should render. (The name became too
    narrow after adding `cluster_providers()` — kept to avoid touching callers.)"""
    return summary(refresh=refresh) + worker_providers() + cluster_providers()


def alerts(refresh: bool = False) -> list[dict]:
    """Only services in warn/error state (for the status dialog). Subset of summary()."""
    return [s for s in summary_with_workers(refresh=refresh) if s.get("state") in ("warn", "error")]
