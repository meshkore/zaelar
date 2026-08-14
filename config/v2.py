"""config/v2.py — v2 «Colmena» configuration schema (ADDITIVE, INI V2-001).

Coexists with `config/settings.py` (⚙: STT/TTS/voice/language) and `config/connectors.py` without touching them —
nothing is deleted yet (Hermes/duo config cleanup is V2-009). The NEW v2 brain config lives here:

  - **model routing** — the FlashBrain model (fast non-reasoning layer) and the SlowBrain CodeAgent model.
    **Model PER INVOCATION** (hard rule): this stores DEFAULTS that the caller reads and passes for each invocation;
    NEVER a global model env var that forces every session at once.
  - **flags** — v2 deployment switches (memory, orchestrator loop…), for the strangler-fig strategy.

Like the rest of zaelar config: **the UI manages it**, it persists in `config/v2.json` (gitignored, carries
credentials), and the store WINS over `.env` (env = power-user/headless fallback). **REDACTED public view**: API keys
never reach the frontend → `<key>_set: bool`.
"""
import json
import os
import threading
from pathlib import Path

from nucleo import workspace as _workspace

# `<workspace>/config/v2.json` — unset `ZAELAR_WORKSPACE` is byte-identical to the old
# `Path(__file__).resolve().parent / "v2.json"`.
_PATH = _workspace.root() / "config" / "v2.json"
_lock = threading.Lock()

