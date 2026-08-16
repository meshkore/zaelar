"""nucleo/provider_keys.py — single source of truth for "given a base_url, which env var holds its API key?" (V2-098).

Before this module, the same substring→env-var mapping was reimplemented independently in
`nucleo/flash/fast_client.py`, `nucleo/mem_processor.py`, `nucleo/susurro/client.py` and `nucleo/memllm.py` — and
had already drifted: `susurro/client.py` and `memllm.py` only knew 4 endpoints (openai/xai/groq/aimlapi), missing
gemini/mistral/z.ai/deepseek/moonshot entirely. Pointing either at one of the missing endpoints resolves the key
to `""`/`"local"` and fails auth SILENTLY (fail-open masks it) instead of erroring loudly. One list, everyone reads
it — a new endpoint gets added here once instead of in four places that can each forget it.
"""
from __future__ import annotations

import os

# (substring to match in the lowercased base_url, env var name). Order matters: `aimlapi` must be checked first —
# the broker serves models under provider-shaped ids (e.g. "deepseek/deepseek-v4-flash") without those providers'
# own endpoints ever appearing in the URL, so there is no real ambiguity, but keeping the broker first documents
# that its check is deliberately not "just another endpoint".
_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("aimlapi", "AIMLAPI_KEY"),
    ("openai.com", "OPENAI_API_KEY"),
    ("x.ai", "XAI_API_KEY"),
    ("groq.com", "GROQ_API_KEY"),
    ("mistral.ai", "MISTRAL_API_KEY"),
    ("z.ai", "Z_AI_API_KEY"),
    ("generativelanguage.googleapis.com", "GEMINI_API_KEY"),
    ("gemini", "GEMINI_API_KEY"),
    ("moonshot", "MOONSHOT_API_KEY"),
    ("deepseek.com", "DEEPSEEK_API_KEY"),
)


def key_for_endpoint(base_url: str, *, default: str = "") -> str:
    """Resolve the API key for a base_url by substring match, env-first. `default` is returned both when no
    endpoint matches AND when the matching env var is unset/empty — callers differ on whether that should stay
    `""` (fast_client, an explicit "no key") or `"local"` (mem_processor/memllm/susurro, an Ollama-compatible
    sentinel their HTTP client accepts as "any non-empty string")."""
    low = (base_url or "").lower()
    for needle, env_name in _ENDPOINTS:
        if needle in low:
            return os.getenv(env_name, "") or default
    return default
