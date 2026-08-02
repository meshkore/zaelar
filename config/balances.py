"""config/balances.py — SALDO/estado de las APIs externas (V2-043).

Doble naturaleza, honesta sobre lo que cada proveedor deja saber:
  · PROACTIVO — para las APIs que EXPONEN saldo/uso, se sondea y se devuelve el número (ElevenLabs
    `/v1/user/subscription` da caracteres usados/límite). Cacheado con TTL (no se sondea en cada request) y
    FAIL-OPEN (una sonda que falla/no existe = `unknown`, nunca una excepción que tumbe nada).
  · REACTIVO — para las que NO exponen saldo (AIMLAPI, xAI, Groq, buscadores…), el único aviso posible es el
    ÚLTIMO error clasificado (`voice/health_state` + `voice/llm_health.classify`): `credit` → «SIN SALDO».

`summary()` funde ambas cosas en una lista por servicio, lista para el diálogo de estado (alertas) y para el
resumen de APIs del área de configuración (importes/datos extendidos). NO expone ninguna key (solo presencia).
"""
from __future__ import annotations

import os
import threading
import time

import httpx

_TTL = 300.0                       # s — cada saldo se resondea como mucho cada 5 min
_TIMEOUT = 6.0
_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}    # service -> (ts, result)


# ── sondas por proveedor (solo las que EXPONEN saldo) ────────────────────────────────────────────────────
def _probe_elevenlabs(key: str) -> dict | None:
    """ElevenLabs expone caracteres usados/límite del ciclo en /v1/user/subscription."""
    try:
        r = httpx.get("https://api.elevenlabs.io/v1/user/subscription",
                      headers={"xi-api-key": key}, timeout=_TIMEOUT)
        if r.status_code in (401, 403):
            # Distinguir key INVÁLIDA de key VÁLIDA pero con permisos restringidos (scoped): ElevenLabs permite
            # keys sin `user_read` que SÍ hacen TTS pero no pueden leer el saldo → NO es una alerta, es "activa,
            # sin permiso de lectura de saldo" (unknown). Solo un fallo de auth REAL es error.
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


# service -> (env vars que aportan la key, sonda). Solo servicios con saldo consultable.
_PROBES = {
    "elevenlabs": (["ELEVENLABS_API_KEY"], _probe_elevenlabs),
}


def _key_for(envs: list[str]) -> str:
    for e in envs:
        v = (os.getenv(e) or "").strip()
        if v:
            return v
    return ""


def balance(service: str, refresh: bool = False) -> dict:
    """Saldo de UN servicio (cacheado). `{state: ok|warn|error|unknown|no_key, ...}`. Nunca lanza."""
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


# ── estado REACTIVO (último error clasificado) para las que no exponen saldo ─────────────────────────────
def _reactive(service_keys: list[str]) -> dict:
    """Lee el último fallo registrado en health_state para estos servicios internos (llm/stt/tts) y lo
    traduce a estado de crédito. `credit` → error 'sin saldo'; `auth` → credencial; `outage`/error → problema."""
    try:
        from voice import health_state
    except Exception:
        return {}
    worst = {}
    rank = {"credit": 3, "auth": 2, "outage": 1, "error": 1}
    for sk in service_keys:
        rec = health_state.get(sk)
        if not rec:
            continue
        kind = rec.get("kind") or "error"
        if not worst or rank.get(kind, 0) > rank.get(worst.get("kind", ""), 0):
            worst = {"kind": kind, "text": rec.get("text", "")}
    return worst


# mapea servicio EXTERNO → los servicios INTERNOS (health_state) por los que se manifiesta un error suyo.
_REACTIVE_MAP = {
    "aimlapi": ["llm"], "xai": ["llm"], "groq": ["llm"], "gemini": ["llm"],
    "deepgram": ["stt", "tts"], "mistral": ["stt"], "cartesia": ["tts"], "elevenlabs": ["tts"],
}
_CREDIT_KIND = {"credit": ("error", "SIN SALDO/cuota"), "auth": ("error", "credencial inválida"),
                "outage": ("warn", "el proveedor no responde")}


def summary(refresh: bool = False) -> list[dict]:
    """Estado por servicio externo para el diálogo de estado + el resumen de APIs de la config.
    Funde: presencia de key (doctor), saldo proactivo (si se expone) y último error clasificado (reactivo).
    `[{key, enables, set, state, detail, balance?}]`. Nunca lanza; nunca expone la key."""
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
        # 1) saldo proactivo si el proveedor lo expone
        bal = balance(svc, refresh=refresh) if svc in _PROBES else None
        if bal and bal.get("state") not in (None, "no_key", "unknown"):
            item["state"] = bal["state"]
            item["detail"] = bal.get("detail", "")
            item["balance"] = {k: bal[k] for k in ("used", "limit", "remaining", "unit", "tier") if k in bal}
        else:
            item["state"] = "ok"
            item["detail"] = "activa" + (" · no expone saldo" if svc not in _PROBES else "")
        # 2) reactivo: un error reciente (crédito/auth) MANDA sobre "ok"
        react = _reactive(_REACTIVE_MAP.get(svc, []))
        if react:
            st, txt = _CREDIT_KIND.get(react["kind"], ("warn", "problema reciente"))
            item["state"] = st
            item["detail"] = txt
            item["last_error"] = (react.get("text") or "")[:120]
        out.append(item)
    return out


def worker_providers() -> list[dict]:
    """Escalones del proveedor de los BRAIN WORKERS, en el mismo formato que el resto de servicios.

    Faltaba justo esto (2026-08-02): el plan de Z.AI agotó su cuota semanal en mitad de una tarea y el panel de
    alertas —que existe para avisar de esto— no dijo nada, porque el proveedor de los workers no estaba en
    ningún mapa. El operador se enteró leyendo un «API Error … Weekly Limit Exhausted» donde esperaba su informe."""
    try:
        from nucleo.workers import providers as prov
        tiers = prov.status()
    except Exception:
        return []
    out = []
    for t in tiers:
        out.append({"key": f"worker:{t['name']}", "enables": f"procesos de fondo · {t.get('plan', '')}",
                    "set": True, "state": t["state"],
                    "detail": ("EN USO · " if t.get("active") else "") + t.get("detail", "")})
    if tiers and all(t["state"] != "ok" for t in tiers):
        out.append({"key": "worker:sin-relevo", "enables": "procesos de fondo", "set": True, "state": "error",
                    "detail": "NINGÚN proveedor con cuota — los procesos de fondo no pueden correr"})
    return out


def summary_with_workers(refresh: bool = False) -> list[dict]:
    """summary() + los escalones de los workers. Lo que debe pintar el diálogo de estado."""
    return summary(refresh=refresh) + worker_providers()


def alerts(refresh: bool = False) -> list[dict]:
    """Solo los servicios en estado warn/error (para el diálogo de estado). Subconjunto de summary()."""
    return [s for s in summary_with_workers(refresh=refresh) if s.get("state") in ("warn", "error")]