# Shape by section + defaults. Adding a capability = one entry here.
# NB: `*_model` values are DEFAULTS; the brain passes them PER INVOCATION (never a global model env var).
_DEFAULTS: dict[str, dict] = {
    # FlashBrain — fast non-reasoning layer (provider `nucleo`, V2-004). Non-reasoners only.
    "fast": {
        "provider": "aimlapi",                              # 'ollama' (local) | 'aimlapi' (cloud)
        # 2026-08-14 — DeepSeek V4 Flash through the AIMLAPI broker. The DIRECT endpoint (api.deepseek.com) was
        # wired and measured the same day and is **NOT the default**, deliberately, because it did not pass the gate.
        #
        # What direct buys (real voice prompt, 6 turns/arm) — the reasoning-off parameter
        # `thinking:{"type":"disabled"}` is accepted-and-IGNORED by the broker and OBEYED direct:
        #
        #                    TTFT p50   worst    reasoning tokens   routing (node 2.13, 14 cases)
        #   AIMLAPI            4.24s   14.71s        2138                14/14
        #   DIRECT             1.01s    1.30s           0                12/14  ← estilo, pregunta memoria
        #
        # So: 4.2x median latency and 11.3x worst case — the worst case being what the operator experiences as "it's
        # gone dumb" — against a 2-case routing regression on a SINGLE sample. The standing rule is «if node 2.13
        # drops, it does not ship», and it is not waived because the latency number is attractive. Routing errors are
        # the failure the operator called "conversaciones absurdas"; being fast at doing the wrong thing is worse.
        #
        # Direct is instead the FIRST latency-relay rung (provider_chain._voice_chain): when turn_perf reports two
        # slow turns in a row we relay to it, which is exactly what V2-094 exists for. So the cure is applied where
        # the problem shows up, without betting routing quality on n=1.
        # To promote it: run node 2.13 with 3 rounds against direct (it is a bench candidate now) and if it holds
        # 14/14, flip `base_url` here to https://api.deepseek.com and `model` to `deepseek-v4-flash`. See V2-097 §1.
        #
        # Superseded default: `anthropic/claude-haiku-4.5` (V2-034 A/B, 2026-07-12) — chosen over
        # grok-4-fast-non-reasoning, which "seems dumb". Haiku is still a valid choice on this same broker.
        # Still PER INVOCATION; changed via UI/config.
        "model": "deepseek/deepseek-v4-flash",              # default; passed per invocation
        "base_url": "",                                     # empty → the provider's own (AIMLAPI broker)
        "api_key": "",
    },
    # SlowBrain — headless code agent behind the CodeAgent interface (V2-006).
    # Model PER INVOCATION: `model` is the global default; `model_<kind>` allows a different model by task type
    # (memory/web/code) — empty = falls back to `model`, and empty `model` = provider default. The dispatcher READS
    # them and passes them in each `RunSpec` (never sets a global model env var).
    "code_agent": {
        "provider": "claude_code",                          # 'claude_code' | 'codex'
        "model": "",                                        # global default; empty = provider default
        "model_memory": "",                                 # MEMORY agent ★ (cheap/mechanical work)
        "model_web": "",                                    # web work agents (V2-007)
        "model_code": "",                                   # code work agents (V2-007)
        "api_key": "",
        # base_url: EXTERNAL Anthropic-compatible endpoint for `claude` workers (2026-07-31). Empty = the system's
        # normal Anthropic account. If it points at a compatible provider (e.g. Z.AI GLM coding plan, "one API to
        # use from Claude Code"), the worker uses it through ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN; the token is
        # resolved from the credential store by endpoint (z.ai → Z_AI_API_KEY), never from this JSON.
        "base_url": "",
        "max_parallel": 3,                                  # POOL: max concurrent Claude Code sessions (V2-036) —
        #                                                     avoid saturating machine/tokens; env CODE_AGENT_MAX_PARALLEL.
        # Explicit RELAY chain (2026-08-03): the operator manually orders primary→failover→failover (each one
        # {name, base_url, env|api_key, model, plan}). `nucleo.workers.providers.chain()` reads it if NOT empty;
        # empty (default) = usual behavior (base_url above + KNOWN catalog + local license).
        "providers": [],
    },
    # CLUSTER BRAIN chain (V2-069 "one mind", off-voice — `nucleo.flash.provider_chain`, 2026-08-03). Motivated by
    # the Z.AI 429 incident: a cluster turn (heartbeat/reply to a peer) had only ONE tier fixed at server boot
    # (`connectors/meshkore/brain.py`), without relay — once its quota was exhausted, the turn died and was retried
    # ALWAYS against the same broken provider. `providers` (empty = default) lets the operator manually set
    # primary→failover→failover ({name, base_url, env|api_key, model, plan}); empty = default chain built from
    # present credentials (direct Z.AI → AIMLAPI/DeepSeek → xAI → Groq), as before.
    "cluster": {
        "providers": [],
    },
    # Memory — RETRIEVAL models (embedding + reranker), MODEL-AGNOSTIC (V2-030). Same as `fast`/`code_agent`:
    # DEFAULTS that memory reads; local by default (self-sufficient with our GPU/CPU), ready for cloud/external APIs
    # by changing only the `*_provider`. Details in `zaelar-memory.md §Retrieval`.
    "memory": {
        # LONG-recall reranker (off-hot-path, fail-open). Moves the correct item from top-10 to top-1/3.
        # DEFAULT `local` (V2-030): jina-reranker-v2-multilingual en CPU sube recall@1 41.6→56.2% y recall@3
        # empata al techo OpenAI (68.7 vs 69.0%) — gratis, 100% local, sin GPU. `openai` = techo cloud opcional.
        "rerank_provider": "local",            # 'off' | 'local' (fastembed CPU, default) | 'openai' (LLM listwise) | 'cohere'/'voyage'
        "rerank_model": "",                    # empty = provider default (openai→gpt-4o-mini, local→bge-reranker-base)
        "rerank_base_url": "",                 # alternative OpenAI-compatible endpoint (empty = OpenAI)
        "rerank_top_n": 20,                    # nº de candidatos del tope que se reordenan
        "rerank_blend": 0.85,                  # peso del rerank vs score original (recencia/importancia)
        "rerank_api_key": "",                  # secret (redacted); empty = OPENAI_API_KEY from env
        # Memory embedding (Phase 3: abstraction; default remains local, without automatic re-embed).
        "embed_provider": "auto",              # 'auto' (ollama→fastembed→hash) | 'ollama' | 'fastembed' | 'voyage'/'openai' (cloud)
        "embed_model": "embeddinggemma",       # modelo de embedding; cambiarlo EXIGE re-embed (memory/reembed.py)
        "embed_api_key": "",                   # secret (redacted); cloud providers only
        # The write HEART (mem_processor): distills each turn into pills. It runs OFF-HOT-PATH (async queue) →
        # **voice does NOT pay its latency**, and READS use no LLM. That is why the choice axis is quality-vs-PRICE,
        # never speed: here a slow and cheap model is perfectly valid.
        #
        # **DEFAULT = `deepseek/deepseek-v4-flash` via AIMLAPI** (2026-08-09 round, benchmarks §12.3). Sweep of 21
        # commercial candidates × 34 cases × 4 axes (`tests/memory/e2e/bot/distiller_bench.py`), 3 passes over the
        # finalists. Replaces `gpt-4.1-mini` **on price at equal useful quality**: completeness 98.5% vs 98.9% (one
        # fact of difference, within noise), precision 100% vs 100% (neither ever pollutes a discard), and **$0.68
        # vs $1.516 per 1,000 turns → −55%**. Overrides the previous "memory = ALWAYS OpenAI" directive
        # (2026-07-17), which was made when the only measured cheap contender was gpt-4o-mini.
        #   · Layer/slot 94.4% vs incumbent 100% — its TWO only reproducible failures: loses "there are five of us"
        #     from a family enumeration (it saves the rest of the names) and does not mark `change=update` on a pure
        #     NEGATION ("I no longer work at X", where there is no new value to supersede with). Neither destroys
        #     already-saved data.
        #   · ⛔ `gpt-4o-mini` is even cheaper ($0.567) and was VETOED: with the allergy stated in ENGLISH it assigns
        #     `slot=operator.diet` (3/3 passes + 3/3 direct reproduction). A slot INVALIDATES everything previous
        #     with that slot → a future "now I am vegetarian" would erase the allergy. This is the exact error the
        #     prompt warns about, and in personal memory it is silent data loss, not a percentage point.
        #   · Fallback si AIMLAPI/DeepSeek cae: `google/gemini-2.5-flash` (96,7/100/100) → `openai/gpt-4.1-mini`.
        #   · SAME model in self-host and cloud (operator decision 2026-08-09: one commercial model that works in
        #     both places). The sites that set it by env in cloud —`engine/fly.accounts.toml` and
        #     `cloud/provisioner/src/machineConfig.js`— are synchronized with this default.
        #   · The LOCAL option (Ollama) remains available by pointing `mem_processor_base_url` to `localhost:11434`.
        "mem_processor_model": "deepseek/deepseek-v4-flash",     # empty = env MEM_PROCESSOR_MODEL or fallback
        "mem_processor_base_url": "https://api.aimlapi.com/v1",  # endpoint OpenAI-compatible; a Ollama = local
        "mem_processor_api_key": "",                     # secret (redacted); empty = PER-ENDPOINT key (AIMLAPI_KEY)
        # DEEP sleep «REM phase» (V2-056, memory/rem.py): daily LLM consolidation — synthesis of pill clusters into
        # high-level INSIGHTS (kind='insight', slot insight:<concept>, superseded by sleep). Fully off-hot-path
        # (triggered by the loop); model per task (router nucleo/memllm.py, key by endpoint). Synthesis benchmark
        # 2026-07-20 → see zaelar-model-benchmarks.md §12.2.
        # MODEL unchanged (§12.2 gave gpt-4.1-mini 100% and it has not been remeasured); what changes on 2026-08-09
        # is the ACCOUNT: from direct OpenAI to AIMLAPI, same as the HEART, for three concrete reasons:
        #   (1) REM **has no environment variable** (not in _ENV_MAP), so this default is the ONLY thing governing
        #       cloud — and there is no `OPENAI_API_KEY` among cloud secrets (the provisioner injects
        #       AIMLAPI/Z_AI/ELEVENLABS/XAI/MISTRAL/DEEPGRAM): pointed at OpenAI, deep sleep silently failed on
        #       every cloud machine.
        #   (2) one provider account for the whole memory module (the reason the HEART was already on AIMLAPI),
        #       instead of two invoices for two tasks in the same piece.
        #   (3) that direct OpenAI account is heavily rate-limited (429 with few calls in flight, 20s p50 measured
        #       in the §12.3 sweep) — a bad place for consolidation that processes batches.
        "rem_model": "deepseek/deepseek-v4-flash",
        "rem_base_url": "https://api.aimlapi.com/v1",
        "rem_api_key": "",                               # secret (redacted); empty = key by endpoint
        "rem_every_hours": 24,                           # deep-sleep cadence (min 1h)
    },
    # Messaging triage (WhatsApp/Telegram relevance classifier). ⚠️ Previously LOCAL (qwen2.5:3b) for PRIVACY
    # (nothing personal left the machine). The operator requested ZERO local execution (battery) → moved to
    # EXTERNAL; the personal message now DOES leave to the cloud (tradeoff explicitly accepted 2026-07-17). Simple
    # classification task (no tool-routing) → grok is fine and uses xAI credit. Configurable per piece.
    "triage": {
        "provider": "xai",
        "model": "grok-4.20-0309-non-reasoning",
        "base_url": "https://api.x.ai/v1",
        "api_key": "",                                    # secret (redacted); empty = XAI_API_KEY from env
    },
    # «Susurro» (V2-053) — off-hot-path conversational auditor: a POWERFUL model (here it CAN be a reasoner,
    # because it is OUTSIDE the voice path) receives conversation+events when there is FRICTION (complaint/
    # repetition/degraded turn/rail fail/stuck worker) and returns corrections from a CLOSED catalog (F1:
    # repair_say + finding). First-class kill switch: `enabled` (UI) + env ZAELAR_SUSURRO. Hard fail-open: no
    # key/timeout → nothing happens. NEVER modifies BRAIN RULES at runtime (V2-053 §3d invariant).
    "susurro": {
        "enabled": True,
        "provider": "aimlapi",
        # 2026-08-09 — through the BROKER, not direct OpenAI. Operator rule: one API account to manage (AIMLAPI);
        # Z.AI and Groq are separate and only where needed. The MODEL does not change (gpt-4.1-mini, same as before),
        # only the path — so there is no quality regression to measure. Extra reason: the direct OpenAI account is
        # heavily rate-limited (429 with few calls in flight, 20s p50 measured in the §12.3 sweep), which disguised
        # an endpoint issue as a "bad model". Benchmark §10 (choosing the Susurro model with data) is still pending.
        "model": "openai/gpt-4.1-mini",
        "base_url": "https://api.aimlapi.com/v1",
        "api_key": "",                          # secret (redacted); empty = resolved by endpoint (OPENAI_API_KEY…)
        "pulse_turns": 0,                       # 0 = friction only; N = also light audit every N turns
        "cooldown_s": 60,                       # minimum between audits (anti-burst)
        "window_turns": 8,                      # verbatim conversation turns in the audit window
        "recency_window_s": 120,                # only turns/events from this window enter the audit (anti-contamination)
    },
    # RESEARCH DIRECTOR (nucleo/research.py) — composes the BRIEF with which a Brain Worker executes a SELECTION
    # (hard/soft criteria separated, expert enrichments, minimum candidate breadth, quality rubric, deliverable
    # shape). Runs in the ASYNC pre-flight of escalation, never in the voice turn, so here it CAN reason. Empty =
    # goes through the reasoning-tier CHAIN (nucleo/flash/provider_chain.py), which also relays provider if the
    # primary runs out of quota; fill model+base_url only to PIN a concrete one. Fail-open: without a brief the
    # worker starts as before.
    "research": {
        "enabled": True,                        # first-class kill switch (UI) + env ZAELAR_RESEARCH=0
        "model": "",
        "base_url": "",
        "api_key": "",                          # secret (redacted); empty = key by endpoint
    },
    # v2 deployment flags. After Hermes' burial (V2-009), the default brain is «Colmena» itself.
    "flags": {
        "brain": "nucleo",                                  # active brain: 'nucleo' (own) · 'direct'/'local' (baselines)
        "memory_enabled": True,                             # memoria central (V2-002/003)
        "loop_enabled": True,                               # loop orquestador (V2-005)
    },
}

