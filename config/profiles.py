"""config/profiles.py — PROFILE as a COORDINATED config package (V2-040).

Today "local vs cloud" is THREE disconnected switches: `voice/engine/core/profile.py` (`ZAELAR_PROFILE` → voice
engine STT/TTS/LLM), `config/v2.py` (brain routing + memory embed/rerank/HEART), and `config/settings.py`
(⚙ → ZAELAR_STT/TTS/LANGUAGE). Choosing "local" fixed voice but left embeddings/rerank/HEART/FlashBrain wherever
they were. This module UNIFIES them: profile name → the COMPLETE set of coordinated defaults across the three axes,
applicable in one step (`apply`).

**The profile only moves DEFAULTS.** Per-component override (env/UI) remains valid — that is what makes HYBRIDS
possible (e.g. `local` + `ZAELAR_LLM_PROVIDER=aimlapi` on a weak machine). `apply` writes to the SAME stores as the
UI (`settings.json` + `v2.json`), so nothing is hardcoded in code and everything remains manually configurable
afterwards.

Two built-in profiles:
  - **local** — voice and memory ON THE MACHINE (whisper + kokoro + Ollama FlashBrain + Ollama embeddings + local
    rerank + local HEART). Zero cloud keys for voice/memory. (SlowBrain = `claude` CLI still needs its auth.)
  - **cloud** — everything through cloud providers (voxtral/deepgram + cartesia/elevenlabs + AIMLAPI FlashBrain +
    cloud embed/rerank/proc). Keys only, no local models. **= deploy target.** `remote` = ALIAS of `cloud`.
"""
from __future__ import annotations

# Profile → coordinated package. `voice` = what the engine sees (materialized as ZAELAR_* through settings.json).
# `v2` = patch by config/v2.py section. An EMPTY value means "provider default" (we do not force it).
_PROFILES: dict[str, dict] = {
    "local": {
        "label": "Local · privado y gratis",
        "summary": "Voz y memoria en tu máquina (Ollama + modelos locales). Sin coste por token ni datos a la nube. "
                   "Ideal en Apple Silicon / GPU. El agente de código (SlowBrain) sí usa Claude.",
        "voice": {"stt_provider": "whisper_local", "tts_provider": "kokoro_local"},
        "v2": {
            "fast": {"provider": "ollama", "model": "qwen2.5:14b-instruct", "base_url": "", "api_key": ""},
            # ⚠️ `mem_processor_base_url` is NOT optional here, and its absence was a real latent bug until
            # 2026-08-19: this profile set a LOCAL model name and left the endpoint untouched, so picking «Local»
            # while the endpoint pointed at a cloud provider sent `qwen2.5:7b-instruct` to DeepSeek — HTTP 400 on
            # every write, every turn silently on the lossy regex heuristic. A profile is a COORDINATED package;
            # naming a model without its endpoint is the same "compatible in the protocol, not in the catalogue"
            # trap the provider rule warns about.
            #
            # Ollama as the write titular is the operator's rule for a LOCAL install (2026-08-19), and it is safe to
            # declare here even on a machine that has never pulled the model: `nucleo/memllm.local_titular_ready`
            # steps over a local titular that is not answering, so the write lands on DeepSeek V4 Flash direct
            # instead of on the heuristic. TRADE-OFF worth knowing before choosing this profile: a local distiller
            # runs on the SAME GPU as local STT/TTS and has been measured to cut the voice (15-29 s) — which is why
            # it is a profile the operator picks, never a default.
            "memory": {"embed_provider": "ollama", "embed_model": "embeddinggemma",
                       "rerank_provider": "local",
                       "mem_processor_model": "qwen2.5:7b-instruct",
                       "mem_processor_base_url": "http://localhost:11434/v1"},
        },
        "engine_profile": "local",
    },
    "cloud": {
        "label": "Nube · sin instalar modelos",
        "summary": "Todo por proveedores de nube (STT/TTS/cerebro/memoria). No necesita GPU ni Ollama, solo tus "
                   "claves de API. Es el perfil del despliegue en servidor.",
        "voice": {"stt_provider": "deepgram", "tts_provider": "elevenlabs"},
        "v2": {
            # Named a two-versions-old model until 2026-08-19, which stopped being the titular on 2026-08-02, so
            # anyone who picked this profile in the wizard was silently overwriting the live default with a
            # two-versions-old model — a profile is a shortcut to the RECOMMENDED setup, and one that ships a stale
            # model is worse than one that ships nothing.
            #
            # ⚠️ It is DELIBERATELY the broker and not `api.deepseek.com`, even though the standing provider rule
            # (2026-08-19) puts the direct endpoint first and `config/v2.py §fast` now defaults to it. Reason: a
            # profile WRITES `config/v2.json`, the store WINS over env (`config/v2.py::get`), and a cloud Machine
            # gets its endpoint from env — `fly.accounts.toml` pins `FAST_*` to the broker there because the direct
            # endpoint's key is not among the cloud's provider secrets. So on the very deployment this profile is
            # named after, writing the direct endpoint would OVERRIDE the working env with an endpoint that has no
            # credential. The rule picks the order when both are reachable; here only one is.
            "fast": {"provider": "aimlapi", "model": "deepseek/deepseek-v4-flash", "base_url": "", "api_key": ""},
            "memory": {"embed_provider": "fastembed", "embed_model": "",
                       "rerank_provider": "local", "mem_processor_model": ""},
        },
        "engine_profile": "remote",
    },
}
_ALIASES = {"remote": "cloud"}

