#
# auth_memory.py — migas de MEMORIA de la autenticación del navegador (INI-016, auth).
#
# Reparto memoria ↔ storage (protocolo `zaelar-memory.md §Acciones↔memoria`): el SECRETO en sí (cookies/tokens)
# NUNCA entra en memoria — vive en el perfil PERSISTENTE de Chromium en disco (`widgets/_data/navegador/profile/`),
# cifrado en reposo por el SO. La memoria solo guarda lo que zaelar debe RECORDAR como un humano:
#
#   • record_session_established(site) → EVENTO recallable ("tengo sesión en <sitio> desde el <fecha>"), con `slot`
#     por sitio para que un re-login SUPERSEDA en vez de duplicar. Calca `widgets/lifecycle.record_created`.
#   • checkpoint_auth_pending / clear_auth_pending → MIGA DURABLE de un login A MEDIAS. Las tareas del navegador
#     viven en RAM y un reinicio las mata (`tasks.py`), así que el checkpoint NO persiste la tarea: deja el rastro
#     en la memoria de ESTADO (`memory.set_state`, calca `nucleo/reset.py`) + un evento en CORTO. Al arrancar,
#     zaelar puede leer `read_auth_pending()` y recordar "dejaste el login de <sitio> a medias".
#
# Escritor SANCIONADO por la fachada `memory.write`/`set_state` (cola async, loop-agnóstica) igual que
# `widgets/lifecycle.py`. Todo best-effort: un fallo de memoria NUNCA rompe el flujo de autenticación.
#
from __future__ import annotations

import time

from loguru import logger


def _memory():
    from memory import api as memory
    return memory


def record_session_established(site: str) -> None:
    """Da de ALTA en memoria el HECHO de que hay sesión iniciada en `site` (recallable; el secreto NO se guarda).
    `slot` por sitio → un re-login supersede el hecho anterior en vez de acumular duplicados. Best-effort."""
    site = (site or "").strip().lower()
    if not site:
        return
    when = time.strftime("%Y-%m-%d")
    try:
        _memory().write(
            f"[navegador:auth] Hay sesión iniciada en «{site}» (desde el {when}); el navegador entra con la cuenta "
            f"del operador. Las credenciales viven en el perfil del navegador, no aquí.",
            kind="event", level="mid", importance=0.55, slot=f"navegador.session.{site}",
            meta={"entity": site, "source": "navegador.auth", "said_at": when},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"auth_memory: record_session_established falló: {e}")


def checkpoint_auth_pending(site: str, task_id: str = "", goal: str = "") -> None:
    """Congela en ESTADO que hay un login A MEDIAS (recuperable tras crash/reinicio) + registra el evento en CORTO.
    Calca la secuencia congelar→registrar del Reset. Best-effort."""
    site = (site or "").strip().lower()
    ts = time.strftime("%Y-%m-%d %H:%M")
    try:
        m = _memory()
        m.set_state({"auth_pendiente": {
            "sitio": site, "tarea": task_id, "objetivo": (goal or "")[:200], "cuando": ts,
        }})
        m.write(
            f"[navegador:auth] Quedó un inicio de sesión a medias en «{site}» ({ts}); si el operador no lo terminó, "
            f"recuérdaselo y ofrécele retomarlo.",
            level="short", kind="event", importance=0.6,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"auth_memory: checkpoint_auth_pending falló: {e}")


def clear_auth_pending() -> None:
    """Limpia la miga de login-a-medias (el operador terminó o canceló). Best-effort."""
    try:
        _memory().set_state({"auth_pendiente": None})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"auth_memory: clear_auth_pending falló: {e}")


def read_auth_pending() -> dict | None:
    """Lee la miga de login-a-medias del ESTADO (para el aviso de arranque tras un reinicio). Best-effort → None."""
    try:
        return (_memory().state() or {}).get("auth_pendiente") or None
    except Exception:
        return None