# Keys that are NEVER returned to the frontend (→ `<key>_set: bool`). Privacy fail-safe. Any key that ENDS in
# `api_key` (api_key/rerank_api_key/embed_api_key…) is redacted — no need to list them one by one.
# NB: use a literal, not builtins.set() — this module defines a `set()` function that would shadow it.
_SECRET_KEYS = {"api_key"}


def _is_secret(key: str) -> bool:
    return key in _SECRET_KEYS or key.endswith("api_key")

# FALLBACK env var by key (back-compat / power-user). Queried only if the store says nothing.
_ENV_FALLBACK = {
    ("fast", "provider"): "FAST_PROVIDER",
    ("fast", "model"): "FAST_MODEL",
    ("fast", "base_url"): "FAST_BASE_URL",
    ("fast", "api_key"): "FAST_API_KEY",
    ("code_agent", "provider"): "CODE_AGENT_PROVIDER",
    ("code_agent", "model"): "CODE_AGENT_MODEL",
    ("code_agent", "model_memory"): "CODE_AGENT_MODEL_MEMORY",
    ("code_agent", "model_web"): "CODE_AGENT_MODEL_WEB",
    ("code_agent", "model_code"): "CODE_AGENT_MODEL_CODE",
    ("code_agent", "api_key"): "CODE_AGENT_API_KEY",
    ("code_agent", "base_url"): "CODE_AGENT_BASE_URL",
    ("memory", "rerank_provider"): "MEMORY_RERANK",
    ("memory", "rerank_model"): "MEMORY_RERANK_MODEL",
    ("memory", "rerank_base_url"): "MEMORY_RERANK_BASE_URL",
    ("memory", "rerank_top_n"): "MEMORY_RERANK_TOP_N",
    ("memory", "rerank_blend"): "MEMORY_RERANK_BLEND",
    ("memory", "rerank_api_key"): "MEMORY_RERANK_KEY",
    ("memory", "embed_provider"): "ZAELAR_EMBED_BACKEND",
    ("memory", "embed_model"): "ZAELAR_EMBED_MODEL",
    ("memory", "mem_processor_model"): "MEM_PROCESSOR_MODEL",
    ("memory", "mem_processor_base_url"): "MEM_PROCESSOR_URL",
    ("memory", "mem_processor_api_key"): "MEM_PROCESSOR_KEY",
    ("triage", "provider"): "MSG_TRIAGE_PROVIDER",
    ("triage", "model"): "MSG_TRIAGE_MODEL",
    ("triage", "base_url"): "MSG_TRIAGE_URL",
    ("triage", "api_key"): "MSG_TRIAGE_KEY",
    ("susurro", "model"): "SUSURRO_MODEL",
    ("susurro", "base_url"): "SUSURRO_URL",
    ("susurro", "api_key"): "SUSURRO_KEY",
    ("susurro", "pulse_turns"): "SUSURRO_PULSE_TURNS",
    ("flags", "brain"): "BRAIN",
}


