"""What a provider's failure IS: exhausted until a reset, a context overflow, a broken request, a tool limit.
Part of nucleo.workers.providers; every package name is read through _p, so a patch of providers.<name> reaches it."""
from __future__ import annotations

import re

from nucleo.workers import providers as _p


# ── exhaustion detection and relay ───────────────────────────────────────────────────────────────────────
# The provider states its reset as a date, a date+time, or ONLY a time (a same-day 5 h window). Reading only the
# date made the time-only case a past epoch → 30 min floor → 7 h of 429s, one worker at a time (e2e, 2026-08-10).
# V2-309: `6:10am` (1 digit + suffix) did not match either; 1-2 digits and an optional am/pm are accepted.
_RESET_RE = re.compile(
    r"reset(?:s|ting)?(?:\s+(?:at|on|in))?\s*[:\s]\s*"
    r"(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?|\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm)?)", re.I)


_ZAI_CODE_RE = re.compile(r"\[1[23]\d\d\]")


# A WINDOW limit (5 h, daily) is not a transient rate-limit: it clears at the provider's stated time, so it gets a
# cooldown and a relay. V2-309: «session limit» is the same class (2026-08-25 04:36, «resets 6:10am» returned "",
# so every new worker died on the same dead tier); its stated reset time is honoured like any window.
_WINDOW_RE = re.compile(
    r"usage limit reached|limit reached for\s+\d+\s*(?:hour|hr|minute|min|day)|"
    r"(?:hit|reached|exceeded)\s+(?:your|the)\s+session limit|session limit\b[^.]{0,40}\breset|"
    r"limit will reset|quota (?:will )?reset", re.I)


# Señales de CUOTA/PLAN agotado, más específicas que el `credit` genérico de `llm_health` (que también pilla un
# rate-limit pasajero). Aquí importa distinguir «espera 20s» de «hasta el jueves».
_EXHAUSTED_RE = re.compile(
    r"limit exhausted|quota exceeded|insufficient (?:balance|credit|quota)|out of credit|"
    r"monthly limit|weekly limit|plan limit|saldo insuficiente", re.I)


# ── A BLOWN CONTEXT IS NOT A SICK PROVIDER (incident 2026-08-18) ─────────────────────────────────────────────
# Session `08f54c0c` died with "reached its context window limit", unclassified, so no relay and no alert. Own
# family on purpose: the cause is context SIZE, so relaying would blow up the next tier too — the answer is COMPACT
# AND CONTINUE (`session._context_handoff`). Both wordings count: the CLI's "context window" and the real
# `max_output_tokens` apiError (input + output reservation over the window — why it died at 138k, not 200k).
_CONTEXT_RE = re.compile(
    r"context window|context[_ ]length|max_output_tokens|maximum context|"
    r"too many tokens|prompt is too long|input length and `max_tokens`", re.I)


def is_context_overflow(text: str) -> bool:
    """True if the error says the CONTEXT (input + output reservation) no longer fits the model's window.

    It must ALSO not be a quota problem: a 429 that happens to mention tokens is the other thing, and confusing
    the two would send us compacting when the right move is to relay to another provider."""
    t = text or ""
    if not _p._CONTEXT_RE.search(t):
        return False
    return _p.classify_failure(t) == ""


# V2-243 — AN EMPTY BALANCE IS NOT A QUOTA: a quota returns on its own, a balance only when the operator tops up.
# Measured 2026-08-21: DeepSeek `Insufficient Balance` (HTTP 402) showed «no quota until 03:02 · NO RELAY». A
# separate predicate, not a new `classify_failure` value: `nucleo/llm/provider_chain.py` branches on its three
# values and would return None for an unknown one (same reason as `is_context_overflow`).
_DEPLETED_RE = re.compile(
    r"insufficient (?:balance|credit|funds)|out of credit|no credit|balance is insufficient|"
    r"saldo insuficiente|sin saldo|recharge|top ?[- ]?up", re.I)


def is_depleted(text: str) -> bool:
    """True si el proveedor dice que se quedó SIN SALDO y NO anuncia cuándo vuelve.

    La ausencia de fecha es parte del predicado: un plan con forfait que dice «reset at …» sí vuelve solo, y
    tratarlo como saldo lo apagaría durante horas de más."""
    t = str(text or "")
    if not _p._DEPLETED_RE.search(t):
        return False
    return not _p._RESET_RE.search(t)


