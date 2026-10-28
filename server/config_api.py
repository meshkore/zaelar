"""server/config_api.py — control plane for the full CONFIGURATION surface (V2-043).

The frontend full-screen configuration area (choosing WHICH API/model each piece uses + API balance summary) is
backed here. UI-managed config (product invariant): the user changes EVERYTHING from the interface, never by
editing files. It gathers what used to be scattered around (v2.py, settings.py, connectors.py, credentials.py,
doctor.py, spotify) behind one mouth — without duplicating logic, delegating to each owning module.

  · GET  /api/config            → REDACTED aggregate view (never a cleartext key): v2 (fast/code_agent/memory/
                                   flags) + voice (settings) + connectors + spotify + credentials + provider
                                   catalog per piece + API balance summary.
  · POST /api/config/v2         → {section, patch} → v2.set(section, patch) (per piece: model/provider/params).
  · POST /api/config/credential → {key|provider, value} → credentials.set_key (doctor resolves provider→env).
  · GET  /api/config/apis       → balance summary/alerts (proactive where exposed + reactive from last error).

Loopback (single-user local app), like the rest of the API. Voice still goes through `/api/settings`; the config
area consumes it the same way. v2 changes (fast/code_agent/memory) are PER INVOCATION → they apply without
reconnecting.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from server import connectors_api as _connectors_api
from server.config_catalog import _PROVIDER_CATALOG, _catalog_for_ui

router = APIRouter()
router.include_router(_connectors_api.router)   # /api/connectors/* (refactor2710-13 T-03)

# Sections of config/v2.json that pick a PROVIDER/model (as opposed to `flags`, which doesn't). When
# ZAELAR_USER_ID is set these are locked (not user-editable). Self-host is completely unaffected
# (is_cloud_account() is always False there).
_CLOUD_LOCKED_V2_SECTIONS = frozenset({"fast", "code_agent", "memory", "triage", "susurro"})


@router.get("/api/config")
async def get_config():
    """REDACTED aggregate view for the configuration area. NEVER contains a cleartext API key."""
    out: dict = {}
    try:
        from config import v2
        out["v2"] = v2.public_all()
    except Exception as e:  # noqa: BLE001
        out["v2"] = {"error": str(e)[:120]}
    try:
        from config import settings
        out["voice"] = settings.effective()
    except Exception as e:  # noqa: BLE001
        out["voice"] = {"error": str(e)[:120]}
    try:
        from config import connectors
        out["connectors"] = connectors.public_all()
    except Exception as e:  # noqa: BLE001
        out["connectors"] = {"error": str(e)[:120]}
    try:
        from connectors.spotify import auth as _sp
        out["spotify"] = _sp.status()
    except Exception:
        out["spotify"] = {"can_connect": False}
    try:
        from config import doctor
        out["credentials"] = doctor.credentials()
    except Exception:
        out["credentials"] = []
    out["catalog"] = _catalog_for_ui()
    try:
        from nucleo.energy import account as cloud_account
        out["cloud_profile"] = cloud_account.is_cloud_account()
        out["account_url"] = cloud_account.account_url()
    except Exception:
        out["cloud_profile"] = False
        out["account_url"] = ""
    try:
        from config import balances
        out["apis"] = balances.summary_with_workers()
    except Exception:
        out["apis"] = []
    return JSONResponse(out)


_MODEL_FIELDS = {"fast": ("model",),
                 "code_agent": ("model", "model_memory", "model_web", "model_code")}


def _model_mismatch(section: str, patch: dict) -> str:
    """Is a model being saved that the selected provider DOES NOT serve? Return the reason, or "" if it matches.

    The bug this closes: when changing provider, models from the previous one remained set (Codex with five fields
    at `glm-5.2`). Saving was OK and the error appeared minutes later, INSIDE a task, as "There's an issue with the
    selected model" — the operator has no way to connect that with what they saved. A config mismatch is rejected
    HERE, with the name of the offending value.

    Only applies to CLOSED-list sections and only if the provider declares models: a provider without a list (or an
    open section) still accepts whatever the caller sends — this validates, it does not lock in.

    ⚠️ It reads the RESULT of the patch, not the patch (fixed 2026-09-11 from a live corruption). The first
    version compared `patch["provider"]` against `patch["model"]`, so a patch carrying ONLY a provider had no
    model to compare and walked straight through — leaving `config/v2.json` holding
    `{"fast": {"provider": "aimlapi"}}` over a `model` and `base_url` that still belonged to DeepSeek. The
    effective config was a provider from one vendor with an endpoint from another, which is the V2-657 defect
    exactly: observability prints one name while the traffic goes somewhere else. A validator that reads the
    REQUEST instead of the resulting STATE cannot see a partial write, and a partial write is the normal shape
    of a config edit."""
    conf = _PROVIDER_CATALOG.get(section) or {}
    if not conf.get("closed_models"):
        return ""
    if not str(patch.get("provider") or "").strip():
        # No provider named in this patch: the effective one is unchanged, so a model field that is present
        # still has to agree with it — which is what merging below covers.
        if not any(str(patch.get(f) or "").strip() for f in _MODEL_FIELDS.get(section, ())):
            return ""
    try:
        from config import v2 as _v2
        effective = {**_v2.get(section), **{k: v for k, v in (patch or {}).items() if v not in (None, "")}}
    except Exception:  # noqa: BLE001 — an unreadable store must not block a save; validate the patch alone
        effective = dict(patch or {})
    prov_id = str(effective.get("provider") or "").strip()
    if not prov_id:
        return ""
    prov = next((p for p in conf.get("providers", []) if p.get("id") == prov_id), None)
    if prov is None:
        return f"unknown provider «{prov_id}» for {section}"
    allowed = set(prov.get("models") or [])
    if not allowed:
        return ""
    for field in _MODEL_FIELDS.get(section, ()):
        val = str(effective.get(field) or "").strip()
        if val and val not in allowed:
            return (f"«{val}» is not served by {prov.get('label') or prov_id} (field {field}). "
                    f"Available: {', '.join(sorted(allowed))}")
    # The endpoint travels with the provider. A provider swapped without its `base_url` leaves the label
    # saying one vendor and the traffic going to another — silent, and expensive to diagnose (V2-657).
    want_url = str(prov.get("base_url") or "").strip()
    got_url = str(effective.get("base_url") or "").strip()
    if want_url and got_url and got_url.rstrip("/") != want_url.rstrip("/"):
        return (f"«{prov.get('label') or prov_id}» does not answer at {got_url} — change the provider and its "
                f"endpoint together (expected {want_url})")
    return ""


@router.post("/api/config/v2")
async def set_v2(payload: dict | None = None):
    """Write one v2 section (fast/code_agent/memory/flags) per piece. `{section, patch}`. Returns the public
    (redacted) view of that section. Changes are PER INVOCATION → they apply without reconnecting."""
    payload = payload or {}
    section = (payload.get("section") or "").strip()
    patch = payload.get("patch") or {}
    if not section or not isinstance(patch, dict):
        return JSONResponse({"ok": False, "error": "missing section/patch"}, status_code=400)
    if section in _CLOUD_LOCKED_V2_SECTIONS:
        try:
            from nucleo.energy import account as cloud_account
            if cloud_account.is_cloud_account():
                return JSONResponse(
                    {"ok": False, "error": "provider/model selection is centrally managed in the cloud profile"},
                    status_code=403,
                )
        except Exception:
            pass
    bad = _model_mismatch(section, patch)
    if bad:
        return JSONResponse({"ok": False, "error": bad}, status_code=400)
    try:
        from config import v2
        v2.set(section, patch)
        return JSONResponse({"ok": True, "section": section, "config": v2.public(section)})
    except KeyError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)[:160]}, status_code=500)


@router.post("/api/config/credential")
async def set_credential(payload: dict | None = None):
    """Save/update a credential in the store (chmod 600). `{key|provider, value}`. Resolves a known `provider`
    (aimlapi/xai/groq/elevenlabs…) to its main environment variable through the doctor catalog, or accepts a literal
    env name (power-user). Empty value = delete. NEVER returns the value."""
    payload = payload or {}
    raw = (payload.get("key") or payload.get("provider") or "").strip()
    value = payload.get("value")
    if not raw:
        return JSONResponse({"ok": False, "error": "missing key/provider"}, status_code=400)
    env_name = raw
    try:
        from config import doctor
        for c in doctor.CREDENTIALS:
            if c["key"] == raw and c.get("env"):
                env_name = c["env"][0]           # provider's main variable
                break
    except Exception:
        pass
    try:
        from config import credentials
        credentials.set_key(env_name, value or "")
        return JSONResponse({"ok": True, "key": raw, "env": env_name, "set": bool(value)})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)[:160]}, status_code=500)


@router.get("/api/config/benchmarks")
async def get_benchmarks():
    """CURATED read-only replica of model decisions — where each choice comes from, cost, latency, tool-calling/
    hallucination reliability, and which candidates were evaluated. See `config/model_benchmarks.py`."""
    try:
        from config import model_benchmarks
        return JSONResponse(model_benchmarks.snapshot())
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"modules": [], "error": str(e)[:160]})


@router.get("/api/config/apis")
async def get_apis(refresh: bool = False):
    """External API/service summary with BALANCE (proactive where exposed + reactive from last error). For the config
    summary and status-dialog alerts. `refresh=1` forces probing again."""
    try:
        from config import balances
        return JSONResponse({"apis": balances.summary_with_workers(refresh=refresh), "alerts": balances.alerts(refresh=refresh)})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"apis": [], "alerts": [], "error": str(e)[:120]})
