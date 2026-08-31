#
# LLM HEALTH / CREDIT GUARD — a small, brain-agnostic custom piece whose ONLY job is to catch a language-model
# PROVIDER failure (no credit/quota, bad key, outage) and turn it into a CLEAN signal, so zaelar NEVER reads a raw
# "HTTP 429 RESOURCE_EXHAUSTED…" out loud. This is intentionally OUTSIDE the brain: a balance/credit problem is
# infrastructure, not thinking, so it can be handled with zero LLM.
#
# Reactive by necessity: AIMLAPI exposes no balance/usage endpoint (all 404), so we can't poll a number ahead of
# time — we detect the failure the moment a turn returns a provider error and surface it (UI banner + one short
# spoken line). If a provider ever adds a balance API, add a proactive check here and keep the same messaging.
#
# UNAMBIGUOUS provider-error signatures ONLY. NOT plain words like "quota"/"credit"/"billing"/"rate limit" —
# zaelar debates AI models, pricing and quotas with peers, so those words appear in NORMAL replies and must never
# trigger a false "no balance". Hermes surfaces a real provider failure with one of these exact error tokens.
_ERR_MARKERS = (
    "api call failed", "error code:", "http 429", "http 401", "http 403", "http 400",
    "http 500", "http 502", "http 503", "http 504", "resource_exhausted", "insufficient_quota",
    "exceeded your current quota", "too many requests", "invalid api key", "invalid_api_key",
    "invalid jwt", "rate limit exceeded", "connection error:", "upstream access forbidden",
)


def looks_like_error(text: str) -> bool:
    """True ONLY if this reply/exception is unmistakably a provider error we must NOT speak verbatim.
    A normal conversational reply (even one discussing quotas/pricing/rate-limits) must return False."""
    t = (text or "").lower()
    return any(m in t for m in _ERR_MARKERS)


def classify(text: str) -> str:
    """'credit' (no balance/quota) · 'auth' (bad key) · 'outage' (everything else). Only called on real errors."""
    t = (text or "").lower()
    if any(x in t for x in ("429", "resource_exhausted", "insufficient_quota", "exceeded your current quota",
                            "too many requests", "rate limit exceeded")):
        return "credit"
    if any(x in t for x in ("401", "403", "invalid api key", "invalid_api_key", "invalid jwt", "unauthorized")):
        return "auth"
    return "outage"


def messages(text: str) -> tuple[str, str]:
    """Return (ui_banner, spoken_line) for the operator — clear, human, no HTTP jargon."""
    kind = classify(text)
    if kind == "credit":
        return ("⚠️ Sin saldo/cuota en el modelo de lenguaje — recarga los créditos.",
                "Oye, nos hemos quedado sin saldo en el modelo. Recarga los créditos y seguimos.")
    if kind == "auth":
        return ("⚠️ Credencial del modelo inválida — revisa la API key.",
                "Tengo un problema con la credencial del modelo. Revísala, por favor.")
    return ("⚠️ El modelo de lenguaje no responde ahora mismo.",
            "Ahora mismo no puedo acceder al modelo. Probemos de nuevo en un momento.")
