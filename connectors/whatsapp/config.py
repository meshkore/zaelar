#
# config.py — WhatsApp connector knobs. Everything through .env (gitignored); sane defaults.
#
# The classifier DEFAULTS to the LOCAL model (Ollama) — nothing personal leaves the machine. Switching to a remote
# model is ONLY changing WA_TRIAGE_MODEL/WA_TRIAGE_URL/WA_TRIAGE_KEY (e.g. AIMLAPI). The design does not change.
#
import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def bridge_port() -> int:
    # 3111 by default: away from :3000, where other local tools tend to listen.
    return int(os.getenv("WA_BRIDGE_PORT", "3111"))


def bridge_url() -> str:
    return f"http://127.0.0.1:{bridge_port()}"


def session_dir() -> Path:
    # zaelar's OWN pairing session (personal credentials, gitignored), shared with no other tool.
    # With `ZAELAR_WORKSPACE` set the session lives in the workspace like every other per-install credential: a
    # container whose code directory is rebuilt on each image would otherwise lose the pairing on every restart,
    # and re-pairing is a QR the person has to scan again.
    d = os.getenv("WA_SESSION_DIR")
    if d:
        return Path(d)
    if os.getenv("ZAELAR_WORKSPACE"):
        from nucleo import workspace as _workspace
        return _workspace.root() / "connectors" / "whatsapp" / "_session"
    return _HERE / "_session"


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
    endpoint map (`nucleo/energy/keys.py`) rather than from nowhere: the default here is local Ollama, but
    `WA_TRIAGE_URL` can point anywhere, and sending the literal `local` to a real provider fails auth silently —
    the failure measured in the messaging triage on 2026-08-31, which cost hours because the 401 never surfaced."""
    k = os.getenv("WA_TRIAGE_KEY", "")
    if k:
        return k
    from nucleo.energy import keys as provider_keys
    return provider_keys.key_for_endpoint(triage_url(), default="local")


def operator_name() -> str:
    # Helps the classifier decide whether it is addressed to me. Optional.
    return os.getenv("WA_MY_NAME", "").strip()


def poll_interval() -> float:
    return float(os.getenv("WA_POLL_INTERVAL", "5"))

