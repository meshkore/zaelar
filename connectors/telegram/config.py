#
# config.py — knobs del conector Telegram (INI-015). Todo por .env (gitignored); valores por defecto sanos.
#
# Telegram = USERBOT con Telethon (cuenta PERSONAL del operador), NO la Bot API — es la única forma de leer sus
# chats personales. Credenciales de my.telegram.org (TG_API_ID + TG_API_HASH). El clasificador es el compartido
# (connectors/messaging/triage.py), LOCAL por defecto → nada personal sale de la máquina.
#
import os
from pathlib import Path

from config import connectors as _store   # config MANEJADA POR LA INTERFAZ (store gana sobre .env)

_HERE = Path(__file__).resolve().parent


def enabled() -> bool:
    # El store (escrito por la UI) manda; si no dice nada, cae a TG_ENABLED (back-compat / power-user).
    return _store.enabled("telegram")


def api_id() -> int | None:
    # Store primero (lo puso el usuario desde el widget), luego .env como fallback.
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
    # Sesión de login PROPIA (credenciales personales, gitignored). Telethon guarda aquí el .session (StringSession
    # en fichero) del userbot enlazado por QR.
    d = os.getenv("TG_SESSION_DIR") or str(_HERE / "_session")
    return Path(d)


def session_path() -> str:
    return str(session_dir() / "zaelar")


def operator_name() -> str:
    # Ayuda al clasificador a decidir "¿va dirigido a mí?". Opcional.
    return (os.getenv("TG_MY_NAME") or "").strip()


def batch_interval() -> float:
    # Segundos entre pasadas de triaje del buffer de mensajes entrantes (batching → menos llamadas al clasificador).
    return float(os.getenv("TG_BATCH_INTERVAL", "5"))
