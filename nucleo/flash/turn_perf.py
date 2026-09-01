"""nucleo/flash/turn_perf.py — FlashBrain turn-latency VERDICT (2026-08-02).

The instrumentation already existed and was rich (`llm_metrics` + `timings`: TTFT, input/output tokens, tok/s, size
per prompt block, cold start, contention). The problem was that it lived BURIED in the response event's `extra`:
to find out why a turn took 8 s, we had to export the jsonl and cross-reference fields by hand.

This measures nothing new — it READS what is already measured and answers the only question that matters live in one line:

    was this turn slow BEFORE the first token, because of the PROMPT, because of the PROVIDER, or because of a cold start?

Operator premise (2026-08-02): «DeepSeek Flash is quite fast; if a turn exceeds 1–2 s, it is because we are sending it
an overly long prompt or because the provider has had a temporary failure». The verdict distinguishes those two cases
exactly and NAMES the specific culprit (which block inflates the prompt), so there is no need to guess. Deterministic,
without an LLM, fail-open: if data is missing, it degrades to "no data" and never breaks the turn.
"""
from __future__ import annotations

# Thresholds. `SLOW_MS` = from this point onward the turn is flagged and explained; it comes from the operator's
# benchmark (1–2 s is normal), with enough margin not to flag every turn with tools.
SLOW_MS = 2500
# A prompt above this already explains a slow turn on a fast model by itself.
BIG_PROMPT_TOKENS = 6000
# Throughput below this with a normal prompt = the provider is performing poorly, not us.
SLOW_TOKS_PER_S = 8.0
# A long silence before the turn → the first call pays for the handshake/model startup.
COLD_GAP_S = 90.0

# ── TTFT: the suspect this verdict did not know how to name (2026-08-14) ──────────────────────────────────────
# The branch order was cold → prompt → provider, and `prompt` wins with `ptok >= 6000`. Since the VOICE prompt
# is ALWAYS 9–10k tokens, **the `proveedor` branch was unreachable on the voice path, by construction**: the
# 10 slow turns in session b70a45d0 were labeled «PROMPT GRANDE» with a constant prompt (9.363–10.314 tok,
# ±9%) and TTFT ranging from 0 to 25.703 ms. A flat input cannot explain a factor of 10; the
# DIFFICULTY of the decision did (the two 25.6 s spikes are the session's two hardest turns), which is the signature
# of V4 Flash's hidden reasoning, already measured on 2026-08-02 («reasons even when asked not to»).
#
# So the verdict stops deciding based on prompt SIZE and instead looks at WHERE the time went:
#   · almost all before the first token (high TTFT/total) → the model was THINKING or the provider was queueing;
#   · distributed, with low throughput → the provider generates slowly;
#   · distributed, with normal throughput → the prompt/work.
# The prompt size is still named, but as DATA, not as the culprit: it has been measured at ~150 ms.
TTFT_DOMINATES = 0.70      # fraction of the turn spent before the first token to blame pre-token time
TTFT_SLOW_MS = 4000        # …and from here onward in absolute terms (below this, a 3 s turn is not a problem)

# Blocks that make up the prompt, in the order in which they are named to the operator. `sz_*` are chars already
# measured by the prompt builder; `tools_chars` is supplied by the tools catalog offered in THIS turn.
_BLOCKS = (
    ("tools_chars", "catálogo de tools"),
    ("sz_resources", "capa de recursos"),
    ("sz_widgets", "catálogo de widgets"),
    ("sz_memory", "estado/memoria"),
    ("sz_recall", "recall largo"),
    ("sz_recent", "conversación reciente"),
    ("sz_live", "estado vivo"),
)


def _num(d: dict, *keys, default=None):
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)):
            return v
    return default


def biggest_block(m: dict) -> tuple[str, int]:
    """The block that inflates this turn's prompt the most (readable name, chars). ('', 0) if there is no data."""
    best, best_n = "", 0
    for key, label in _BLOCKS:
        n = _num(m, key, default=0) or 0
        if n > best_n:
            best, best_n = label, int(n)
    return best, best_n


