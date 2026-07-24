#
# config.py — knobs COMPARTIDOS del clasificador de mensajería (INI-015).
#
# ⚠️ HISTÓRICO: el clasificador apuntaba por DEFECTO al modelo LOCAL (Ollama qwen2.5:3b) por PRIVACIDAD (nada
# personal salía de la máquina). El operador pidió CERO ejecución local (batería, 2026-07-17) → ahora el DEFAULT es
# EXTERNO (`config/v2.py §triage`, grok vía xAI por defecto). TRADEOFF aceptado: el mensaje personal SALE a la nube.
# Fuente de verdad = `config/v2 §triage` (UI-managed); env `MSG_TRIAGE_*`/`WA_TRIAGE_*` = fallback power-user.
#
import os


def _cfg(key: str) -> str:
    try:
        from config import v2 as _v2
        return (_v2.get("triage").get(key) or "").strip()
    except Exception:
        return ""


def triage_url() -> str:
    # OpenAI-compatible. Config §triage.base_url → env → localhost (solo si alguien vuelve a apuntar a Ollama).
    return (_cfg("base_url") or os.getenv("MSG_TRIAGE_URL") or os.getenv("WA_TRIAGE_URL")
            or os.getenv("ZAELAR_LOCAL_LLM_URL", "http://localhost:11434/v1"))


def triage_model() -> str:
    return (_cfg("model") or os.getenv("MSG_TRIAGE_MODEL") or os.getenv("WA_TRIAGE_MODEL")
            or os.getenv("ZAELAR_LOCAL_LLM_MODEL", "qwen2.5:3b"))


def triage_key() -> str:
    # Config §triage.api_key (inline) → env → si el endpoint es xAI/OpenAI y no hay key, la del entorno → "local".
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
    # Nombre del operador — ayuda al clasificador a decidir "¿va dirigido a mí?". Cada conector puede pasar el suyo
    # (WA_MY_NAME / TG_MY_NAME); este es el fallback común.
    return (os.getenv("MSG_MY_NAME") or os.getenv("WA_MY_NAME") or "").strip()
