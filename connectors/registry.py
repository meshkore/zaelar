#
# Connectors registry — SINGLE typed inventory of ALL agent connectors (V2-083).
#
# Previously the catalog was scattered (config/connectors.py=messaging, spotify/auth, meshkore, architect). This
# unifies it in ONE point for the Configuration "Connectors" tab: each connector with family, auth method, state
# (connected/authenticated), and which credentials are set (REDACTED). Connectors are NATIVE: connection code lives
# in `connectors/<x>/`, but ALL configuration/credentials are DYNAMIC, visible, revocable, and authenticatable from
# the frontend — NOTHING in `.env` (env only as power-user fallback).
#
# Read-only: this module only READS state. WRITES (connect/disconnect/revoke) go through the existing endpoints for
# each family (`/api/messaging/*`, `/api/spotify/*`, `/api/meshkore/*`) + architect endpoints (V2-083).
#
from __future__ import annotations

# Descriptor for each connector:
#   id · label · family (mensajeria|musica|infra) · auth (qr|app-password|oauth|token|cluster)
#   connected (bool) · detail (human str) · config (REDACTED dict) · [clusters] (meshkore only)


def _messaging() -> list[dict]:
    out = []
    try:
        from config import connectors as cfg
        from connectors.messaging import control, store
        live = store.load().get("platforms", {})
        meta = {
            "whatsapp": ("WhatsApp", "qr"),
            "telegram": ("Telegram", "app-password"),   # api_id/api_hash → then QR
            "email": ("Email", "app-password"),
        }
        for p in control.PLATFORMS:
            pub = cfg.public(p)
            lv = live.get(p) or {}
            status = str(lv.get("status") or ("off" if not pub.get("enabled") else "starting"))
            label, auth = meta.get(p, (p.title(), "app-password"))
            out.append({"id": p, "label": label, "family": "mensajeria", "auth": auth,
                        "connected": status == "connected", "status": status,
                        "detail": str(lv.get("detail") or ""), "qr": lv.get("qr"), "config": pub})
    except Exception as e:
        out.append({"id": "messaging", "label": "Messaging", "family": "mensajeria", "auth": "app-password",
                    "connected": False, "status": "error", "detail": f"registry unavailable: {e}", "config": {}})
    return out


def _music() -> list[dict]:
    # V2-631: the DEFAULT free source is a row too — the tab is the operator's source catalog, and the source
    # everything actually plays through was invisible in it. Always connected (no login, no key); the priority
    # rule lives in connectors/music/registry.py: a connected Spotify outranks it, YouTube-audio never goes away.
    yt_row = {"id": "youtube-audio", "label": "YouTube (audio gratis)", "family": "musica", "auth": "none",
              "connected": True, "status": "connected",
              "detail": "Default free source — plays without an account. A connected Spotify takes priority.",
              "config": {}}
    try:
        from connectors.spotify import auth
        st = auth.status() or {}
        return [{"id": "spotify", "label": "Spotify", "family": "musica", "auth": "oauth",
                 "connected": bool(st.get("logged_in")), "status": "connected" if st.get("logged_in") else "off",
                 "detail": "Play and control Spotify (OAuth).", "config": st}, yt_row]
    except Exception as e:
        return [{"id": "spotify", "label": "Spotify", "family": "musica", "auth": "oauth",
                 "connected": False, "status": "error", "detail": str(e), "config": {}}, yt_row]