def verdict(m: dict) -> dict:
    """Diagnose the turn from the metrics ALREADY collected. Returns `{slow, cause, label, …}`.

    `cause` ∈ frio · pre_token · proveedor · trabajo · prompt · reparto · ok — and `label` is the line that is
    read in the viewer. The branch order IS the design decision: see the note on `TTFT_DOMINATES`.
    """
    total = _num(m, "total_ms", "fast_ms", default=0) or 0
    ttft = _num(m, "ttft_ms", default=0) or 0
    gen = _num(m, "gen_ms", "llm_total_ms", default=0) or 0
    ptok = _num(m, "prompt_tokens", "prompt_tokens_est", default=0) or 0
    tps = _num(m, "tok_per_s")
    # PREFIX CACHE (2026-09-01). TTFT pays the PREFILL, and DeepSeek reports how much of it came from its
    # automatic prefix cache (`prompt_cache_hit_tokens`, captured by fast_client since 2026-08-14 — but only
    # for billing; this verdict diagnosed TTFT blind to it). Measured in session 701fcc1b: same conversation,
    # near-constant ~10k-token prompt, TTFT 953 → 2280 ms. Hidden reasoning cannot be told apart from a cold
    # prefill without this number — and a low hit fraction at a constant prompt is OURS to fix (an unstable
    # prompt prefix busts the provider cache every turn), unlike the provider's queue or its reasoning.
    cache_hit = _num(m, "prompt_cache_hit_tokens")
    cache_frac = round(cache_hit / ptok, 3) if (cache_hit is not None and ptok) else None
    gap = _num(m, "gap_since_last_s", default=0) or 0
    cold = bool(m.get("cold_estimate")) or gap >= COLD_GAP_S
    # A turn that ESCALATES or SEARCHES makes a 2nd pass: it is slow because of WORK, not a failure.
    worked = bool(m.get("escalated") or m.get("searched"))

    block, block_n = biggest_block(m)
    slow = total >= SLOW_MS

    # How much of the turn was spent BEFORE the first token? This is the question that separates «thinks a lot» from
    # «writes slowly», and the one that was missing. Without measured ttft, nothing can be asserted → 0.0 (blames no one).
    ttft_frac = (ttft / total) if (ttft and total) else 0.0
    ttft_bound = ttft >= TTFT_SLOW_MS and ttft_frac >= TTFT_DOMINATES

    if not slow:
        cause = "ok"
        label = f"⏱ turno {int(total)} ms · prompt {int(ptok)} tok · TTFT {int(ttft)} ms"
    elif cold:
        cause = "frio"
        label = (f"⏱ turno LENTO {int(total)} ms — ARRANQUE EN FRÍO "
                 f"({int(gap)} s sin hablar; la 1ª llamada paga handshake)")
    elif ttft_bound:
        # Almost everything was spent BEFORE THE FIRST TOKEN. In this brain that is hidden reasoning (V4 Flash reasons
        # even when asked not to: measured on 2026-08-02, `thinking:disabled` halves it but does not disable it)
        # or provider queueing. BOTH are named and the distinguishing data is provided, instead of blaming the prompt.
        cause = "pre_token"
        label = (f"⏱ turno LENTO {int(total)} ms — TODO ANTES DEL 1er TOKEN: TTFT {int(ttft)} ms "
                 f"({int(ttft_frac * 100)}% del turno) con {tps if tps is not None else '?'} tok/s después. "
                 f"Razonamiento oculto o cola del proveedor — el prompt ({int(ptok)} tok) no lo explica")
    elif tps is not None and tps < SLOW_TOKS_PER_S:
        cause = "proveedor"
        label = (f"⏱ turno LENTO {int(total)} ms — PROVEEDOR LENTO: {tps} tok/s con un prompt normal "
                 f"({int(ptok)} tok) · TTFT {int(ttft)} ms")
    elif worked:
        cause = "trabajo"
        label = (f"⏱ turno {int(total)} ms — con TRABAJO en el turno "
                 f"({'escalada' if m.get('escalated') else 'búsqueda'}, 2º pase): normal que suba")
    elif ptok >= BIG_PROMPT_TOKENS and ttft_frac < TTFT_DOMINATES:
        # The prompt is blamed only when the time was ACTUALLY distributed. If almost all of it was spent before the first
        # token, pre-token time is the culprit even if the prompt is large — this is exactly the bias that meant
        # `proveedor` could never appear on voice.
        cause = "prompt"
        label = (f"⏱ turno LENTO {int(total)} ms — PROMPT GRANDE: {int(ptok)} tok"
                 + (f", lo que más pesa es «{block}» ({block_n} chars)" if block else "")
                 + f" · TTFT {int(ttft)} ms ({int(ttft_frac * 100)}%)")
    else:
        # Slow and without a dominant cause. Previously this was resolved by blaming the prompt or provider by elimination;
        # saying «I don't know, here are the numbers» is more useful than an invented culprit.
        cause = "reparto"
        label = (f"⏱ turno LENTO {int(total)} ms — sin causa dominante: TTFT {int(ttft)} ms "
                 f"({int(ttft_frac * 100)}%) · {tps if tps is not None else '?'} tok/s · prompt {int(ptok)} tok")

    # The cache fraction rides on EVERY label (not just slow ones): its value is the SERIES — watching it drop
    # from ~90% to 0% across turns is what points at a prefix-stability regression before anything gets slow.
    if cache_frac is not None:
        label += f" · caché {int(cache_frac * 100)}%"
    return {"slow": slow, "cause": cause, "label": label, "total_ms": int(total), "ttft_ms": int(ttft),
            "cache_hit_tokens": (int(cache_hit) if cache_hit is not None else None),
            "cache_hit_frac": cache_frac,
            "gen_ms": int(gen), "prompt_tokens": int(ptok), "tok_per_s": tps, "gap_since_last_s": round(gap, 1),
            "cold": cold, "top_block": block, "top_block_chars": block_n,
            # `ttft_frac` travels in the event: it is the series that governs the failover latency circuit
            # (`provider_chain.note_slow`) and makes it possible to see TTFT VARIANCE with a constant prompt.
            "ttft_frac": round(ttft_frac, 3),
            # WHERE `prompt_tokens` comes from, and the estimate ALONGSIDE the real value. Without this, the number
            # used to bill a cancelled turn cannot be audited: on 2026-08-14 the estimate had been underbilling by 16%
            # (it assumed 4 chars/token, English; the real input is 3.36) and it had to be reconstructed by cross-referencing two fields
            # that matched in only 114 of 1,070 events. A billed number must be comparable with
            # the truth in the same row.
            "usage_source": m.get("usage_source") or "",
            "prompt_tokens_est": _num(m, "prompt_tokens_est", default=0) or 0,
            "prompt_chars": _num(m, "prompt_chars", default=0) or 0,
            "tools_chars": _num(m, "tools_chars", default=0) or 0,
            "model": m.get("model") or "", "engine": m.get("engine") or m.get("provider") or ""}


def emit_verdict(metrics: dict) -> dict:
    """Publish the verdict on the observability bus (`kind="perf"`) and return it. Fail-open."""
    v = verdict(metrics or {})
    try:
        from voice.observer import emit
        emit("perf", v["label"], role="system", extra=v)
    except Exception:
        pass
    return v
