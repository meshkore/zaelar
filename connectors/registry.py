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
    try:
        from connectors.spotify import auth
        st = auth.status() or {}
        return [{"id": "spotify", "label": "Spotify", "family": "musica", "auth": "oauth",
                 "connected": bool(st.get("logged_in")), "status": "connected" if st.get("logged_in") else "off",
                 "detail": "Play and control Spotify (OAuth).", "config": st}]
    except Exception as e:
        return [{"id": "spotify", "label": "Spotify", "family": "musica", "auth": "oauth",
                 "connected": False, "status": "error", "detail": str(e), "config": {}}]


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


# Stable family order (messaging -> music -> files -> photos -> infra) for the tab.
def descriptors() -> list[dict]:
    """Complete connector inventory with state + redacted config. Each source is isolated (a broken connector does
    not take down the registry)."""
    return [*_messaging(), *_music(), *_files(), *_photos(), *_architect(), *_meshkore()]