def _files() -> list[dict]:
    """Cloud file connectors (V2-557). One row per provider, each isolated like the rest: a broken import here
    must not empty the whole Connectors tab. `browsable` travels because a connected provider whose granted
    scope cannot list folders is NOT the same state as a connected one that can, and the tab is where the
    operator can act on the difference."""
    try:
        from connectors.files import oauth, providers
        # The tab renders a PERMISSION selector, and the tiers live in the catalog while the connection state
        # lives in the token store. Merging here is what stops the form from offering an empty dropdown — the
        # same mismatch the widget's own connect panel had before this.
        catalog = {c["id"]: c for c in providers.public_list()}
        out = []
        for st in oauth.status():
            cat = catalog.get(st["id"], {})
            connected = bool(st.get("connected"))
            out.append({"id": st["id"], "label": st["label"], "family": "archivos", "auth": "oauth",
                        "connected": connected,
                        "status": "connected" if connected else ("off" if st.get("app_configured")
                                                                 else "unconfigured"),
                        "detail": st.get("note") or "",
                        "config": {"app_configured": bool(st.get("app_configured")),
                                   "tier": st.get("tier") or "", "tier_label": st.get("tier_label") or "",
                                   "browsable": bool(st.get("browsable")),
                                   "tiers": cat.get("tiers") or [],
                                   "default_tier": cat.get("default_tier") or ""}})
        return out
    except Exception as e:
        return [{"id": "files", "label": "Archivos en la nube", "family": "archivos", "auth": "oauth",
                 "connected": False, "status": "error", "detail": str(e), "config": {}}]


def _photos() -> list[dict]:
    """Photo-library connectors (V2-564). Google's Picker never hands back a standing feed of "the whole
    library" — see `connectors/photos/providers.py` — so `browsable` is always False here, unlike `_files()`,
    where a connected provider CAN carry a browsable tier."""
    try:
        from connectors.photos import oauth, providers
        catalog = {c["id"]: c for c in providers.public_list()}
        out = []
        for st in oauth.status():
            cat = catalog.get(st["id"], {})
            connected = bool(st.get("connected"))
            out.append({"id": st["id"], "label": st["label"], "family": "fotos", "auth": "oauth",
                        "connected": connected,
                        "status": "connected" if connected else ("off" if st.get("app_configured")
                                                                 else "unconfigured"),
                        "detail": st.get("note") or "",
                        "config": {"app_configured": bool(st.get("app_configured")),
                                   "tiers": cat.get("tiers") or [],
                                   "default_tier": cat.get("default_tier") or ""}})
        return out
    except Exception as e:
        return [{"id": "photos", "label": "Fotos", "family": "fotos", "auth": "oauth",
                 "connected": False, "status": "error", "detail": str(e), "config": {}}]


def _videoaccounts() -> list[dict]:
    """Video-account connectors (V2-597). One row per provider (YouTube only in v1), isolated like the rest:
    a broken import here must not empty the whole Connectors tab. Status trichotomy mirrors `_files()`:
    connected → off (app registered, not connected) → unconfigured (no client_id yet)."""
    try:
        from connectors.video import oauth, providers
        catalog = {c["id"]: c for c in providers.public_list()}
        out = []
        for st in oauth.status():
            cat = catalog.get(st["id"], {})
            connected = bool(st.get("connected"))
            out.append({"id": st["id"], "label": st["label"], "family": "video", "auth": "oauth",
                        "connected": connected,
                        "status": "connected" if connected else ("off" if st.get("app_configured")
                                                                 else "unconfigured"),
                        "detail": st.get("note") or "",
                        "config": {"app_configured": bool(st.get("app_configured")),
                                   "tier": st.get("tier") or "", "tier_label": st.get("tier_label") or "",
                                   "tiers": cat.get("tiers") or [],
                                   "default_tier": cat.get("default_tier") or ""}})
        return out
    except Exception as e:
        return [{"id": "youtube", "label": "YouTube (cuenta)", "family": "video", "auth": "oauth",
                 "connected": False, "status": "error", "detail": str(e), "config": {}}]


def _calendar() -> list[dict]:
    """Calendar-account connectors (V2-679). family="agenda" on purpose: `widgets/agenda/data.py::calendars()`
    reads exactly this family (or "calendar", both accepted), keyed by id "google" — matching
    `connectors/calendar/providers.py`'s registry id so this row REPLACES the widget's own "not built yet"
    placeholder instead of standing beside it."""
    try:
        from connectors.calendar import oauth, providers
        catalog = {c["id"]: c for c in providers.public_list()}
        out = []
        for st in oauth.status():
            cat = catalog.get(st["id"], {})
            connected = bool(st.get("connected"))
            out.append({"id": st["id"], "label": st["label"], "family": "agenda", "auth": "oauth",
                        "connected": connected,
                        "status": "connected" if connected else ("off" if st.get("app_configured")
                                                                 else "unconfigured"),
                        "detail": st.get("note") or "",
                        "config": {"app_configured": bool(st.get("app_configured")),
                                   "tier": st.get("tier") or "", "tier_label": st.get("tier_label") or "",
                                   "tiers": cat.get("tiers") or [],
                                   "default_tier": cat.get("default_tier") or ""}})
        return out
    except Exception as e:
        return [{"id": "google", "label": "Google Calendar", "family": "agenda", "auth": "oauth",
                 "connected": False, "status": "error", "detail": str(e), "config": {}}]


