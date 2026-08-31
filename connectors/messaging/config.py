#
# config.py — SHARED knobs for the messaging classifier (INI-015).
#
# HISTORICAL NOTE: the classifier DEFAULTED to the LOCAL model (Ollama qwen2.5:3b) for PRIVACY (nothing personal left
# the machine). The operator requested ZERO local execution (battery, 2026-07-17) -> DEFAULT is now EXTERNAL
# (`config/v2.py §triage`, grok via xAI by default). Accepted TRADEOFF: the personal message DOES go to the cloud.
# Source of truth = `config/v2 §triage` (UI-managed); env `MSG_TRIAGE_*`/`WA_TRIAGE_*` = power-user fallback.
#
import os


def _cfg(key: str) -> str:
    try:
        from config import v2 as _v2
        return (_v2.get("triage").get(key) or "").strip()
    except Exception:
        return ""


def triage_url() -> str:
    # OpenAI-compatible. Config §triage.base_url -> env -> localhost (only if someone points back to Ollama).
    return (_cfg("base_url") or os.getenv("MSG_TRIAGE_URL") or os.getenv("WA_TRIAGE_URL")
            or os.getenv("ZAELAR_LOCAL_LLM_URL", "http://localhost:11434/v1"))


def triage_model() -> str:
    return (_cfg("model") or os.getenv("MSG_TRIAGE_MODEL") or os.getenv("WA_TRIAGE_MODEL")
            or os.getenv("ZAELAR_LOCAL_LLM_MODEL", "qwen2.5:3b"))


def triage_key() -> str:
    """Config §triage.api_key (inline) -> env -> the key registered for THIS endpoint -> "local" (Ollama's
    any-non-empty-string sentinel).

    The last step used to be a hand-rolled `if "x.ai" … elif "openai.com" …`, and it is exactly the drift
    `nucleo/provider_keys.py` was created to end — its own docstring names the four files that had already
    diverged; this was a FIFTH, never migrated. Measured on the operator's engine 2026-08-31: §triage pointed at
    `https://api.deepseek.com`, an endpoint this chain did not know, so it sent the literal string `local` as the
    bearer token. DeepSeek answered `401 Authentication Fails, Your api key: ****ocal is invalid` — and because
    the caller read `data["choices"]` straight off, the only trace was `triage failed: 'choices'`, for hours,
    while the engine held a perfectly good `DEEPSEEK_API_KEY` and the operator went looking at his balance.
    One list, everyone reads it: a new endpoint is added there once."""
    k = _cfg("api_key") or os.getenv("MSG_TRIAGE_KEY") or os.getenv("WA_TRIAGE_KEY", "")
    if k:
        return k
    from nucleo import provider_keys
    return provider_keys.key_for_endpoint(triage_url(), default="local")


def operator_name() -> str:
    # Operator name — helps the classifier decide whether it is addressed to me. Each connector can pass its own
    # (WA_MY_NAME / TG_MY_NAME); this is the common fallback.
    return (os.getenv("MSG_MY_NAME") or os.getenv("WA_MY_NAME") or "").strip()
