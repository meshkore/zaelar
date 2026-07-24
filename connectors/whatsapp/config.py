#
# config.py — knobs del conector WhatsApp (INI-014). Todo por .env (gitignored); valores por defecto sanos.
#
# El clasificador apunta por DEFECTO al modelo LOCAL (Ollama) — nada personal sale de la máquina. Cambiar a un
# modelo remoto es SOLO cambiar WA_TRIAGE_MODEL/WA_TRIAGE_URL/WA_TRIAGE_KEY (p.ej. AIMLAPI). No cambia el diseño.
#
import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def bridge_port() -> int:
    # 3111 por defecto para NO chocar con el bridge de `hermes gateway` (que usa :3000).
    return int(os.getenv("WA_BRIDGE_PORT", "3111"))


def bridge_url() -> str:
    return f"http://127.0.0.1:{bridge_port()}"


def session_dir() -> Path:
    # Sesión de pairing PROPIA de zaelar (credenciales personales, gitignored). No compartimos la de Hermes.
    d = os.getenv("WA_SESSION_DIR") or str(_HERE / "_session")
    return Path(d)


def bridge_dir() -> Path:
    return _HERE / "bridge"


# ── Clasificador (triaje) ──────────────────────────────────────────────────
def triage_url() -> str:
    # OpenAI-compatible. Local Ollama por defecto (mismo endpoint que el perfil `local` del motor de voz).
    return os.getenv("WA_TRIAGE_URL") or os.getenv("ZAELAR_LOCAL_LLM_URL", "http://localhost:11434/v1")


def triage_model() -> str:
    return os.getenv("WA_TRIAGE_MODEL") or os.getenv("ZAELAR_LOCAL_LLM_MODEL", "qwen2.5:3b")


def triage_key() -> str:
    # Ollama ignora el valor pero exige uno no vacío. Para un backend remoto, pon la API key aquí.
    return os.getenv("WA_TRIAGE_KEY", "local")


def operator_name() -> str:
    # Ayuda al clasificador a decidir "¿va dirigido a mí?". Opcional.
    return os.getenv("WA_MY_NAME", "").strip()


def poll_interval() -> float:
    return float(os.getenv("WA_POLL_INTERVAL", "5"))