def _contacts() -> list[dict]:
    """Address-book connectors (V2-699). family="contactos" on purpose: `widgets/contactos/gcontacts.py::
    providers()` reads exactly this family, keyed by id "google" — matching
    `connectors/contacts/providers.py`'s registry id so this row REPLACES the widget's own "not built yet"
    placeholder instead of standing beside it. The same contract the calendar row settled in V2-679."""
    try:
        from connectors.contacts import oauth, providers
        catalog = {c["id"]: c for c in providers.public_list()}
        out = []
        for st in oauth.status():
            cat = catalog.get(st["id"], {})
            connected = bool(st.get("connected"))
            out.append({"id": st["id"], "label": st["label"], "family": "contactos", "auth": "oauth",
                        "connected": connected,
                        "status": "connected" if connected else ("off" if st.get("app_configured")
                                                                 else "unconfigured"),
                        "detail": st.get("note") or "",
                        "config": {"app_configured": bool(st.get("app_configured")),
                                   "tier": st.get("tier") or "", "tier_label": st.get("tier_label") or "",
                                   "tiers": cat.get("tiers") or [],
                                   "default_tier": cat.get("default_tier") or ""}})
        return out
    except Exception as e:
        return [{"id": "google-contacts", "label": "Google Contacts", "family": "contactos", "auth": "oauth",
                 "connected": False, "status": "error", "detail": str(e), "config": {}}]


def _google() -> list[dict]:
    """The Google ACCOUNT row (V2-685) — the identity, not a sixth surface.

    Gmail, Calendar, Meet, Drive, Photos and YouTube already appear in their own families, each with its
    own card and its own tokens. What had no row anywhere was the thing they SHARE: the OAuth app. When it
    is missing, all five go dormant at once and each of them says so separately, which reads as five
    unrelated faults instead of one missing answer. family="infra" because it is not a widget surface —
    it is what the surfaces authenticate against.

    `connected` counts services with live tokens, so the row distinguishes the three states that need
    different actions: no app registered at all, an app nobody has consented to yet, and a working account.
    """
    try:
        from connectors.google import app as gapp, services as gsvc
        st = gapp.status()
        live: list[str] = []
        for svc in gsvc.SERVICES.values():
            if not svc.owner:
                continue                                   # Meet has no flow of its own: it rides calendar
            try:
                mod = __import__(f"{svc.owner}.oauth", fromlist=["oauth"])
                rows = mod.status() or []
                if any(r.get("connected") for r in (rows if isinstance(rows, list) else [rows])):
                    live.append(svc.id)
            except Exception:                              # noqa: BLE001 — one broken door never hides the rest
                continue
        if "calendar" in live:
            live.append("meet")                            # a connected calendar IS a usable Meet
        configured = bool(st.get("configured"))
        # id "google-account", NOT "google": `_calendar()` already ships a row keyed "google" (its provider
        # id, which `widgets/agenda/data.py::_CALENDARS` matches on). Two rows with one id is a collision the
        # tab resolves by showing whichever it saw last — the account row would have eaten the calendar card.
        return [{"id": "google-account", "label": "Google (cuenta)", "family": "infra", "auth": "oauth",
                 "connected": bool(live),
                 "status": "connected" if live else ("off" if configured else "unconfigured"),
                 "detail": ("Una sola cuenta para Gmail, Calendar, Meet, Drive, Fotos y YouTube."
                            if configured else
                            "Falta el cliente OAuth de Google: deja el client_secret_*.json de Google Cloud "
                            "en .meshkore/credentials/ y se activan las seis puertas a la vez."),
                 "config": {"app_configured": configured, "source": st.get("source") or "",
                            "project_id": st.get("project_id") or "",
                            "web_client": bool(st.get("web_client")),
                            "redirect_uris": st.get("redirect_uris") or [],
                            "services": gsvc.public_list(), "connected_services": sorted(set(live))}}]
    except Exception as e:                                 # noqa: BLE001
        return [{"id": "google-account", "label": "Google (cuenta)", "family": "infra", "auth": "oauth",
                 "connected": False, "status": "error", "detail": str(e), "config": {}}]


