#
# control.py — la lógica de CONECTAR/DESCONECTAR un conector desde la UI (INI-015), en un solo sitio. La usan DOS
# entradas: (a) la API HTTP (server_api.py, para uso programático) y (b) el supervisor (supervisor.py), que drena
# las órdenes que el WIDGET encola en el store (el widget solo puede hablar por ctx.action → data.py → store; no
# puede hacer fetch, por el contrato de aislamiento de widgets). Ambas convergen aquí → una sola verdad.
#
# "Conectar" = persistir config en el store frontend-managed (config/connectors.py) + arrancar el conector EN
# CALIENTE. "Desconectar" = pararlo + desactivar (opcionalmente olvidar sesión/credenciales). Nunca toca .env.
#
from loguru import logger

from config import connectors as cfg

PLATFORMS = ("whatsapp", "telegram", "email")


def _services():
    from connectors.email import service as em
    from connectors.telegram import service as tg
    from connectors.whatsapp import service as wa
    return {"whatsapp": wa, "telegram": tg, "email": em}


def validate_connect(platform: str, payload: dict) -> str | None:
    """Devuelve un mensaje de error si la petición de conexión es inválida; None si es válida."""
    if platform not in PLATFORMS:
        return f"plataforma desconocida: {platform}"
    if platform == "telegram":
        api_id = str((payload or {}).get("api_id") or "").strip()
        api_hash = str((payload or {}).get("api_hash") or "").strip()
        if not api_id.isdigit() or not api_hash:
            return ("api_id (número) y api_hash son obligatorios. "
                    "Sácalos de my.telegram.org → API development tools.")
    if platform == "email":
        p = payload or {}
        addr = str(p.get("email_address") or "").strip()
        pwd = str(p.get("email_password") or "").strip()
        if "@" not in addr:
            return "La dirección de correo es obligatoria (p.ej. tucuenta@gmail.com)."
        if not pwd:
            return ("La contraseña de aplicación es obligatoria. En Gmail/Outlook actívala en la seguridad de tu "
                    "cuenta (con verificación en 2 pasos): 'contraseña de aplicación'.")
        prov = str(p.get("provider") or "").strip().lower()
        from connectors.email.mailbox import PRESETS
        if prov not in PRESETS and prov not in ("", "otro", "other"):
            return f"proveedor desconocido: {prov}"
        # Si no hay preset explícito y el payload no trae hosts, exige que el dominio de la dirección sea deducible.
        has_hosts = bool(str(p.get("imap_host") or "").strip() and str(p.get("smtp_host") or "").strip())
        if prov not in PRESETS and not has_hosts:
            domain = addr.split("@")[-1].lower()
            deducible = any(k in domain for k in ("gmail", "googlemail", "outlook", "hotmail", "live",
                                                  "office365", "icloud", "me.com", "yahoo"))
            if not deducible:
                return ("Para un proveedor no listado necesito el servidor IMAP y el SMTP (p.ej. imap.tudominio.com "
                        "y smtp.tudominio.com).")
    return None


async def apply_connect(platform: str, payload: dict | None = None) -> dict:
    """Persiste config + (re)arranca el conector. Devuelve {ok, ...}. Idempotente ante un conector ya corriendo."""
    payload = payload or {}
    err = validate_connect(platform, payload)
    if err:
        return {"ok": False, "error": err}

    patch = {"enabled": True}
    if platform == "telegram":
        patch.update({"api_id": str(payload.get("api_id")).strip(),
                      "api_hash": str(payload.get("api_hash")).strip()})
    if platform == "email":
        patch.update({"email_address": str(payload.get("email_address") or "").strip(),
                      "email_password": str(payload.get("email_password") or ""),
                      "provider": str(payload.get("provider") or "").strip().lower()})
        for k in ("imap_host", "imap_port", "smtp_host", "smtp_port"):     # solo si el usuario los dio (proveedor 'otro')
            v = payload.get(k)
            if v not in (None, ""):
                patch[k] = str(v).strip() if "host" in k else int(v)
        if payload.get("autoreply") is not None:
            patch["autoreply"] = bool(payload.get("autoreply"))
    cfg.set(platform, patch)

    svc = _services()[platform]
    try:
        await svc.stop()          # reinicio limpio si ya estaba corriendo (toma la config nueva)
    except Exception:
        pass
    try:
        svc.start()
    except Exception as e:
        logger.warning(f"messaging connect {platform}: start falló: {e}")
        return {"ok": False, "error": str(e)}
    logger.info(f"messaging: {platform} conectado desde la UI")
    return {"ok": True, "platform": platform}


async def apply_disconnect(platform: str, payload: dict | None = None) -> dict:
    """Para el conector + lo desactiva. Con {forget:true} borra sesión (y credenciales de Telegram)."""
    if platform not in PLATFORMS:
        return {"ok": False, "error": f"plataforma desconocida: {platform}"}
    payload = payload or {}
    forget = bool(payload.get("forget"))

    svc = _services()[platform]
    try:
        await svc.stop()
    except Exception as e:
        logger.debug(f"messaging disconnect {platform}: stop: {e}")

    patch = {"enabled": False}
    if forget and platform == "telegram":
        patch.update({"api_id": "", "api_hash": ""})
    if forget and platform == "email":
        patch.update({"email_address": "", "email_password": "", "provider": "",
                      "imap_host": "", "smtp_host": ""})
    cfg.set(platform, patch)
    if forget:
        _forget_session(platform)

    try:
        from connectors.messaging import store
        store.set_platform_status(platform, "off", None)
    except Exception:
        pass
    logger.info(f"messaging: {platform} desconectado desde la UI (forget={forget})")
    return {"ok": True, "platform": platform, "forgot": forget}


def _forget_session(platform: str) -> None:
    import shutil
    try:
        if platform == "telegram":
            from connectors.telegram import config as tgc
            shutil.rmtree(tgc.session_dir(), ignore_errors=True)
        elif platform == "whatsapp":
            from connectors.whatsapp import config as wac
            shutil.rmtree(wac.session_dir(), ignore_errors=True)
    except Exception as e:
        logger.debug(f"forget session {platform}: {e}")