def _read() -> dict:
    with _lock:
        if _PATH.exists():
            try:
                data = json.loads(_PATH.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
    return {}


def _write(data: dict) -> None:
    with _lock:
        tmp = str(_PATH) + ".tmp"
        Path(tmp).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, _PATH)


def get(section: str) -> dict:
    """Effective config for a section (defaults + store + fallback env). Includes secrets → INTERNAL use."""
    base = dict(_DEFAULTS.get(section, {}))
    stored = _read().get(section, {}) or {}
    for k in base:
        if stored.get(k) not in (None, ""):
            base[k] = stored[k]
        elif (section, k) in _ENV_FALLBACK:
            env_val = os.getenv(_ENV_FALLBACK[(section, k)], "")
            if env_val:
                base[k] = env_val
    return base


def set(section: str, patch: dict) -> dict:
    """Apply a patch to a section (atomic read-modify-write). Only keys declared in _DEFAULTS."""
    if section not in _DEFAULTS:
        raise KeyError(f"config/v2: sección desconocida {section!r}")
    allowed = set_keys(section)
    data = _read()
    cur = dict(data.get(section, {}) or {})
    for k, v in (patch or {}).items():
        if k in allowed:
            cur[k] = v
    data[section] = cur
    _write(data)
    return get(section)


