#
# config.py — WhatsApp connector knobs (INI-014). Everything through .env (gitignored); sane defaults.
#
# The classifier DEFAULTS to the LOCAL model (Ollama) — nothing personal leaves the machine. Switching to a remote
# model is ONLY changing WA_TRIAGE_MODEL/WA_TRIAGE_URL/WA_TRIAGE_KEY (e.g. AIMLAPI). The design does not change.
#
import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def bridge_port() -> int:
    # 3111 by default to avoid colliding with the `hermes gateway` bridge (which uses :3000).
    return int(os.getenv("WA_BRIDGE_PORT", "3111"))


def bridge_url() -> str:
    return f"http://127.0.0.1:{bridge_port()}"


def session_dir() -> Path:
    # zaelar's OWN pairing session (personal credentials, gitignored). We do not share Hermes's.
    d = os.getenv("WA_SESSION_DIR") or str(_HERE / "_session")
    return Path(d)


def bridge_dir() -> Path:
    return _HERE / "bridge"


# ── Classifier (triage) ────────────────────────────────────────────────────
def triage_url() -> str:
    # OpenAI-compatible. Local Ollama by default (same endpoint as the voice engine's `local` profile).
    return os.getenv("WA_TRIAGE_URL") or os.getenv("ZAELAR_LOCAL_LLM_URL", "http://localhost:11434/v1")


def triage_model() -> str:
    return os.getenv("WA_TRIAGE_MODEL") or os.getenv("ZAELAR_LOCAL_LLM_MODEL", "qwen2.5:3b")


def triage_key() -> str:
    """Ollama ignores the value but requires a non-empty one. For a REMOTE backend the key comes from the shared
    endpoint map (`nucleo/provider_keys.py`) rather than from nowhere: the default here is local Ollama, but
    `WA_TRIAGE_URL` can point anywhere, and sending the literal `local` to a real provider fails auth silently —
    the failure measured in the messaging triage on 2026-08-31, which cost hours because the 401 never surfaced."""
    k = os.getenv("WA_TRIAGE_KEY", "")
    if k:
        return k
    from nucleo import provider_keys
    return provider_keys.key_for_endpoint(triage_url(), default="local")


def operator_name() -> str:
    # Helps the classifier decide whether it is addressed to me. Optional.
    return os.getenv("WA_MY_NAME", "").strip()


def poll_interval() -> float:
    return float(os.getenv("WA_POLL_INTERVAL", "5"))
