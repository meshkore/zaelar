"""Why a connect failed, said so the operator can act on it (no jargon)."""
from connectors.email import config


def _auth_failure_hint() -> str:
    """What to say when the server refuses the credentials (V2-559). The generic advice — «use an app password» —
    is useless to someone who already created one, and it is what the operator got after following the guide and
    pasting a LINK instead of the password. So the stored value is looked at first: when it CANNOT be an app
    password we say what was pasted, and only otherwise fall back to the per-provider causes."""
    try:
        from connectors.email import credentials as _creds
        pid = config.resolved_provider_id()
        why = _creds.diagnose(pid, config.address(), config.password())
        if why:
            return why
    except Exception:
        pid = ""
    tail = ("La contraseña es correcta pero el servidor la rechaza: revisa la dirección y que la contraseña de "
            "aplicación siga activa.")
    if pid == "gmail":
        domain = config.address().split("@")[-1].lower()
        own = domain and "gmail" not in domain and "googlemail" not in domain
        tail = ("Comprueba en Gmail que el acceso IMAP esté ACTIVADO (Configuración → Reenvío y correo POP/IMAP) "
                "y que la contraseña de aplicación siga activa.")
        if own:
            # A custom domain on Google Workspace: same servers, but two extra switches only an admin can flip.
            tail += (f" Tu dirección es de tu propio dominio ({domain}), así que puede ser Google Workspace: ahí "
                     "el administrador puede tener desactivadas las contraseñas de aplicación o el acceso IMAP.")
    return f"No pude iniciar sesión con esa contraseña. {tail}"


def _friendly_error(why: str) -> str:
    """Translate the technical reason for an IMAP/SMTP failure into something ACTIONABLE for the user (no jargon)."""
    w = (why or "").lower()
    if "imap" in w and ("auth" in w or "login" in w or "invalid credentials" in w or "[alert]" in w):
        return _auth_failure_hint()
    if "smtp" in w and ("auth" in w or "5.7" in w or "login" in w):
        return ("El correo se lee pero no pude autenticar el ENVÍO (SMTP). Suele ser la misma contraseña de "
                "aplicación; revisa que el envío por SMTP esté permitido en tu cuenta.")
    if "nodename" in w or "not known" in w or "getaddrinfo" in w or "resolve" in w:
        return "No encuentro el servidor de correo. Revisa el proveedor o los servidores IMAP/SMTP."
    if "timed out" in w or "timeout" in w:
        return "El servidor de correo no respondió a tiempo. Revisa tu conexión y vuelve a intentarlo."
    if "certificate" in w or "ssl" in w:
        return "Error de seguridad (SSL) al conectar con el servidor de correo. Revisa el host/puerto."
    return f"No pude conectar con tu correo: {why}"