def set_keys(section: str) -> frozenset:
    # literal, NOT builtins.set() — the name `set` is shadowed by the function `set()` above.
    return frozenset(_DEFAULTS.get(section, {}).keys())


def public(section: str) -> dict:
    """REDACTED frontend view: secrets NEVER leave (→ `<key>_set: bool`)."""
    cfg = get(section)
    out = {}
    for k, val in cfg.items():
        if _is_secret(k):
            out[k + "_set"] = bool(val)
        else:
            out[k] = val
    return out


def public_all() -> dict:
    """All v2 config for the frontend, redacted. NEVER contains a cleartext API key."""
    return {s: public(s) for s in _DEFAULTS}


# ── brain convenience accessors (model PER INVOCATION) ───────────────────────────────────────────────────
def fast_model_spec() -> dict:
    """FlashBrain model selection to pass PER INVOCATION (sets no global env var)."""
    return get("fast")


def code_agent_spec() -> dict:
    return get("code_agent")


def code_agent_model(kind: str = "generic") -> str:
    """CodeAgent model for one task TYPE, to pass PER INVOCATION. Cascades:
    `model_<kind>` → `model` (global default) → "" (provider default). Never sets a global env var."""
    cfg = get("code_agent")
    per_kind = (cfg.get(f"model_{kind}") or "").strip()
    return per_kind or (cfg.get("model") or "").strip()


