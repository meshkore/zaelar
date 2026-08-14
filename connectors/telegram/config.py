#
# config.py — Telegram connector knobs (INI-015). Everything through .env (gitignored); sane defaults.
#
# Telegram = USERBOT with Telethon (operator's PERSONAL account), NOT the Bot API — the only way to read personal
# chats. Credentials from my.telegram.org (TG_API_ID + TG_API_HASH). The classifier is shared
# (connectors/messaging/triage.py), LOCAL by default -> nothing personal leaves the machine.
#
import os
from pathlib import Path

from config import connectors as _store   # UI-MANAGED config (store wins over .env)

_HERE = Path(__file__).resolve().parent


def enabled() -> bool:
    # Store (written by the UI) wins; if it says nothing, fall back to TG_ENABLED (back-compat / power-user).
    return _store.enabled("telegram")


def api_id() -> int | None:
    # Store first (set by the user from the widget), then .env as fallback.
    raw = str(_store.get("telegram").get("api_id") or os.getenv("TG_API_ID") or "").strip()
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def api_hash() -> str:
    return str(_store.get("telegram").get("api_hash") or os.getenv("TG_API_HASH") or "").strip()


def has_credentials() -> bool:
    return api_id() is not None and bool(api_hash())


def session_dir() -> Path:
    # OWN login session (personal credentials, gitignored). Telethon stores the QR-linked userbot .session
    # (StringSession in a file) here.
    d = os.getenv("TG_SESSION_DIR") or str(_HERE / "_session")
    return Path(d)


def session_path() -> str:
    return str(session_dir() / "zaelar")


def operator_name() -> str:
    # Helps the classifier decide whether it is addressed to me. Optional.
    return (os.getenv("TG_MY_NAME") or "").strip()


def batch_interval() -> float:
    # Seconds between triage passes over the inbound-message buffer (batching -> fewer classifier calls).
    return float(os.getenv("TG_BATCH_INTERVAL", "5"))
