"""config/profiles.py — PROFILE as a COORDINATED config package (V2-040).

Today "local vs cloud" is THREE disconnected switches: `voice/engine/core/profile.py` (`ZAELAR_PROFILE` → voice
engine STT/TTS/LLM), `config/v2.py` (brain routing + memory embed/rerank/HEART), and `config/settings.py`
(⚙ → ZAELAR_STT/TTS/LANGUAGE). Choosing "local" fixed voice but left embeddings/rerank/HEART/FlashBrain wherever
they were. This module UNIFIES them: profile name → the COMPLETE set of coordinated defaults across the three axes,
applicable in one step (`apply`).

**The profile only moves DEFAULTS.** Per-component override (env/UI) remains valid — that is what makes HYBRIDS
possible (e.g. `local` + a cloud FlashBrain on a weak machine). `apply` writes to the SAME stores as the UI
(`settings.json` + `v2.json`), so nothing is hardcoded in code and everything remains manually configurable
afterwards.

**No model name lives in this file (V2-824).** Both packages are READ from `config/models.default.json`: the
`cloud` profile from the services' titulars, the `local` profile from the table's `local` block. A copy of a
fact is a fact that will disagree — this module carried its own outdated local tags and a `fastembed` embedding
provider for a year after the table had moved on, and re-applying a profile wrote those stale values into the
operator's `config/v2.json` on every pass.

Two built-in profiles:
  - **local** — voice and memory ON THE MACHINE (whisper + kokoro + the table's local LLM for the FlashBrain and
    the memory HEART + the table's local embeddings + local rerank). Zero cloud keys for voice/memory. (The Brain
    Worker = coding-agent CLI still needs its auth.)
  - **cloud** — everything through cloud providers (the table's titulars: STT/TTS, FlashBrain, embeddings, HEART).
    Keys only, no local models. **= the default and the deploy target.** `remote` = ALIAS of `cloud`.
"""
from __future__ import annotations


# Profile → coordinated package. `voice` = what the engine sees (materialized as ZAELAR_* through settings.json).
# `v2` = patch by config/v2.py section. An EMPTY value means "provider default" (we do not force it).
#
# Every reader below fails SOFT on purpose: a profile that cannot be built must not take the wizard or the ⚙ down
# with it, and an empty dict simply leaves the live default alone — which is the safe side, since the live default
# comes from the same table.
def _row(kind: str, name: str) -> dict:
    """A titular (`kind="titular"`) or a `local` block entry, tolerant — and it SAYS what failed."""
    try:
        from config import models as _tabla
        return _tabla.titular(name) if kind == "titular" else _tabla.local(name)
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger("zaelar.config.profiles").warning(
            "profiles: models table %s «%s» unreadable (%s) — the profile leaves that default alone", kind, name, e)
        return {}


def _titular(service: str) -> dict:
    return _row("titular", service)


def _local(name: str) -> dict:
    return _row("local", name)


def _fast_from_table() -> dict:
    """The voice titular, straight from the table (V2-750 — READ, never copied: a hand-aligned copy drifted the
    moment the table moved and kept writing a two-versions-old model into the operator's `config/v2.json`)."""
    t = _titular("voice_brain")
    if not t:
        return {}
    return {"provider": t.get("provider", ""), "model": t.get("model", ""),
            "base_url": t.get("base_url", ""), "api_key": ""}


def _fast_local_from_table() -> dict:
    """The local LLM, from the table's `local` block, WITH its endpoint. ⚠️ `base_url` is not optional here, and
    its absence was a real latent bug until 2026-08-19: a profile that names a local model and leaves the endpoint
    wherever it was sends an Ollama tag to a cloud provider — HTTP 400 on every call, silently."""
    row = _local("llm")
    if not row:
        return {}
    return {"provider": row.get("provider", "ollama"), "model": row.get("model", ""),
            "base_url": row.get("base_url", ""), "api_key": ""}


def _memory_cloud_from_table() -> dict:
    """Embeddings = the table's titular (`services.embeddings`), the one space that exists identically on a laptop
    and in a container. The reranker follows its own row (OFF by default so local and cloud measure the same)."""
    emb = _titular("embeddings")
    rr = _titular("reranker")
    return {"embed_provider": emb.get("provider", "") or "openai", "embed_model": emb.get("model", ""),
            "embed_base_url": emb.get("base_url", ""),
            "rerank_provider": rr.get("provider", "") or "off",
            # empty = the table's `memory_writer` titular, which `config/v2.py` already reads
            "mem_processor_model": "", "mem_processor_base_url": ""}


def _memory_local_from_table() -> dict:
    """Memory on the machine: the local embeddings (another SPACE — applying this over an indexed database is a
    migration, see `apply`) and the local LLM as the HEART, with its endpoint (same trap as `_fast_local_from_table`).

    Ollama as the write titular is the operator's rule for a LOCAL install (2026-08-19), and it is safe to declare
    even on a machine that has never pulled the model: `nucleo/memllm.local_titular_ready` steps over a local
    titular that is not answering, so the write lands on the cloud stand-in instead of on the heuristic. TRADE-OFF
    worth knowing before choosing this profile: a local distiller runs on the SAME GPU as local STT/TTS and has been
    measured to cut the voice (15-29 s) — which is why it is a profile the operator picks, never a default."""
    emb = _local("embeddings")
    llm = _local("llm")
    return {"embed_provider": emb.get("provider", "") or "ollama", "embed_model": emb.get("model", ""),
            "embed_base_url": "",
            "rerank_provider": "local",
            "mem_processor_model": llm.get("model", ""),
            "mem_processor_base_url": llm.get("base_url", "")}