def external_worker_env() -> dict:
    """Env vars for a HEADLESS `claude` agent (brain worker or widget generator) to use the EXTERNAL
    Anthropic-compatible §code_agent endpoint (e.g. Z.AI GLM coding plan) instead of the system Claude
    account/license — so headless agents do NOT consume Claude Teams license tokens (operator rule 2026-07-31).
    Returns {} if `base_url` is not configured (→ normal behavior). SINGLE source for ALL repo `claude` spawns, so
    none are left out. Token is resolved from the credential store BY ENDPOINT (z.ai → `Z_AI_API_KEY`), NEVER from
    config JSON. Fail-open (any failure → {})."""
    try:
        cfg = get("code_agent")
        base = (cfg.get("base_url") or "").strip()
        if not base:
            return {}
        tok = (cfg.get("api_key") or "").strip()
        if not tok and "z.ai" in base.lower():
            tok = os.getenv("Z_AI_API_KEY", "")
        if not tok:
            # CONFIGURED base_url but no resolvable token → if we returned {}, the headless agent would silently
            # fall back to the Claude Teams license (exactly what the operator wants to avoid). Warn LOUDLY
            # (fail-loud).
            try:
                from loguru import logger
                logger.warning(f"code_agent.base_url={base!r} configurado pero SIN token resoluble "
                               "(¿falta Z_AI_API_KEY en el store?) → los brain workers caerían a la licencia "
                               "Claude Teams. Revisa credenciales.")
            except Exception:
                pass
            return {}
        # ANTHROPIC_API_KEY conviviendo con base_url ambigua al CLI → se quita en el consumidor tras aplicar esto.
        return {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_AUTH_TOKEN": tok}
    except Exception:
        return {}


def active_brain() -> str:
    """Selected brain for this run. SINGLE source after Hermes' burial (V2-009): it used to live in
    `brains/__init__.py`. Env-first (`BRAIN`, what `make run` sets = nucleo) → store `flags.brain` → default
    `nucleo`. Read AFTER `config.settings.load_into_env()` so live overrides are honored."""
    env = os.getenv("BRAIN")
    if env:
        return env.lower()
    return (get("flags").get("brain") or "nucleo").lower()
