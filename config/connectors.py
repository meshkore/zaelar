#
# connectors.py — connector config MANAGED BY THE INTERFACE (INI-015). zaelar product principle:
# **the user installs the product ONCE and from then on EVERYTHING is managed from the interface** — they never edit
# environment files. When they say "connect me to Telegram", the messaging widget guides them step by step
# (credential form if needed → QR → connected), and these variables are persisted HERE, not in `.env`.
#
# Persists in config/connectors.json (gitignored — contains personal credentials). The messaging API
# (connectors/messaging/server_api.py) WRITES it from the frontend; connectors (whatsapp/telegram) READ it. `.env`
# still works as a **power-user / back-compat fallback**: if the store says nothing about a platform, the
# corresponding env var is checked. The store ALWAYS wins over `.env`.
#
# Reusable pattern for ANY future connector (email, LinkedIn, X): declare its shape in _DEFAULTS, its secrets in
# _SECRET_KEYS (so they never reach the frontend), and add its guided setup flow to the widget.
#
import json
import os
import threading
from pathlib import Path

from nucleo import workspace as _workspace

# `<workspace>/config/connectors.json` — unset `ZAELAR_WORKSPACE` is byte-identical to the old
# `Path(__file__).resolve().parent / "connectors.json"`.
_PATH = _workspace.root() / "config" / "connectors.json"
_lock = threading.Lock()

# Shape per platform + default values. Adding a connector = one entry here.
_DEFAULTS = {
    "whatsapp": {"enabled": False},                                  # WhatsApp needs no credentials (QR only)
    "telegram": {"enabled": False, "api_id": "", "api_hash": ""},    # Telegram: api_id/api_hash from my.telegram.org
    "email": {"enabled": False, "email_address": "", "email_password": "", "provider": "",   # V2-051: IMAP/SMTP
              "imap_host": "", "imap_port": 0, "smtp_host": "", "smtp_port": 0, "autoreply": False},
    # V2-083: the Architect daemon token lives HERE (dynamic store), NOT in .env — configurable/revocable from the
    # Connectors tab. Optional `url` (default loopback). `token` is SECRET (redacted to the frontend).
    "architect": {"enabled": False, "token": "", "url": ""},
}
# Keys that are NEVER returned to the frontend (replaced by a `<key>_set` boolean). Privacy fail-safe.
_SECRET_KEYS = {"api_hash", "email_password", "token"}
# env var used as FALLBACK for the `enabled` flag when the store says nothing (back-compat / power-user).
_ENABLED_ENV = {"whatsapp": "WA_ENABLED", "telegram": "TG_ENABLED", "email": "EMAIL_ENABLED"}


def _read() -> dict:
    with _lock:
        if _PATH.exists():
            try:
                data = json.loads(_PATH.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
    return {}


def _write(data: dict) -> None:
    with _lock:
        tmp = str(_PATH) + ".tmp"
        Path(tmp).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, _PATH)


def get(platform: str) -> dict:
    """Effective config for a platform (defaults + persisted values). Includes secrets → INTERNAL connector use."""
    base = dict(_DEFAULTS.get(platform, {}))
    base.update(_read().get(platform, {}) or {})
    return base


def set(platform: str, patch: dict) -> dict:
    """Apply a patch to a platform config (atomic read-modify-write). Return the effective config."""
    data = _read()
    cur = dict(data.get(platform, {}) or {})
    cur.update(patch or {})
    data[platform] = cur
    _write(data)
    return get(platform)


def enabled(platform: str) -> bool:
    """Is the connector enabled? The store WINS; if it says nothing, fall back to env var (back-compat / power-user)."""
    v = _read().get(platform, {}).get("enabled")
    if v is not None:
        return bool(v)
    return os.getenv(_ENABLED_ENV.get(platform, ""), "0") == "1"


def public(platform: str) -> dict:
    """REDACTED frontend view: secrets NEVER leave — they are replaced by `<key>_set: bool`."""
    cfg = get(platform)
    out = {}
    for k, val in cfg.items():
        if k in _SECRET_KEYS:
            out[k + "_set"] = bool(val)
        else:
            out[k] = val
    return out


def public_all() -> dict:
    return {p: public(p) for p in _DEFAULTS}