_PROFILES: dict[str, dict] = {
    "local": {
        "label": "Local · privado y gratis",
        "summary": "Voz y memoria en tu máquina (Ollama + modelos locales). Sin coste por token ni datos a la nube. "
                   "Ideal en Apple Silicon / GPU. El agente de código (SlowBrain) sí usa Claude.",
        "voice": {"stt_provider": "whisper_local", "tts_provider": "kokoro_local"},
        "v2": {
            "fast": _fast_local_from_table(),
            "memory": _memory_local_from_table(),
        },
        "engine_profile": "local",
    },
    "cloud": {
        "label": "Nube · sin instalar modelos",
        "summary": "Todo por proveedores de nube (STT/TTS/cerebro/memoria). No necesita GPU ni Ollama, solo tus "
                   "claves de API. Es el perfil del despliegue en servidor.",
        "voice": {"stt_provider": "deepgram", "tts_provider": "inworld"},
        "v2": {
            "fast": _fast_from_table(),
            "memory": _memory_cloud_from_table(),
        },
        "engine_profile": "remote",
    },
}
_ALIASES = {"remote": "cloud"}

# V2-671 — this used to be `"local"`, while `voice/engine/core/profile.py` defaulted the very same concept to
# `"remote"`. TWO defaults for one idea, in two files, and the disagreement was not theoretical: a factory
# reset dropped `wizard_done`, the first-run wizard fired, applied `local` because that was the recommendation
# on an Apple Silicon machine with Ollama running, and `apply()` rewrote settings.json AND v2.json together —
# so the operator's engine came back up on a local model instead of the table's titular, with the paid voice
# stack swapped underneath it. The checkbox that promised to preserve his install had preserved it for about
# twenty seconds.
#
# The default is now the CANONICAL TABLE's stack (`config/models.default.json`), which is the same in both
# deployments — that is the point of having one table. `local` stays a deliberate opt-in from the ⚙ for
# someone who wants models on their own machine, never something a detector decides for them.
DEFAULT = "cloud"

def _embedding_keys() -> tuple:
    """The keys of `§memory` whose change moves the EMBEDDING SPACE — derived from the section itself (every
    `embed_*` key that is not a secret), so a new one is covered the day it is declared. Writing any of them is
    not a config edit: it is a migration of every vector in the database (V2-824), through `reembed.migrate`."""
    from config import v2 as _v2
    return tuple(k for k in _v2.set_keys("memory") if k.startswith("embed_") and not k.endswith("api_key"))


EMBEDDING_KEYS = _embedding_keys()


def deployment() -> str:
    """WHERE this process runs — `cloud` when ZAELAR_USER_ID is set, `self_host` otherwise.

    The operator's rule (2026-09-11): *«el paso de si quiero una instalación local o remota es absurdo porque
    tú ya sabes si estás corriendo en el ordenador del cliente o la versión de la nube»*. He is right about the
    question and it is worth being precise about WHY, because the two things share a word: this function
    answers where the process runs, and the PROFILE answers which providers it uses. They are independent —
    a self-hosted engine on a laptop runs the cloud-provider profile perfectly well, and that is the default.
    The deployment is therefore never asked; it is read from the one thing that can tell, the env var a
    hosted deployment sets.
    """
    from nucleo import cloud_account
    return "cloud" if cloud_account.is_cloud_account() else "self_host"


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
    still win (stores are the layer the UI edits manually).

    If the profile moves the EMBEDDING space (`local` ↔ `cloud`), the memory is migrated through the one door
    (`memory/reembed.migrate`, V2-824): the vectors are recomputed in the new space and the signature resealed. A
    database with no vectors is only stamped. The report lands in `applied["embedding_migration"]`."""
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
    embedding_moved = False
    try:
        from config import v2
        before = {k: v2.get("memory").get(k) for k in EMBEDDING_KEYS}
        for section, patch in p["v2"].items():
            v2.set(section, patch)
        # the profile's default brain is always «Colmena» itself
        v2.set("flags", {"brain": "nucleo"})
        after = {k: v2.get("memory").get(k) for k in EMBEDDING_KEYS}
        embedding_moved = before != after
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

    # 4) the embedding SPACE moved → migrate the memory (synchronous: this is an operator gesture, not a turn)
    if embedding_moved:
        try:
            from memory import api as _memapi
            applied["embedding_migration"] = _memapi.migrate_embeddings(reason=f"profile {n}")
        except Exception as e:  # noqa: BLE001
            applied["embedding_migration"] = {"ok": False, "error": str(e)[:200]}

    return {"profile": n, "applied": applied}


def active() -> str:
    """Active config profile (the one applied last), from the store; default DEFAULT."""
    try:
        from config import settings
        return canon(settings.get("config_profile") or DEFAULT)
    except Exception:
        return DEFAULT
