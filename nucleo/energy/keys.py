"""nucleo/energy/keys.py — single source of truth for "given a base_url, which env var holds its API key?" (V2-098).

Before this module, the same substring→env-var mapping was reimplemented independently in
`nucleo/llm/fast_client.py`, `nucleo/mem_processor.py`, a since-retired auditor client and `nucleo/memllm.py` — and
had already drifted: that client and `memllm.py` only knew 4 endpoints, missing
gemini/mistral/z.ai/deepseek/moonshot entirely. Pointing either at one of the missing endpoints resolves the key
to `""`/`"local"` and fails auth SILENTLY (fail-open masks it) instead of erroring loudly. One list, everyone reads
it — a new endpoint gets added here once instead of in four places that can each forget it.

ROUTING POLICY: every LLM call goes to the provider's own DIRECT endpoint listed below — there is no broker. This
governs *which host to call*, never *whether to reason*: the memory tasks' routes carry a separate, explicit
per-task `disable_thinking` flag, because a model's benchmarked quality can assume reasoning-on (§12.3/§12.4 of
`zaelar-model-benchmarks.md`). Picking a host is a routing decision; touching `disable_thinking` is a separate,
benchmark-backed one — don't let one quietly relitigate the other.
"""
from __future__ import annotations

import os

# (substring to match in the lowercased base_url, env var name); the first match wins.
_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("openai.com", "OPENAI_API_KEY"),
    ("x.ai", "XAI_API_KEY"),
    ("groq.com", "GROQ_API_KEY"),
    ("mistral.ai", "MISTRAL_API_KEY"),
    ("z.ai", "Z_AI_API_KEY"),
    ("generativelanguage.googleapis.com", "GEMINI_API_KEY"),
    ("gemini", "GEMINI_API_KEY"),
    ("moonshot", "MOONSHOT_API_KEY"),
    ("deepseek.com", "DEEPSEEK_API_KEY"),
    # Voice (2026-10-23): read by the voice builders through SETTINGS, listed here so a mediated deployment's egress
    # credential stands in for them too (`llm_egress.stand_in_for_provider_keys`).
    ("deepgram.com", "DEEPGRAM_API_KEY"),
    ("elevenlabs.io", "ELEVENLABS_API_KEY"),
    ("inworld.ai", "INWORLD_API_KEY"),
    # The decision model (Jev, `nucleo/jev.py`): listed so mediated egress stands in for its key as well.
    ("typesafe.ai", "TYPESAFE_API_KEY"),
    # The search indexes (`search/providers`), so mediated egress stands in for their keys too.
    ("perplexity.ai", "PERPLEXITY_API_KEY"),
    ("search.brave.com", "BRAVE_API_KEY"),
    ("tavily.com", "TAVILY_API_KEY"),
    ("foursquare.com", "FOURSQUARE_SERVICE_KEY"),
    ("brightdata.com", "BRIGHTDATA_API_TOKEN"),
)


def key_for_endpoint(base_url: str, *, default: str = "") -> str:
    """Resolve the API key for a base_url by substring match, env-first. `default` is returned both when no
    endpoint matches AND when the matching env var is unset/empty — callers differ on whether that should stay
    `""` (fast_client, an explicit "no key") or `"local"` (mem_processor/memllm, an Ollama-compatible
    sentinel their HTTP client accepts as "any non-empty string")."""
    low = (base_url or "").lower()
    for needle, env_name in _ENDPOINTS:
        if needle in low:
            return os.getenv(env_name, "") or default
    return default
