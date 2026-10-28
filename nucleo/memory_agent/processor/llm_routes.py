"""The off-hot-path LLM tasks' ROUTES, as data: each task's titular and its ONE stand-in (V2-056, V2-750).

Every entry is `(base_url, model, disable_thinking)`. `disable_thinking` is a PER-TASK decision, never inferred from
the endpoint: a task asking for STRICT JSON under a long instruction makes a reasoner burn its whole `max_tokens`
and return an EMPTY 200 (measured on `paraphrase`: content '' at every budget tried), and moving a task to an
endpoint that obeys the flag without deciding it silently swaps in an unmeasured variant of the model. The two
hot-path judges (`turn_complete`, `directed`) disable it for latency; the JSON tasks disable it to work at all.
Config `§memory.<task>_model/_base_url/_api_key` overrides the titular. Benchmarks: `zaelar-model-benchmarks.md §12`.
"""
from __future__ import annotations

_DEFAULTS = {
    # rem — deep-sleep synthesis. The titular is a cheap non-reasoning model; the stronger one is the stand-in, so
    # an empty 200 FALLS THROUGH instead of killing the cycle.
    "rem": ("https://api.deepseek.com", "deepseek-flash", True),
    # i18n (V2-089) — UI translation during initialization; paid ONCE per language, so the batch must not be lost.
    # DeepSeek's native endpoint obeys `thinking:disabled` (the broker accepted and ignored it, V2-097).
    "i18n": ("https://api.deepseek.com", "deepseek-v4-pro", True),
    # turn_complete (V2-102) — the turn-completeness judge, per ambiguous fragment: hot path, reasoning OFF.
    "turn_complete": ("https://api.deepseek.com", "deepseek-v4-flash", True),
    # directed — open-mic «is this aimed at me?» gate (voice/attention.py): same hot-path profile.
    "directed": ("https://api.deepseek.com", "deepseek-v4-flash", True),
    # errand_scope — with an errand live, is a NEW escalation separate or ABOUT it? Off the voice turn but in
    # front of a worker he is waiting on.
    "errand_scope": ("https://api.deepseek.com", "deepseek-v4-flash", True),
    # paraphrase (V2-031 T2) — reformulations of a durable pill for the paraphrase index, from REM. Reasoning OFF
    # or it returns nothing (measured 2026-08-18).
    "paraphrase": ("https://api.deepseek.com", "deepseek-flash", True),
    # batch_split (V2-771) — a message with SEVERAL tasks split into ordered steps; strict JSON → reasoning OFF.
    "batch_split": ("https://api.deepseek.com", "deepseek-flash", True),
    # rule_shape (V2-806) — a spoken rule shaped ONCE into rules-table rows; batch_split's profile and seat.
    "rule_shape": ("https://api.deepseek.com", "deepseek-flash", True),
}

_AIML = "https://api.aimlapi.com/v1"
# DeepSeek on its OWN endpoint: the titular of most tasks; `failover_rungs` skips a rung that is already the
# titular, so listing it costs nothing and keeps the order true when the titular is, say, a local Ollama.
_DS = "https://api.deepseek.com"
# The one stand-in of every memory task («OpenAI siempre tiene que ser failover», operator, 2026-09-22).
_OAI = "https://api.openai.com/v1"

# FAILOVER — ONE stand-in per task, native providers only, the broker never (operator, 2026-09-22). A rung is
# skipped when its credential is absent: a request with no key buys a 401 and a slower failure, never a chance.
# ⚠️ Only OFF-HOT-PATH tasks get a chain: the hot-path judges fail open to a safe default in milliseconds, and a
# second attempt through a slow provider would hurt more than the default they degrade to.
_FAILOVER: dict[str, tuple[tuple[str, str], ...]] = {
    "rem": ((_OAI, "gpt-4.1-mini"),),
    # distill — the write HEART resolves its own TITULAR (`distill_config`); only its fallback ORDER lives here.
    # ⛔ NOT `gpt-4o-mini`: cheaper and VETOED (puts an allergy stated in English into `slot=operator.diet`).
    "distill": ((_OAI, "gpt-4.1-mini"),),
    "batch_split": ((_OAI, "gpt-4.1-mini"),),
    "rule_shape": ((_OAI, "gpt-4.1-mini"),),
    # paraphrase — a rung that answers 200 with nothing in it is worse than no rung; gpt-4.1-mini has no thinking.
    "paraphrase": ((_OAI, "gpt-4.1-mini"),),
    # i18n — one rung stops a lost batch from meaning 50 English strings in the UI.
    "i18n": ((_OAI, "gpt-4.1-mini"),),
}


def has_credential(url: str, key: str) -> bool:
    """A local endpoint legitimately needs no key (`key_for_endpoint`'s `"local"` sentinel); a cloud one that
    resolves to it has a MISSING credential, and trying it anyway just delays the real answer."""
    if key and key != "local":
        return True
    return any(h in (url or "").lower() for h in ("localhost", "127.0.0.1", "11434"))
