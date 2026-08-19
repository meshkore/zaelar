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

router = APIRouter()

# Sections of config/v2.json that pick a PROVIDER/model (as opposed to `flags`, which doesn't). In the
# cloud profile (ZAELAR_USER_ID set) these are centrally managed by the operator, not user-editable —
# see INI-019 addenda "Cambio B", 2026-08-05. Self-host is completely unaffected (is_cloud_account()
# is always False there) — this NEVER restricts the OSS product, only the hosted cloud accounts.
_CLOUD_LOCKED_V2_SECTIONS = frozenset({"fast", "code_agent", "memory", "triage", "susurro"})


# PROVIDER catalog per piece (hints for UI dropdowns). It is not exhaustive and does not force anything — the user
# can type a model/base_url manually; this only speeds up selection. Cloud vs local is marked.
_PROVIDER_CATALOG = {
    "fast": {                       # FlashBrain — NON-reasoner, per invocation
        # CLOSED ON PURPOSE (2026-08-12, operator rule): the FlashBrain model is CHOSEN from a list, not typed, and
        # the list only contains benchmark-approved choices. A bad model here does not throw a clean error: it gives
        # an agent that does the wrong thing (the grok veto exists exactly for that), which is indistinguishable from
        # a bug. Therefore excluded: `xai`/grok (VETOED in the voice layer — it misroutes memory questions and sends
        # research to `web_search`, re-measured §9.1.b), direct `openai` and `mistral` (the rule is ONE API account:
        # all commercial traffic goes through the AIMLAPI broker), and `zai` (reasoner → violates voice=non-reasoner).
        "providers": [
            # 2026-08-14 — DeepSeek DIRECT is the production default, and it is a separate entry from the broker on
            # purpose: same model, different behaviour. `thinking:{"type":"disabled"}` is accepted-and-ignored by
            # AIMLAPI and OBEYED here. Measured with the real voice prompt, 6 turns/arm: TTFT p50 4.24s → 1.01s,
            # worst case 14.71s → 1.30s, reasoning tokens 2138 → 0. This is the one exception to the "one API
            # account, everything through the broker" rule, and it earns it: the broker cannot turn the reasoning
            # off, and voice=non-reasoner is a hard invariant, not a preference.
            {"id": "deepseek", "label": "DeepSeek DIRECT (production default — the only one that truly stops reasoning)",
             "base_url": "https://api.deepseek.com", "key_env": "DEEPSEEK_API_KEY", "cloud": True,
             "models": ["deepseek-v4-flash", "deepseek-v4-pro"]},
            # `google/gemini-3.7-flash` (live 2026-08-14) is a CANDIDATE, NOT endorsed — and it goes here, on the
            # broker, because the broker DOES serve it (verified against `/models` and a real call). The first
            # version of this entry added OpenRouter as a new provider, which would have broken the "one API
            # account" rule and needed a credential we do not have, for a model we already had access to.
            # Why it needs measuring before anything else: the reason it looks attractive is the reason to be
            # careful. Gemini Flash has always been fast here and has always routed WORSE — in this very bench
            # gemini-3.6-flash scores 6/14 and gemini-3.5-flash 8/14, against deepseek's 14/14, mostly by not
            # invoking tools at all. Reasoning-off knob is `reasoning_effort:"none"`, already sent by
            # `ModelSpec.reasoning_effort()` for Gemini endpoints. Gate: node 2.13. See V2-097 §4.
            {"id": "aimlapi", "label": "AIMLAPI (broker — the one account we manage)",
             "base_url": "https://api.aimlapi.com/v1", "key_env": "AIMLAPI_KEY", "cloud": True,
             "models": ["deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash",
                        "google/gemini-3.7-flash"]},
            {"id": "groq", "label": "Groq (cloud, fastest — routes worse)",
             "base_url": "https://api.groq.com/openai/v1", "key_env": "GROQ_API_KEY", "cloud": True,
             "models": ["llama-3.3-70b-versatile"]},
            {"id": "ollama", "label": "Ollama (local/free — slow, offline fallback)",
             "base_url": "http://localhost:11434/v1", "key_env": "", "cloud": False,
             "models": ["qwen2.5:14b-instruct"]},
        ],
        "closed_models": True,      # the UI renders a dropdown, not a text field
        "note": "NON-reasoners only (the voice turn must close fast) and only benchmark-endorsed ones. "
                "deepseek-v4-pro DIRECT = production default (operator's norm, 2026-08-19: it is the titular and "
                "the only endpoint that actually obeys `thinking:disabled`). deepseek-v4-flash routed 12/12 in "
                "§9. The broker entries carry the `deepseek/` prefix and the direct ones do not — that is the "
                "provider's catalog, not a typo. Endpoint comes from the provider: there is no URL to type.",
    },
    "code_agent": {                 # Brain Workers — the headless agent that DRIVES tasks
        # REAL models per provider (2026-08-12). This list used to be EMPTY for both, so the UI rendered a free
        # field: the operator switched to Codex and the previous provider's `glm-5.2` values remained — a model
        # Codex does not serve — and the task died with "There's an issue with the selected model". A provider may
        # only offer ITS models.
        "providers": [
            {"id": "claude_code", "label": "Claude Code (CLI)", "cloud": True,
             # TWO families, and both are legitimate for THIS provider: the own-license aliases, and the
             # Anthropic-compatible RELAY rung models (`workers/providers.py`), because Claude Code still drives —
             # only the endpoint underneath changes. Leaving relay models out would mark the operator's working
             # TODAY config as invalid (claude_code + glm-5.2 + Z.AI endpoint), and that config is correct.
             # glm-5.3 (live 2026-08-14) VERIFIED against the real coding-plan endpoint. Two things worth knowing,
             # both measured: (1) asking for `glm-5.2` already returns `model: "glm-5.3"` — the plan upgraded under
             # us, so the old value was describing something that no longer ran; (2) the endpoint DOES validate the
             # name (an invented model gets error 1214), so this is an alias, not a free-for-all. `glm-5.2` stays
             # listed because it is still accepted. NOTE: 5.3 is a REASONER (its first content block is `thinking`)
             # — fine for workers, never for the voice layer.
             "models": ["opus", "sonnet", "sonnet[1m]", "opus[1m]",
                        "glm-5.3", "glm-5.2", "glm-4.6", "kimi-k2.6"],
             "note": "Can restrict Bash to our bridges only (single-writer invariant) → the only backend valid for "
                     "untrusted input (deny_tools) and cluster dev workers. The glm-*/kimi-* entries belong to the "
                     "relay tiers (Z.AI / Moonshot subscription plans): they only work while that endpoint is the "
                     "active tier — see workers/providers.py."},
            {"id": "codex", "label": "Codex (CLI)", "cloud": True,
             # VERIFIED against the list returned by the model server itself (2026-08-12): these are the three.
             # There is no 5.6 family available — a `gpt-5.6-*` in config.toml is not served by the API.
             "models": ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini"],
             "note": "Has NO tool allowlist — only sandbox modes, so a Codex worker runs a full shell "
                     "(wider blast radius). Refused for untrusted input and dev workers."},
            {"id": "grok_build", "label": "Grok Build (CLI)", "cloud": True, "key_env": "XAI_API_KEY",
             # VERIFIED with `grok models` against the real account (2026-08-13).
             "models": ["grok-4.5", "grok-4.6", "grok-build-0.1", "grok-4.3",
                        "grok-4.20-0309-non-reasoning"],
             "note": "Same wire format AND same allowlist syntax as Claude Code — verified it enforces "
                     "`--deny Bash(...)`, so it CAN hold the single-writer invariant (unlike Codex). "
                     "Pay-per-token: watch the cost, a trivial turn already costs ~$0.03 (large system prompt)."},
        ],
        "closed_models": True,
        # PRESETS (2026-08-13, operator request): a Brain Worker option is not "a provider"; it is the COMBINATION
        # of who drives (the CLI) and who reasons underneath (the endpoint + its model). Picking the three pieces by
        # hand is where mismatches happened (`glm-5.2` on Codex, `gpt-5.5` on Z.AI): a preset moves them TOGETHER in
        # one step. The operator can still fine-tune manually afterwards.
        "presets": [
            {"id": "cc_zai", "label": "Claude Code + Z.AI (GLM-5.2)", "provider": "claude_code",
             "base_url": "https://api.z.ai/api/anthropic", "model": "glm-5.2", "key_env": "Z_AI_API_KEY",
             "billing": "subscription", "cost": "GLM coding plan (flat rate)",
             "note": "The operator's rule: subscription plans, never pay-per-token. Quota is WEEKLY and when it "
                     "runs out everything on this tier dies at once — that is what the relay chain exists for."},
            {"id": "cc_deepseek", "label": "Claude Code + DeepSeek V4", "provider": "claude_code",
             "base_url": "https://api.deepseek.com/anthropic", "model": "deepseek-v4-flash",
             "key_env": "DEEPSEEK_API_KEY",
             "billing": "per_token", "cost": "~$0.14/$0.28 per Mtok (v4-flash)",
             "note": "⚠️ Its gateway does NOT map Claude aliases — that belief is what shipped this rung broken. "
                     "Verified against the live endpoint: a Claude alias gets `400 — The supported API model names "
                     "are deepseek-v4-pro or deepseek-v4-flash`. Use the DeepSeek name. Compatible in the PROTOCOL "
                     "is not compatible in the CATALOG. Cheapest of the three."},
            {"id": "grok45", "label": "Grok Build + Grok 4.5", "provider": "grok_build",
             "base_url": "", "model": "grok-4.5", "key_env": "XAI_API_KEY",
             "billing": "per_token", "cost": "pay-per-token — measured ~$0.03 for a trivial turn",
             "note": "Native xAI agent CLI. Grok 4.6 ($2/$6 per Mtok, 500k ctx, reasoning) is selectable as the "
                     "model if quality beats cost."},
            {"id": "cc_local", "label": "Claude Code + local licence", "provider": "claude_code",
             "base_url": "", "model": "", "key_env": "",
             "billing": "licence", "cost": "the operator's own Claude licence",
             "note": "LOCAL ONLY — a browser login does not exist inside a container, so this tier cannot be the "
                     "cloud's coverage. It is the last rung of the relay chain."},
        ],
        "note": "Headless agent that drives tasks (memory/web/code). Per-task-type model optional. "
                "Each provider serves ONLY its own models. Pick a preset to move CLI + endpoint + model together.",
    },
    "memory_processor": {           # write HEART (mem_processor / pill distiller)
        "providers": [
            {"id": "aimlapi", "label": "AIMLAPI (broker — the one account we manage)",
             "base_url": "https://api.aimlapi.com/v1", "key_env": "AIMLAPI_KEY", "cloud": True,
             "models": ["deepseek/deepseek-v4-flash", "google/gemini-2.5-flash", "openai/gpt-4.1-mini"]},
            {"id": "ollama", "label": "Ollama (local — only if local usage is accepted)", "base_url": "http://localhost:11434/v1",
             "key_env": "", "cloud": False, "models": ["qwen2.5:7b-instruct", "qwen2.5:3b"]},
        ],
        # Updated 2026-08-09: the previous label ("RULE: memory ALWAYS OpenAI") was OVERRULED by benchmark §12.3
        # and by the single-API-account rule. Choose with data, not by provider reputation.
        "note": "Off-hot-path (does not touch voice latency) but WRITE-COMPLETENESS is the nº1 lever of recall. "
                "BENCHMARKED 2026-08-09 (21 candidates × 34 cases, see zaelar-model-benchmarks.md §12.3): "
                "deepseek-v4-flash ties gpt-4.1-mini on capture (98.5 vs 98.9%) and precision (100%) for −55% cost "
                "→ CHOSEN; fallback gemini-2.5-flash → gpt-4.1-mini. ⛔ gpt-4o-mini is VETOED: it files an allergy "
                "under slot=operator.diet, and a slot invalidates every earlier pill with that slot — a later diet "
                "change would erase the allergy. Everything goes through the AIMLAPI broker (one account).",
    },
    "triage": {                     # messaging classifier (WhatsApp/Telegram relevance)
        "providers": [
            {"id": "xai", "label": "xAI grok (cheap, uses existing credit)", "base_url": "https://api.x.ai/v1",
             "key_env": "XAI_API_KEY", "cloud": True, "models": ["grok-4.20-0309-non-reasoning"]},
            {"id": "openai", "label": "OpenAI", "base_url": "https://api.openai.com/v1",
             "key_env": "OPENAI_API_KEY", "cloud": True, "models": ["gpt-4o-mini"]},
            {"id": "ollama", "label": "Ollama (local — PRIVATE, nothing leaves the machine)", "base_url": "http://localhost:11434/v1",
             "key_env": "", "cloud": False, "models": ["qwen2.5:3b"]},
        ],
        "note": "⚠️ PRIVACY: in external mode, personal messages LEAVE to the cloud (that is why it used to be local). "
                "Simple classification task (no tool-routing) → grok is fine. Operator accepted the tradeoff (battery).",
    },
    "susurro": {                    # «Susurro» (V2-053) — off-hot-path conversational auditor
        "providers": [
            {"id": "aimlapi", "label": "AIMLAPI (broker — the one account we manage)",
             "base_url": "https://api.aimlapi.com/v1", "key_env": "AIMLAPI_KEY", "cloud": True,
             "models": ["openai/gpt-4.1-mini", "openai/gpt-4.1",
                        "deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash"]},
            {"id": "xai", "label": "xAI grok", "base_url": "https://api.x.ai/v1",
             "key_env": "XAI_API_KEY", "cloud": True, "models": ["grok-4.20-0309-non-reasoning"]},
            {"id": "off", "label": "Disabled (enabled=false)", "cloud": False},
        ],
        "note": "Audits stretches with FRICTION (complaint/repetition/failure) and returns structured corrections. "
                "OUTSIDE the voice path → here a reasoner IS worth it (benchmark §10 pending). "
                "pulse_turns=0 → friction only; N → also every N turns.",
    },
    "memory_embed": {
        "providers": [
            {"id": "auto", "label": "Auto (ollama→fastembed→hash)", "cloud": False},
            {"id": "ollama", "label": "Ollama (local)", "cloud": False, "models": ["embeddinggemma", "bge-m3"]},
            {"id": "fastembed", "label": "fastembed (local CPU)", "cloud": False},
            {"id": "openai", "label": "OpenAI (cloud)", "cloud": True, "key_env": "OPENAI_API_KEY"},
            {"id": "voyage", "label": "Voyage (cloud)", "cloud": True, "key_env": "VOYAGE_API_KEY"},
        ],
        "note": "Changing the embedding REQUIRES re-embed (memory/reembed.py). Local by default.",
    },
    "memory_rerank": {
        "providers": [
            {"id": "local", "label": "Local (jina, CPU/free)", "cloud": False},
            {"id": "openai", "label": "OpenAI (listwise, cloud)", "cloud": True, "key_env": "OPENAI_API_KEY"},
            {"id": "cohere", "label": "Cohere (cloud)", "cloud": True, "key_env": "COHERE_API_KEY"},
            {"id": "voyage", "label": "Voyage (cloud)", "cloud": True, "key_env": "VOYAGE_API_KEY"},
            {"id": "off", "label": "Disabled", "cloud": False},
        ],
        "note": "Reorders LONG recall (off-hot-path). Local raises recall@1 at no cost.",
    },
}


