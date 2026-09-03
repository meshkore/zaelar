#
# credentials.py — what the user PASTES into the app-password box, and what to say when it is not a password
# (V2-559). Split out of config/control because THREE callers need the same verdict and they used to have none:
# the widget (before enqueuing), control.validate_connect (before persisting) and service._friendly_error (after
# IMAP said no).
#
# Why it exists: the connect form accepted any string. The operator followed the guide, created the app password
# at myaccount.google.com/apppasswords, and pasted a LINK instead of the password — 47 characters starting with
# `https://`. It was stored verbatim, IMAP answered `[AUTHENTICATIONFAILED] Invalid credentials`, and the card
# told him his credentials were wrong. Every word of that was true and none of it was useful: the product held
# the evidence (a URL is not a 16-letter app password) and threw it away to print a generic reason.
#
# Two jobs, both pure and stdlib-only so the widget's contract and the connector share one source of truth:
#   · normalize() — Google shows the app password as `abcd efgh ijkl mnop`. Those spaces are presentation; the
#     IMAP AUTH does not want them. Stripping them is not a guess, it is the documented form.
#   · diagnose()  — name what was pasted when it CANNOT be an app password, in the user's words.
#
# The shape check is deliberately narrow. It only fires where the provider publishes a fixed format (Google and
# Apple: 16 letters), and never for Outlook/Yahoo/IMAP, whose formats vary — a false "that is not a password"
# would lock a user out of a mailbox that works, which is worse than the generic error this replaces.
#
import re

# Providers whose app password has a documented, fixed shape: 16 ASCII letters (Google shows them in four
# groups of four separated by spaces; Apple by dashes). Anything else here is certainly not the password.
_FIXED_16_LETTERS = ("gmail", "icloud")

_URL_RE = re.compile(r"^(?:[a-z][a-z0-9+.\-]*://|www\.)", re.I)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)


def normalize(raw) -> str:
    """The password as the mail server wants it: no whitespace anywhere (not just the ends). `str.strip()` was
    what we had, and it leaves `abcd efgh ijkl mnop` — the exact string Google puts on screen — intact."""
    return re.sub(r"\s+", "", str(raw or ""))


def _core(provider_id: str, pwd: str) -> str:
    """The letters alone, for a shape check: Apple's separators are part of what it displays and its sign-in
    accepts the password with or without them, so they must not count against the length."""
    return pwd.replace("-", "") if (provider_id or "").lower() == "icloud" else pwd


def looks_like_app_password(provider_id: str, raw) -> bool:
    """True when the value could be this provider's app password. Providers with no published format always
    answer True — absence of a rule is not evidence of a bad password."""
    pwd = normalize(raw)
    if not pwd or _URL_RE.match(pwd) or _EMAIL_RE.match(pwd):
        return False
    if (provider_id or "").lower() in _FIXED_16_LETTERS:
        core = _core(provider_id, pwd)
        return len(core) == 16 and core.isascii() and core.isalpha()
    return True


def diagnose(provider_id: str, address: str, raw) -> str | None:
    """A message naming what was pasted, or None when the value is plausible. User-facing product text (Spanish),
    like every other string this connector puts on the card."""
    pwd = normalize(raw)
    if not pwd:
        return "Necesito la contraseña de aplicación (no tu contraseña normal del correo)."
    if _URL_RE.match(pwd):
        return ("Eso es un ENLACE, no la contraseña. Abre el enlace, crea allí la contraseña de aplicación y "
                "pega aquí la CONTRASEÑA que te muestre (16 letras, sin espacios).")
    if _EMAIL_RE.match(pwd):
        return "Eso es una dirección de correo, no la contraseña de aplicación."
    if (address or "").strip().lower() and pwd.lower() == (address or "").strip().lower():
        return "Has pegado tu dirección otra vez. En este campo va la contraseña de aplicación."
    pid = (provider_id or "").lower()
    if pid in _FIXED_16_LETTERS:
        core = _core(pid, pwd)
        who = "Google" if pid == "gmail" else "Apple"
        if not (core.isascii() and core.isalpha()):
            return (f"La contraseña de aplicación de {who} son 16 LETRAS, sin números ni símbolos. "
                    "Parece que has pegado otra cosa.")
        if len(core) != 16:
            return (f"La contraseña de aplicación de {who} son 16 letras y me has pegado {len(core)}. "
                    "Cópiala entera, tal cual te la muestra la página.")
    return None
