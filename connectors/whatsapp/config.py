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
    # Ollama ignores the value but requires a non-empty one. For a remote backend, put the API key here.
    return os.getenv("WA_TRIAGE_KEY", "local")


def operator_name() -> str:
    # Helps the classifier decide whether it is addressed to me. Optional.
    return os.getenv("WA_MY_NAME", "").strip()


def poll_interval() -> float:
    return float(os.getenv("WA_POLL_INTERVAL", "5"))