def _detected_code_agents() -> dict:
    """Which Brain Worker CLI is installed on THIS machine, and with which default version/model?

    This exists because the UI offered both providers equally without checking whether the binary was present: the
    operator picked Codex, saved, and the failure appeared minutes later inside a dead task. Choosing a provider that
    is not installed must be visible BEFORE saving, in the dropdown itself.

    Cheap (local `--version`) and NEVER raises: if detection fails, the UI simply marks nothing."""
    det: dict = {}
    try:
        from nucleo.workers import codex_session as _cx
        det["codex"] = _cx.detect()
    except Exception:
        det["codex"] = {"installed": False}
    try:
        import subprocess

        from nucleo.workers import claude_session as _cc
        path = _cc._find_claude()
        det["claude_code"] = {"installed": bool(path), "path": path, "version": "", "default_model": ""}
        if path:
            # Show the version HERE too. Codex and Grok showed it while Claude Code did not, so in the panel the
            # PRODUCTION provider was the only one without a badge — exactly the asymmetry that makes you doubt
            # whether it was really detected. `claude --version` answers "2.1.212 (Claude Code)": the first token is
            # the version.
            try:
                r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=8)
                det["claude_code"]["version"] = ((r.stdout or r.stderr or "").strip().split() or [""])[0]
            except Exception:
                pass
    except Exception:
        det["claude_code"] = {"installed": False}
    try:
        from nucleo.workers import grok_session as _gk
        det["grok_build"] = _gk.detect()
    except Exception:
        det["grok_build"] = {"installed": False}
    return det


