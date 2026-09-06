#
# service.py — the provider-AGNOSTIC facade of the video-account connectors (V2-597). The ONLY thing the rest
# of the system imports. Fail-safe by contract: every entry returns {"ok": False, "error": …} — it never
# raises to a caller, because a widget action or a status pull must degrade to words, not to a traceback.
#
# The V2-557 rule that matters most here: a legitimate emptiness must not look like a failure. An account
# with ZERO subscriptions answers `ok: True` with a `reason` — collapsing them is how «tu cuenta no tiene
# nada» gets shown to someone whose account is full, and how a real defect gets diagnosed as an empty account.
#
from __future__ import annotations

import time

from connectors.video import oauth, providers
from connectors.video import youtube as _yt

# How many subscriptions get their uploads pulled, and how many uploads each. 25×2 keeps the pull under a
# minute of sequential round-trips and ~26 quota units; the widget caps what it SHOWS separately.
_MAX_CHANNELS = 25
_PER_CHANNEL = 2
_MAX_ITEMS = 24


def available() -> bool:
    """Is the video-ACCOUNT layer usable at all? (V2-603 F2 — operator's directive, 2026-09-06.)

    False until an OAuth client exists for some provider — either the one shipped with the engine
    (`providers.builtin_client_id`, empty until Zaelar registers its Google app) or one the operator pasted
    in ⚙ → Conectores. While it is False the connector is **hidden, not shown-and-broken**: the card renders
    no platform row, the voice declines instead of opening a dead wizard, and the brain is told the capability
    does not exist yet so it cannot narrate it (V2-540's rule).

    The gate is DERIVED, never a flag anybody has to remember to flip: the day the client id lands in the
    registry — or a self-hoster pastes their own — every surface turns on by itself. A hand-set switch is a
    second thing to get wrong, and this one would be got wrong exactly once, silently, on release day.

    Measured 2026-09-06 (session e1acdcca): with no client registered, offering «conectar tu cuenta» led to
    nine minutes of a wizard that could not finish, because nothing in the product said the door was shut."""
    try:
        return any(oauth.configured(p.id) for p in providers.PROVIDERS.values())
    except Exception:
        return False


def providers_public() -> list[dict]:
    return providers.public_list()


def status() -> dict:
    """Per-provider connection state, REDACTED (a token never leaves this module)."""
    try:
        return {"ok": True, "providers": oauth.status()}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200], "providers": []}


def _prepared(provider_id: str):
    """Resolve provider + token once, so every entry point reports the same three failures with the same
    words (the V2-557 pattern). Returns (provider, token, error_dict|None)."""
    p = providers.get(provider_id)
    if not p:
        return None, None, {"ok": False, "error": f"proveedor desconocido: {provider_id or '(vacío)'}"}
    if not oauth.configured(p.id):
        return None, None, {"ok": False, "error": f"sin app OAuth registrada para {p.label} "
                                                  f"(el client_id se pone una vez en Configuración → Conectores)"}
    if not oauth.tokens_present(p.id):
        return None, None, {"ok": False, "error": f"{p.label} no está conectado — conéctalo desde la tarjeta"}
    tok = oauth.access_token(p.id)
    if not tok:
        return None, None, {"ok": False, "error": f"la sesión con {p.label} caducó — reconecta la cuenta"}
    return p, tok, None


def connect_url(provider_id: str, tier_id: str = "") -> dict:
    """The consent URL for a provider whose app is already registered. INTENT only — credentials are typed
    once in ⚙ → Conectores, never through this door (V2-520)."""
    try:
        return oauth.authorize_url(provider_id, tier_id)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


def disconnect(provider_id: str) -> dict:
    try:
        return oauth.forget(provider_id)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