# V2-682 — A PROVIDER THAT REJECTS THE REQUEST ITSELF IS DOWN FOR US, even though it answers instantly.
# Measured 2026-09-12: 15 escalations, 15 deaths, all `API Error: 400 [1210][Invalid API parameter…]` from
# `glm-5.3`; `classify_failure` returned '', so no relay, no cooldown, and the next errand picked the same tier.
# A capability is MEASURED, never read. Separate predicate for the reason above `is_depleted`. Errs towards
# relaying (a false mark costs one relay; a miss costs every errand), with a SHORT cooldown: config/deploy fixes.
_BROKEN_RE = re.compile(
    r"\b(?:400|404|422)\b|invalid[ _]?(?:api[ _]?)?parameter|invalid[ _]request|"
    r"unsupported[ _](?:parameter|model)|model[ _](?:not[ _]found|does[ _]not[ _]exist)|unknown[ _]model|"
    # The Claude Code CLI's own wording: it swallows the provider's answer (measured 2026-09-28: a Z.ai
    # `429 [1310] Weekly/Monthly Limit Exhausted` came out as only this line, no status code), so the CLI
    # sentence is all we get. Either reading — model gone or access gone — means THIS tier cannot serve.
    r"issue with the selected model|may not have access to it",
    re.I)


def is_broken_request(text: str) -> bool:
    """True when the provider REJECTED the call itself — a deterministic 4xx that will repeat identically.

    Three things it must NOT be, and each exclusion is load-bearing:
      · a quota / credential / rate problem — `classify_failure` owns those and answers them better;
      · a blown CONTEXT, which is very often a 400 too and whose answer is COMPACT AND CONTINUE
        (`handoff.context_handoff`): relaying it would blow up identically on the next tier, because the cause
        is the size of the conversation and not who serves it;
      · anything with no 4xx signature at all — a timeout or a 5xx is transient and retrying is right."""
    t = str(text or "")
    if not _p._BROKEN_RE.search(t):
        return False
    if _p.classify_failure(t):
        return False
    return not _p.is_context_overflow(t)


def classify_failure(text: str) -> str:
    """'exhausted' (plan/cuota agotada, hay que relevar) · 'auth' · 'rate' (pasajero) · '' (no es de proveedor)."""
    t = (text or "")
    if _p._EXHAUSTED_RE.search(t):
        return "exhausted"
    low = t.lower()
    if any(x in low for x in ("401", "403", "invalid api key", "unauthorized", "authentication")):
        return "auth"
    # WINDOW EXHAUSTED ≠ RATE-LIMIT (2026-08-10): a 429 that STATES its reset time waits for it on another tier;
    # as `rate` it got no cooldown or relay, and every new worker burned its retry on it for hours.
    if _p._WINDOW_RE.search(t) or ("429" in low and _p._RESET_RE.search(t)):
        return "exhausted"
    if "429" in low or "too many requests" in low or "rate limit" in low:
        return "rate"
    return ""


# ── A BLIND WORKER IS NOT A DOWN WORKER (2026-08-10, real e2e) ───────────────────────────────────────────────
# A plan runs out two ways: the MODEL (call fails → `note_failure` relays) or the provider's BUILT-IN TOOLS (web
# search / page reader): the model still answers but is BLIND, the error hides in a `tool_result`, and it delivers
# conclusions without material. This only SAYS so; no cooldown (the model works). Relay policy is the operator's.
_TOOL_LIMIT_RE = re.compile(
    r"web_search|websearch_prime|web_search_prime|webreader|web_reader|"          # las tools integradas por nombre
    r"search.{0,20}(?:quota|limit)|(?:quota|limit).{0,20}search", re.I)


def classify_tool_failure(text: str) -> str:
    """'blind' si el error de un `tool_result` es una cuota agotada de las TOOLS del proveedor · '' si no lo es.

    Se exige que sea (a) un problema de cuota/límite Y (b) que hable de las tools: un 429 pelado del modelo no es
    ceguera, es el caso que ya cubre `note_failure`, y confundirlos daría una alerta equivocada."""
    t = text or ""
    if not _p._TOOL_LIMIT_RE.search(t):
        return ""
    return "blind" if (_p.classify_failure(t) in ("exhausted", "rate")) else ""
