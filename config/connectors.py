#
# connectors.py — config de conectores MANEJADA POR LA INTERFAZ (INI-015). Principio de producto de zaelar:
# **el usuario instala el producto UNA vez y a partir de ahí TODO se maneja desde la interfaz** — nunca edita
# ficheros de entorno. Cuando dice "conéctame Telegram", el widget de mensajería le guía paso a paso (formulario
# de credenciales si hace falta → QR → conectado), y estas variables se persisten AQUÍ, no en `.env`.
#
# Persiste en config/connectors.json (gitignored — lleva credenciales personales). Lo ESCRIBE la API de mensajería
# (connectors/messaging/server_api.py) desde el frontend; lo LEEN los conectores (whatsapp/telegram). `.env` sigue
# funcionando como **fallback de power-user / back-compat**: si el store no dice nada de una plataforma, se mira la
# env var correspondiente. El store SIEMPRE gana sobre `.env`.
#
# Patrón reutilizable para CUALQUIER conector futuro (email, LinkedIn, X): declara su forma en _DEFAULTS, sus
# secretos en _SECRET_KEYS (para que nunca salgan al frontend), y añade su flujo de setup guiado al widget.
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

# Forma por plataforma + valores por defecto. Añadir un conector = una entrada aquí.
_DEFAULTS = {
    "whatsapp": {"enabled": False},                                  # WhatsApp no necesita credenciales (solo QR)
    "telegram": {"enabled": False, "api_id": "", "api_hash": ""},    # Telegram: api_id/api_hash de my.telegram.org
    "email": {"enabled": False, "email_address": "", "email_password": "", "provider": "",   # V2-051: IMAP/SMTP
              "imap_host": "", "imap_port": 0, "smtp_host": "", "smtp_port": 0, "autoreply": False},
    # V2-083: el token del daemon Architect vive AQUÍ (store dinámico), NO en .env — configurable/revocable desde
    # la pestaña Conectores. `url` opcional (default loopback). `token` es SECRETO (se redacta al frontend).
    "architect": {"enabled": False, "token": "", "url": ""},
}
# Claves que NUNCA se devuelven al frontend (se sustituyen por un booleano `<key>_set`). Fail-safe de privacidad.
_SECRET_KEYS = {"api_hash", "email_password", "token"}
# env var que hace de FALLBACK del flag `enabled` cuando el store no dice nada (back-compat / power-user).
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
    """Config efectiva de una plataforma (defaults + lo persistido). Incluye secretos → uso INTERNO (conectores)."""
    base = dict(_DEFAULTS.get(platform, {}))
    base.update(_read().get(platform, {}) or {})
    return base


def set(platform: str, patch: dict) -> dict:
    """Aplica un patch a la config de una plataforma (read-modify-write atómico). Devuelve la config efectiva."""
    data = _read()
    cur = dict(data.get(platform, {}) or {})
    cur.update(patch or {})
    data[platform] = cur
    _write(data)
    return get(platform)


def enabled(platform: str) -> bool:
    """¿Está activado el conector? El store MANDA; si no dice nada, cae a la env var (back-compat / power-user)."""
    v = _read().get(platform, {}).get("enabled")
    if v is not None:
        return bool(v)
    return os.getenv(_ENABLED_ENV.get(platform, ""), "0") == "1"


def public(platform: str) -> dict:
    """Vista REDACTADA para el frontend: los secretos NUNCA salen — se sustituyen por `<key>_set: bool`."""
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