def _catalog_for_ui() -> dict:
    """The catalog with CLI detection INJECTED into each `code_agent` provider (shallow copy: the module catalog is
    a constant and is not mutated)."""
    cat = dict(_PROVIDER_CATALOG)
    try:
        det = _detected_code_agents()
        ca = dict(cat["code_agent"])
        provs = []
        for p in ca.get("providers", []):
            p = dict(p)
            d = det.get(p["id"]) or {}
            p["detected"] = bool(d.get("installed"))
            if d.get("version"):
                p["version"] = d["version"]
            # A default already used by the CLI beats anything we would choose — BUT only if that model exists. The
            # real case motivating this guard: `~/.codex/config.toml` requested `gpt-5.6-sol`, which the API does
            # not serve for this account; using it as the default would have proposed a model in the UI that was
            # doomed to fail, while silently discarding it would have hidden that the config points at something
            # nonexistent.
            dm = d.get("default_model") or ""
            if dm:
                if dm in (p.get("models") or []):
                    p["default_model"] = dm
                else:
                    p["stale_default"] = dm
            provs.append(p)
        ca["providers"] = provs
        # PRESETS: each one is marked READY or not, and why. A preset that cannot work (missing CLI or missing key)
        # must be visible BEFORE selection: choosing it blindly is what produced a dead task with no apparent
        # relation to what the operator had saved.
        import os as _os
        pres = []
        for p in ca.get("presets", []):
            p = dict(p)
            d = det.get(p["provider"]) or {}
            cli_ok = bool(d.get("installed"))
            env = p.get("key_env") or ""
            key_ok = (not env) or bool((_os.getenv(env) or "").strip())
            p["cli_ok"], p["key_ok"], p["ready"] = cli_ok, key_ok, bool(cli_ok and key_ok)
            p["blocked_by"] = ("cli" if not cli_ok else ("key" if not key_ok else ""))
            pres.append(p)
        ca["presets"] = pres
        cat["code_agent"] = ca
    except Exception:
        pass
    return cat


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
        from nucleo import cloud_account
        out["cloud_profile"] = cloud_account.is_cloud_account()
    except Exception:
        out["cloud_profile"] = False
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
    open section) still accepts whatever the caller sends — this validates, it does not lock in."""
    conf = _PROVIDER_CATALOG.get(section) or {}
    if not conf.get("closed_models"):
        return ""
    prov_id = str(patch.get("provider") or "").strip()
    if not prov_id:
        return ""
    prov = next((p for p in conf.get("providers", []) if p.get("id") == prov_id), None)
    if prov is None:
        return f"unknown provider «{prov_id}» for {section}"
    allowed = set(prov.get("models") or [])
    if not allowed:
        return ""
    for field in _MODEL_FIELDS.get(section, ()):
        val = str(patch.get(field) or "").strip()
        if val and val not in allowed:
            return (f"«{val}» is not served by {prov.get('label') or prov_id} (field {field}). "
                    f"Available: {', '.join(sorted(allowed))}")
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
            from nucleo import cloud_account
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


# ── Connectors (V2-083) — single registry + control for those authenticated by dynamic TOKEN ────────────────
@router.get("/api/connectors")
async def get_connectors():
    """SINGLE connector inventory (messaging/music/infra) with status + REDACTED config — for the Connectors tab.
    Writes go through each family's endpoints (`/api/messaging/*`, `/api/spotify/*`, `/api/meshkore/*`) plus the
    architect endpoints below."""
    try:
        from connectors import registry
        return JSONResponse({"connectors": registry.descriptors()})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"connectors": [], "error": str(e)[:160]})


@router.post("/api/connectors/architect/connect")
async def architect_connect(payload: dict):
    """Set the Architect daemon TOKEN (and optional URL) in the DYNAMIC store (config/connectors.json), NOT in .env —
    configurable/revocable from the UI. The token is secret (redacted on read)."""
    from config import connectors as cfg
    tok = str((payload or {}).get("token") or "").strip()
    if not tok:
        return JSONResponse({"ok": False, "error": "empty token"}, status_code=400)
    patch = {"token": tok, "enabled": True}
    url = str((payload or {}).get("url") or "").strip()
    if url:
        patch["url"] = url
    cfg.set("architect", patch)
    return JSONResponse({"ok": True, "id": "architect", "config": cfg.public("architect")})


@router.post("/api/connectors/architect/disconnect")
async def architect_disconnect():
    """REVOKE the Architect token (delete it from the store). Leaves the connector disconnected."""
    from config import connectors as cfg
    cfg.set("architect", {"token": "", "enabled": False})
    return JSONResponse({"ok": True, "id": "architect", "config": cfg.public("architect")})
