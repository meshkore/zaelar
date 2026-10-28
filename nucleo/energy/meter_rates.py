# ENERGY METERING — the declared PRICE TABLES (split from `meter.py`, refactor2710-10b). Data only, re-exported
# by `meter.py`; read by `meter_price.py`. Calls nobody — the hosts below are rate keys, not endpoints.

# $ per 1M tokens (in, out) by `base_url` substring, for single-priced endpoints only (_MODEL_RATES wins).
# Source: public pricing, 2026-08-05 — RE-VERIFY periodically.
_RATES_PER_1M_TOKENS_USD: dict[str, tuple[float, float]] = {
    "x.ai": (0.20, 0.50),               # Grok 4.1 Fast tier
    "api.openai.com": (0.40, 1.60),     # gpt-4.1-mini tier (OpenAI direct is no longer a default anywhere)
    "api.z.ai": (1.40, 4.40),           # GLM-5.2 — the Brain Workers' primary relay tier (code_agent)
    "moonshot.ai": (0.95, 4.00),        # Kimi K2.6 — the Brain Workers' secondary relay tier
}

# $ per 1M tokens (in, out) by MODEL substring, consulted FIRST for every provider (2026-08-13): the model has
# the price, the endpoint only serves it — "x.ai" said $0.20/$0.50 while a Grok Build worker ran grok-4.5 at $2/$6.
_MODEL_RATES: dict[str, tuple[float, float]] = {
    # DeepSeek DIRECT, api-docs.deepseek.com pricing read 2026-09-25, always the PEAK tier (off-peak is half:
    # at most 2x over, never under). `deepseek-flash` (V4.1-Flash, voice brain titular) had NO row and billed at
    # the catch-all; `deepseek-v4-pro` (brief_composer) had a stale row 4.7x/9.4x too cheap.
    "deepseek-flash": (0.30, 1.20),
    "deepseek-v4-pro": (1.32, 3.96),
    # AIMLAPI broker route, kept for older configs: the broker's price, independent of the rows above.
    "deepseek-v4-flash": (0.14, 0.28),
    # Memory EMBEDDINGS (V2-501, 2026-08-30): output is a real zero; without a row, every insert and query
    # would bill at the catch-all (~100x over).
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
    "mistral-embed": (0.10, 0.0),
    # CORAZÓN fallback chain (§12.3), rated so a failover never meters as the generic fallback rate.
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gpt-4.1-mini": (0.40, 1.60),              # previous CORAZÓN titular; last link of the chain
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "grok-4-fast": (0.20, 0.50),
    "kimi-k2": (0.95, 4.00),
    "glm-4.7": (0.40, 1.75),
    "ministral-8b": (0.10, 0.10),
    "llama-3.3-70b": (0.59, 0.79),
    # Grok Build workers (2026-08-13): its CLI talks to xAI directly and reports no base_url, so they need a row
    # per model. xAI public pricing, 2026-08-13. NOT modelled yet: grok-4.5's long tier ($4/$12 above 200K prompt).
    "grok-4.5": (2.00, 6.00),
    "grok-4.6": (2.00, 6.00),
    "grok-4.3": (3.00, 15.00),
    # Worker relay models, by name too (the base_url row stays as backup). `glm-5.3` is the worker titular;
    # docs.z.ai pricing 2026-09-25, same as 5.2 — Z.AI's pay-per-token price.
    "glm-5.3": (1.40, 4.40),
    "glm-5.2": (1.40, 4.40),
    "kimi-k2.6": (0.95, 4.00),
    # (A repeated key keeps the LAST value: a stale `deepseek-v4-pro` here once voided the good row above.)
}

# Punitive catch-all for an unmapped (base_url, model): over-charges rather than under, logged once per key.
_FALLBACK_RATE_USD: tuple[float, float] = (1.00, 5.00)


_BROKER_MARKUP_AIMLAPI: dict[str, float] = {
    "deepseek-v4-flash": 1.30,      # 0.14 native → 0.182 through the broker
    "grok-4-fast": 1.05,            # 0.20 → 0.21
    "gemini-2.5-flash": 1.00,       # 0.30 → 0.30 (no markup)
}
_BROKER_MARKUP_DEFAULT = 1.30       # the worst markup observed: over-charge rather than under-charge


# $ per 1M CACHED-READ input tokens. Anthropic-shaped usage reports them OUTSIDE `input_tokens`; ignoring them
# left 29% of a measured worker bill out (211k cached vs 74k fresh). grok's rate is MEASURED from xAI CLI costs.
_CACHED_READ_RATES_USD: dict[str, float] = {
    "grok-4.5": 0.30,          # measured, not published
    "grok-4.6": 0.30,
    "glm-5.2": 0.26,           # Z.AI's published cached-input price
    "glm-5.3": 0.26,           # 2026-08-14: inherits 5.2's until Z.AI publishes its own
    # DeepSeek, confirmed on its pricing page 2026-09-25, PEAK tier. The hit is ~50x cheaper than fresh input, so
    # the 25% fallback over-charged it ~12x — and the hit is what grows most in a long session.
    "deepseek-flash": 0.006,
    "deepseek-v4-pro": 0.044,
}
_CACHED_READ_FALLBACK_FRACTION = 0.25      # of the input rate, when a model has no row


# $ per SEARCH REQUEST (2026-08-13: paid search had no rate and billed zero). The rates live beside their
# providers (V2-782, `search/providers::USD_PER_REQUEST`); only the `""` catch-all is ours, logged once.
# Free providers are filtered by the caller: "free" is a fact about the provider, not a zero rate.
from search.providers import USD_PER_REQUEST as _SEARCH_RATES  # noqa: E402 — a declaration table, no engine imports
_SEARCH_USD_PER_REQUEST: dict[str, float] = {**_SEARCH_RATES, "": 0.008}


# $ per ROUND TRIP of the decision model (`nucleo/jev.py`): one trip carries the whole turn's questions.
# ⚠️ ESTIMATED, NOT PUBLISHED — the only rate here with no pricing page behind it.
_DECISION_USD_PER_REQUEST: dict[str, float] = {
    "typesafe": 0.0005,
    "": 0.0005,
}
