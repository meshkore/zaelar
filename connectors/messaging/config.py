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
    # Config §triage.api_key (inline) -> env -> if endpoint is xAI/OpenAI and no key exists, use env key -> "local".
    k = _cfg("api_key") or os.getenv("MSG_TRIAGE_KEY") or os.getenv("WA_TRIAGE_KEY", "")
    if k:
        return k
    u = triage_url().lower()
    if "x.ai" in u:
        return os.getenv("XAI_API_KEY", "") or "local"
    if "openai.com" in u:
        return os.getenv("OPENAI_API_KEY", "") or "local"
    return "local"


def operator_name() -> str:
    # Operator name — helps the classifier decide whether it is addressed to me. Each connector can pass its own
    # (WA_MY_NAME / TG_MY_NAME); this is the common fallback.
    return (os.getenv("MSG_MY_NAME") or os.getenv("WA_MY_NAME") or "").strip()