DEFAULT = "local"


def names() -> list[str]:
    return list(_PROFILES)


def canon(name: str) -> str:
    """Normalize a profile name (aliases included). An UNKNOWN name does not silently degrade: it falls back to
    DEFAULT with a warning to the caller (which may log it) — unlike old `ZAELAR_PROFILE`, which silently fell back
    to remote."""
    n = (name or "").strip().lower()
    n = _ALIASES.get(n, n)
    return n if n in _PROFILES else DEFAULT


def get(name: str) -> dict:
    return dict(_PROFILES[canon(name)])


def _no_secrets(d: dict) -> dict:
    """Remove secret fields (ending in api_key) from the dict — the package does not carry them (they are empty), but
    not even the field NAME reaches the frontend (same redaction convention as config/v2.public)."""
    return {k: v for k, v in d.items() if not k.endswith("api_key")}


def public() -> list[dict]:
    """Profiles for the frontend (name + label + summary + which providers it sets). No secret fields."""
    out = []
    for n, p in _PROFILES.items():
        out.append({"name": n, "label": p["label"], "summary": p["summary"],
                    "voice": p["voice"], "fast": _no_secrets(p["v2"]["fast"]), "memory": p["v2"]["memory"]})
    return out


def requirements(name: str) -> dict:
    """What this profile needs to work — so the wizard can show the GAPS. Returns:
      {needs_ollama, ollama_models, needs_local_accel, credentials:[keys relevantes], claude_cli}
    Everything is derived from the profile package itself (there is no separate list that could diverge)."""
    p = get(name)
    n = canon(name)
    fast = p["v2"]["fast"]
    mem = p["v2"]["memory"]
    models: list[str] = []
    if fast.get("provider") == "ollama" and fast.get("model"):
        models.append(fast["model"])
    if mem.get("embed_provider") == "ollama" and mem.get("embed_model"):
        models.append(mem["embed_model"])
    if (mem.get("mem_processor_model") or "").strip() and n == "local":
        models.append(mem["mem_processor_model"])
    needs_ollama = bool(models)
    # profile-relevant credentials (from the doctor catalog)
    creds: list[str] = []
    try:
        from config.doctor import CREDENTIALS
        creds = [c["key"] for c in CREDENTIALS if n in c.get("profiles", [])]
    except Exception:
        pass
    return {
        "profile": n,
        "needs_ollama": needs_ollama,
        "ollama_models": sorted(set(models)),
        "needs_local_accel": n == "local",
        "credentials": creds,
        "needs_claude_cli": True,     # the SlowBrain/widget generator uses `claude` in BOTH profiles
    }


def apply(name: str) -> dict:
    """Apply the profile to STORES (settings.json + v2.json) — one coordinated lever. Does NOT touch secrets (keys
    are managed separately). Returns `{profile, applied}`. Idempotent. Per-component overrides the user sets AFTER
    still win (stores are the layer the UI edits manually)."""
    n = canon(name)
    p = _PROFILES[n]
    applied: dict = {}

    # 1) VOICE axis → config/settings.py (which in turn writes ZAELAR_STT/TTS to os.environ and persists)
    try:
        from config import settings
        res = settings.update(dict(p["voice"]))
        applied["voice"] = {"ok": res.get("ok"), "keys": list(p["voice"].keys()),
                            "needs_reconnect": res.get("needs_reconnect")}
    except Exception as e:  # noqa: BLE001
        applied["voice"] = {"ok": False, "error": str(e)[:200]}

    # 2) ROUTING/MEMORY axis → config/v2.py (by section; declared keys only, whitelisted by v2.set)
    try:
        from config import v2
        for section, patch in p["v2"].items():
            v2.set(section, patch)
        # the profile's default brain is always «Colmena» itself
        v2.set("flags", {"brain": "nucleo"})
        applied["v2"] = {"ok": True, "sections": list(p["v2"].keys()) + ["flags"]}
    except Exception as e:  # noqa: BLE001
        applied["v2"] = {"ok": False, "error": str(e)[:200]}

    # 3) ENGINE axis → ZAELAR_PROFILE (affects frozen dataclass defaults; applies on next boot).
    #    Persist it as a settings knob so `load_into_env` reapplies it on boot.
    try:
        from config import settings
        settings._write({**settings._read(), "zaelar_profile": p["engine_profile"], "config_profile": n})
        import os
        os.environ["ZAELAR_PROFILE"] = p["engine_profile"]
        applied["engine_profile"] = p["engine_profile"]
    except Exception as e:  # noqa: BLE001
        applied["engine_profile"] = {"error": str(e)[:200]}

    return {"profile": n, "applied": applied}


def active() -> str:
    """Active config profile (the one applied last), from the store; default DEFAULT."""
    try:
        from config import settings
        return canon(settings.get("config_profile") or DEFAULT)
    except Exception:
        return DEFAULT