def suggestions(provider_id: str = "youtube", limit: int = _MAX_ITEMS) -> dict:
    """The home band: recent uploads from the account's subscriptions, newest first, NORMALIZED
    ({videoId,title,channel,published,url}). Per-provider on purpose — results from two platforms are never
    mixed (operator's rule); the widget selects a platform, this fetches exactly that one.

    Blocked-channel filtering is deliberately NOT applied here: the filter is the WIDGET's data (V2-596),
    and the facade must stay usable by a caller with different filters."""
    import httpx
    p, tok, err = _prepared(provider_id)
    if err:
        return err
    try:
        with httpx.Client() as client:
            subs = _yt.list_subscriptions(client, p.api_base, tok, max_n=_MAX_CHANNELS * 2)
            if not subs.get("ok"):
                return {"ok": False, "error": subs.get("error") or "no pude leer las suscripciones"}
            channels = subs.get("channels") or []
            if not channels:
                return {"ok": True, "provider": p.id, "items": [], "channels": 0,
                        "reason": "la cuenta no tiene suscripciones — no hay de dónde sacar sugerencias"}
            items = []
            for ch in channels[:_MAX_CHANNELS]:
                items.extend(_yt.channel_recent_uploads(client, p.api_base, tok,
                                                        ch["channel_id"], ch["channel"], n=_PER_CHANNEL))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"no pude hablar con {p.label}: {e}"[:200]}
    items.sort(key=lambda it: it.get("published") or "", reverse=True)
    items = items[:max(1, min(int(limit or _MAX_ITEMS), 50))]
    out = {"ok": True, "provider": p.id, "items": items, "channels": len(channels),
           "fetched_at": int(time.time())}
    if not items:
        # Subscriptions exist and no uploads came back: a different fact than an empty account, said apart.
        out["reason"] = "tus suscripciones no devolvieron vídeos recientes"
    return out


def brain_state() -> str:
    """One compact line per platform with its REAL connection state, for the FlashBrain turn prompt (V2-603).

    The gap this closes is the expensive one. The brain already received this connector's ACTION LIST on every
    turn (`widgets/brief.py`) — `connect_account`, `open_connectors`, `suggest` — and never once received the
    FACT that no OAuth app was registered and no account connected. Asked to connect an account, it had a verb
    and no state, so it narrated the outcome it assumed: «Hecho.», «La autentificación quedó completada»,
    «Te conecto YouTube ahora mismo» (measured 2026-09-06, session e1acdcca — four claims, zero connections).

    `connectors/messaging/brief._platform_states()` is the same fix for the same failure, and its docstring
    records the same symptom («it invented "you have no important messages" while the widget was closed»).
    Video is the third connector family and the first that had to pay for it twice, so the wording here follows
    V2-582's rule: a state gets WORDS, never a bare enum — «error» reads as neither connected nor disconnected
    and the model fills that ambiguity in both directions.

    Deliberately short (~3 lines): this rides the hot prompt, gated by the card being open (`prompt.py`)."""
    if not available():
        # DECLARED, not omitted. Silence is what let the model invent «Hecho.» in the first place: it had the
        # verbs in its action list and no fact to check them against. Naming the absence is what makes
        # declining possible.
        return ("VÍDEO (cuentas): conectar una cuenta de YouTube TODAVÍA NO ESTÁ DISPONIBLE en esta versión "
                "— la puerta no existe aún, no es que esté desconectada. NO lo ofrezcas, NO digas que puedes "
                "conectarla ni vincularla, y NO abras ninguna tarjeta de conexión. Si te lo piden, dilo con "
                "naturalidad: todavía no está listo. El reproductor de vídeo funciona con normalidad "
                "(buscar, poner, listas): eso NO depende de ninguna cuenta.")
    try:
        rows = oauth.status()
    except Exception:
        return ""
    if not rows:
        return ""
    lines = []
    for r in rows:
        label = r.get("label") or r.get("id")
        if r.get("connected"):
            state = f"CONECTADO ({r.get('tier_label') or r.get('tier') or 'solo lectura'})"
        elif r.get("app_configured"):
            state = ("SIN conectar — la app OAuth ya está registrada, solo falta que el operador AUTORICE "
                     "su cuenta desde la tarjeta")
        else:
            state = ("SIN conectar y SIN app OAuth registrada — no se puede conectar todavía; el operador "
                     "tiene que completar el alta desde la tarjeta")
        lines.append(f"{label}: {state}.")
    lines.append(
        "NUNCA digas que has conectado, vinculado o autorizado una cuenta: tú no puedes: el consentimiento lo "
        "da el operador en la ventana del proveedor. Lo ÚNICO que haces es abrirle la tarjeta con "
        "`widget_data(youtube, open_connectors)` y decirle qué paso le toca. Si arriba pone SIN conectar, "
        "sigue SIN conectar por mucho que se haya abierto un navegador o iniciado sesión en Google: entrar en "
        "Google NO conecta este conector.")
    return "VÍDEO (cuentas):\n" + "\n".join(lines)