def _architect() -> list[dict]:
    try:
        from config import connectors as cfg
        from connectors.architect import client
        pub = cfg.public("architect")
        connected = client.configured()
        return [{"id": "architect", "label": "Architect (code daemon)", "family": "infra", "auth": "token",
                 "connected": connected, "status": "connected" if connected else "off",
                 "detail": "Code projects/agents on the MeshKore daemon. Dynamic token (revocable).",
                 "config": pub}]
    except Exception as e:
        return [{"id": "architect", "label": "Architect", "family": "infra", "auth": "token",
                 "connected": False, "status": "error", "detail": str(e), "config": {}}]


def _meshkore() -> list[dict]:
    try:
        from connectors import meshkore
        mgr = meshkore.get_manager()
        clusters = mgr.clusters() if mgr else []
        # `clusters()` gives the known/connected cluster list; normalize it to {name, connected}.
        norm = []
        for c in (clusters or []):
            if isinstance(c, dict):
                norm.append({"name": c.get("name") or c.get("id") or "?",
                             "connected": bool(c.get("connected", True))})
            else:
                norm.append({"name": str(c), "connected": True})
        return [{"id": "meshkore", "label": "MeshKore (cluster / team)", "family": "infra", "auth": "cluster",
                 "connected": bool(norm), "status": "connected" if norm else "off",
                 "detail": "Access to the team/cluster via cluster_id + token (dynamic, revocable).",
                 "clusters": norm, "config": {}}]
    except Exception as e:
        return [{"id": "meshkore", "label": "MeshKore", "family": "infra", "auth": "cluster",
                 "connected": False, "status": "error", "detail": str(e), "clusters": [], "config": {}}]


# Stable family order (messaging -> music -> files -> photos -> video -> agenda -> infra) for the tab.
# Google leads `infra`: it is the account the five surfaces above authenticate against (V2-685).
#: A source that serves MORE THAN ONE family (V2-714). `family` stays a single string — every view in the
#: engine reads it and none of them changes — and `families` is the full list, first entry being that same
#: `family`. Whoever asks «which sources are mine?» reads `families`.
#:
#: Why it exists, in his words: «quiero todos mis contactos juntos en un sitio… no me importa que el
#: conector viva duplicado en varios widgets, eso le da claridad al asunto». Measured 2026-09-16 (session
#: c20123ab): he opened the contacts card looking for Telegram and WhatsApp and saw «Google and Apple and
#: another one», because the strip filters on `family == "contactos"` and those two are `mensajeria`.
#: One DECLARATION read by whoever needs it, never two ids hardcoded into a widget's source list.
_ALSO: dict[str, tuple[str, ...]] = {
    "telegram": ("contactos",),
    "whatsapp": ("contactos",),
}


def _with_families(rows: list[dict]) -> list[dict]:
    for d in rows:
        fam = str(d.get("family") or "")
        extra = _ALSO.get(str(d.get("id") or ""), ())
        d["families"] = [f for f in (fam, *extra) if f]
    return rows


def serves(d: dict, family: str) -> bool:
    """Does this descriptor serve `family`? The ONE reader, so a strip and a settings tab can never
    disagree about whether Telegram belongs in Contacts."""
    fams = d.get("families")
    if not isinstance(fams, list) or not fams:
        fams = [str(d.get("family") or "")]
    return str(family or "") in fams


def descriptors() -> list[dict]:
    """Complete connector inventory with state + redacted config. Each source is isolated (a broken connector does
    not take down the registry)."""
    return _with_families([*_messaging(), *_music(), *_files(), *_photos(), *_videoaccounts(), *_calendar(),
                           *_contacts(), *_google(), *_architect(), *_meshkore()])
