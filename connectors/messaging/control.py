#
# control.py — CONNECT/DISCONNECT logic for a connector from the UI (INI-015), in one place. Used by TWO entries:
# (a) the HTTP API (server_api.py, for programmatic use) and (b) the supervisor (supervisor.py), which drains orders
# the WIDGET enqueues in the store (the widget can only speak through ctx.action -> data.py -> store; it cannot fetch,
# by the widget isolation contract). Both converge here -> one source of truth.
#
# "Connect" = persist config in the frontend-managed store (config/connectors.py) + start the connector HOT.
# "Disconnect" = stop it + deactivate it (optionally forget session/credentials). Never touches .env.
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
    """Return an error message if the connection request is invalid; None if it is valid."""
    if platform not in PLATFORMS:
        return f"unknown platform: {platform}"
    if platform == "telegram":
        api_id = str((payload or {}).get("api_id") or "").strip()
        api_hash = str((payload or {}).get("api_hash") or "").strip()
        if not api_id.isdigit() or not api_hash:
            return ("Necesito el api_id (solo números) y el api_hash. Los sacas en my.telegram.org → "
                    "API development tools.")
    if platform == "email":
        p = payload or {}
        addr = str(p.get("email_address") or "").strip()
        if "@" not in addr:
            return "Necesito tu dirección de correo (por ejemplo tucuenta@gmail.com)."
        prov = str(p.get("provider") or "").strip().lower()
        from connectors.email.mailbox import PRESETS
        if prov not in PRESETS and prov not in ("", "otro", "other"):
            return f"proveedor desconocido: {prov}"
        # V2-559 — the SAME verdict the form shows before enqueuing, applied again here because this is the
        # door the HTTP API and the supervisor share: a link, an address or a 15-letter Google password never
        # reaches the store to come back later as an anonymous `Invalid credentials`.
        from connectors.email import credentials as _creds
        why = _creds.diagnose(prov or _domain_provider(addr), addr, p.get("email_password"))
        if why:
            return why
        # If there is no explicit preset and the payload has no hosts, require the address domain to be deducible.
        has_hosts = bool(str(p.get("imap_host") or "").strip() and str(p.get("smtp_host") or "").strip())
        if prov not in PRESETS and not has_hosts:
            if not _domain_provider(addr):
                return ("Para un proveedor que no está en la lista necesito sus servidores IMAP y SMTP "
                        "(por ejemplo imap.tudominio.com y smtp.tudominio.com).")
    return None


def _domain_provider(address: str) -> str:
    """Provider id guessable from the address domain, or '' when it is not one we know. Shared by the host
    requirement and the password shape check — a custom domain on Google Workspace still needs Google's rules."""
    domain = str(address or "").split("@")[-1].lower()
    if not domain:
        return ""
    if "gmail" in domain or "googlemail" in domain:
        return "gmail"
    if any(x in domain for x in ("outlook", "hotmail", "live", "office365")):
        return "outlook"
    if "icloud" in domain or "me.com" in domain:
        return "icloud"
    if "yahoo" in domain:
        return "yahoo"
    return ""


async def apply_connect(platform: str, payload: dict | None = None) -> dict:
    """Persist config + (re)start the connector. Returns {ok, ...}. Idempotent with an already-running connector."""
    payload = payload or {}
    err = validate_connect(platform, payload)
    if err:
        return {"ok": False, "error": err}

    patch = {"enabled": True}
    if platform == "telegram":
        patch.update({"api_id": str(payload.get("api_id")).strip(),
                      "api_hash": str(payload.get("api_hash")).strip()})
    if platform == "email":
        from connectors.email import credentials as _creds
        patch.update({"email_address": str(payload.get("email_address") or "").strip(),
                      # V2-559: stored WITHOUT whitespace, so what Google shows in four groups is what IMAP gets.
                      "email_password": _creds.normalize(payload.get("email_password")),
                      "provider": str(payload.get("provider") or "").strip().lower()})
        for k in ("imap_host", "imap_port", "smtp_host", "smtp_port"):     # only if the user provided them (provider 'other')
            v = payload.get(k)
            if v not in (None, ""):
                patch[k] = str(v).strip() if "host" in k else int(v)
        if payload.get("autoreply") is not None:
            patch["autoreply"] = bool(payload.get("autoreply"))
    cfg.set(platform, patch)

    svc = _services()[platform]
    try:
        await svc.stop()          # clean restart if already running (picks up the new config)
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
    """Stop the connector + deactivate it. With {forget:true}, delete session (and Telegram credentials)."""
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
